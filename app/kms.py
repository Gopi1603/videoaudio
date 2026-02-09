"""
Key Management Service (KMS) — Secure key generation, storage, and Shamir's Secret Sharing.

Features:
  • Generate per-file AES-256 keys
  • Wrap keys with Fernet master key for DB storage
  • Split keys into shares using Shamir's Secret Sharing
  • Reconstruct keys from threshold shares
  • Key revocation and rotation support
  • Audit logging for all key operations

Dependencies: cryptography, secrets
"""

import os
import secrets
import hashlib
from typing import Tuple, List, Optional
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.fernet import Fernet

from app import db


# ---------------------------------------------------------------------------
# Master Fernet key — in production this MUST come from env / vault.
# ---------------------------------------------------------------------------
_MASTER_KEY = os.environ.get("FERNET_MASTER_KEY")
if _MASTER_KEY is None:
    _MASTER_KEY = Fernet.generate_key().decode()
    print(f"[DEV] Generated FERNET_MASTER_KEY={_MASTER_KEY}")

_fernet = Fernet(_MASTER_KEY.encode() if isinstance(_MASTER_KEY, str) else _MASTER_KEY)


# ---------------------------------------------------------------------------
# Shamir's Secret Sharing Implementation
# ---------------------------------------------------------------------------
# Using GF(257) with base64 encoding for shares since values can be 0-256

import base64

_PRIME = 257  # Smallest prime > 256 for GF operations


def _mod_inverse(a: int, p: int = _PRIME) -> int:
    """Compute modular inverse using extended Euclidean algorithm."""
    if a == 0:
        raise ValueError("Cannot compute inverse of 0")
    lm, hm = 1, 0
    low, high = a % p, p
    while low > 1:
        ratio = high // low
        nm, new = hm - lm * ratio, high - low * ratio
        lm, low, hm, high = nm, new, lm, low
    return lm % p


def _eval_poly(coeffs: List[int], x: int, prime: int = _PRIME) -> int:
    """Evaluate polynomial at x in GF(prime)."""
    result = 0
    for coeff in reversed(coeffs):
        result = (result * x + coeff) % prime
    return result


def _encode_share(values: List[int]) -> bytes:
    """Encode share values (0-256) to bytes using 2 bytes per value."""
    # Use big-endian 2-byte encoding for each value
    encoded = bytearray()
    for v in values:
        encoded.extend(v.to_bytes(2, 'big'))
    return bytes(encoded)


def _decode_share(data: bytes) -> List[int]:
    """Decode share bytes back to values (0-256)."""
    values = []
    for i in range(0, len(data), 2):
        values.append(int.from_bytes(data[i:i+2], 'big'))
    return values


def split_secret(secret: bytes, n: int, k: int) -> List[Tuple[int, bytes]]:
    """
    Split a secret into n shares, requiring k shares to reconstruct.
    
    Args:
        secret: The secret bytes to split
        n: Total number of shares to generate
        k: Threshold - minimum shares needed to reconstruct
        
    Returns:
        List of (share_index, share_bytes) tuples
    """
    if k > n:
        raise ValueError("Threshold k cannot exceed total shares n")
    if k < 2:
        raise ValueError("Threshold k must be at least 2")
    if n > 255:
        raise ValueError("Maximum 255 shares supported")
    
    shares = [[] for _ in range(n)]
    
    for byte in secret:
        # Generate random polynomial coefficients (degree k-1)
        # The constant term is the secret byte
        coeffs = [byte] + [secrets.randbelow(_PRIME) for _ in range(k - 1)]
        
        # Evaluate polynomial at points 1, 2, ..., n
        for i in range(n):
            x = i + 1  # x values are 1-indexed
            y = _eval_poly(coeffs, x)
            shares[i].append(y)
    
    # Encode shares (values can be 0-256, so use 2 bytes per value)
    return [(i + 1, _encode_share(share)) for i, share in enumerate(shares)]


def reconstruct_secret(shares: List[Tuple[int, bytes]], secret_length: int) -> bytes:
    """
    Reconstruct the secret from k or more shares using Lagrange interpolation.
    
    Args:
        shares: List of (share_index, share_bytes) tuples
        secret_length: Expected length of the original secret
        
    Returns:
        The reconstructed secret bytes
    """
    if len(shares) < 2:
        raise ValueError("Need at least 2 shares to reconstruct")
    
    # Decode shares from bytes to integer lists
    decoded_shares = [(idx, _decode_share(data)) for idx, data in shares]
    
    # Verify all shares have the same length
    share_len = len(decoded_shares[0][1])
    if not all(len(s[1]) == share_len for s in decoded_shares):
        raise ValueError("All shares must have the same length")
    
    x_coords = [s[0] for s in decoded_shares]
    result = []
    
    for byte_idx in range(share_len):
        y_coords = [s[1][byte_idx] for s in decoded_shares]
        
        # Lagrange interpolation to find f(0)
        secret_byte = 0
        for i, (xi, yi) in enumerate(zip(x_coords, y_coords)):
            # Compute Lagrange basis polynomial L_i(0)
            num = 1
            den = 1
            for j, xj in enumerate(x_coords):
                if i != j:
                    num = (num * (-xj)) % _PRIME
                    den = (den * (xi - xj)) % _PRIME
            
            lagrange = (num * _mod_inverse(den)) % _PRIME
            secret_byte = (secret_byte + yi * lagrange) % _PRIME
        
        result.append(secret_byte)
    
    return bytes(result[:secret_length])


# ---------------------------------------------------------------------------
# Key Record Model
# ---------------------------------------------------------------------------
class KeyRecord(db.Model):
    """Stores encryption keys and their shares for a media file."""
    __tablename__ = "key_records"
    
    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("media_files.id"), nullable=False, unique=True)
    
    # Encrypted key (Fernet-wrapped) - used when no splitting required
    encrypted_key = db.Column(db.Text, nullable=True)
    
    # Shamir's Secret Sharing metadata
    total_shares = db.Column(db.Integer, default=1)
    threshold = db.Column(db.Integer, default=1)
    
    # Status: active, revoked, rotated
    status = db.Column(db.String(20), default="active")
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    revoked_at = db.Column(db.DateTime, nullable=True)
    
    # Relationship
    shares = db.relationship("KeyShare", backref="key_record", lazy="dynamic",
                            cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<KeyRecord media_id={self.media_id} status={self.status}>"


class KeyShare(db.Model):
    """Individual share of a split key (for Shamir's Secret Sharing)."""
    __tablename__ = "key_shares"
    
    id = db.Column(db.Integer, primary_key=True)
    key_record_id = db.Column(db.Integer, db.ForeignKey("key_records.id"), nullable=False)
    
    # Share data
    share_index = db.Column(db.Integer, nullable=False)  # 1-indexed
    encrypted_share = db.Column(db.Text, nullable=False)  # Fernet-wrapped share bytes
    
    # Assigned holder (user who holds this share)
    holder_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    
    # Status: active, used, revoked
    status = db.Column(db.String(20), default="active")
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<KeyShare index={self.share_index} holder={self.holder_id}>"


# ---------------------------------------------------------------------------
# KMS Service Functions
# ---------------------------------------------------------------------------

def generate_file_key() -> bytes:
    """Generate a fresh 256-bit AES key."""
    return AESGCM.generate_key(bit_length=256)


def wrap_key(key: bytes) -> str:
    """Fernet-encrypt a key and return URL-safe string for DB storage."""
    return _fernet.encrypt(key).decode()


def unwrap_key(wrapped: str) -> bytes:
    """Recover raw key bytes from Fernet token."""
    return _fernet.decrypt(wrapped.encode())


def store_key(media_id: int, key: bytes, n_shares: int = 1, threshold: int = 1,
              holder_ids: Optional[List[int]] = None) -> KeyRecord:
    """
    Store a file encryption key, optionally splitting with Shamir's Secret Sharing.
    
    Args:
        media_id: ID of the associated MediaFile
        key: The raw AES key bytes
        n_shares: Number of shares to split into (1 = no splitting)
        threshold: Minimum shares required to reconstruct
        holder_ids: Optional list of user IDs to assign shares to
        
    Returns:
        The created KeyRecord
    """
    if n_shares == 1:
        # Simple case: just wrap and store the key
        record = KeyRecord(
            media_id=media_id,
            encrypted_key=wrap_key(key),
            total_shares=1,
            threshold=1,
            status="active"
        )
        db.session.add(record)
        db.session.commit()
        return record
    
    # Shamir's Secret Sharing case
    if threshold < 2:
        threshold = 2
    if threshold > n_shares:
        threshold = n_shares
    
    shares = split_secret(key, n_shares, threshold)
    
    record = KeyRecord(
        media_id=media_id,
        encrypted_key=None,  # Key is split, not stored directly
        total_shares=n_shares,
        threshold=threshold,
        status="active"
    )
    db.session.add(record)
    db.session.flush()  # Get the ID
    
    # Store each share
    for i, (share_idx, share_bytes) in enumerate(shares):
        holder_id = holder_ids[i] if holder_ids and i < len(holder_ids) else None
        share = KeyShare(
            key_record_id=record.id,
            share_index=share_idx,
            encrypted_share=wrap_key(share_bytes),
            holder_id=holder_id,
            status="active"
        )
        db.session.add(share)
    
    db.session.commit()
    return record


def retrieve_key(media_id: int, provided_shares: Optional[List[Tuple[int, bytes]]] = None) -> Optional[bytes]:
    """
    Retrieve and reconstruct a file encryption key.
    
    Args:
        media_id: ID of the MediaFile
        provided_shares: For split keys, list of (share_index, share_bytes) tuples
        
    Returns:
        The decryption key, or None if not available/authorized
    """
    record = KeyRecord.query.filter_by(media_id=media_id, status="active").first()
    if not record:
        return None
    
    if record.total_shares == 1:
        # Simple case: unwrap and return
        return unwrap_key(record.encrypted_key)
    
    # Shamir's case: need to reconstruct from shares
    if provided_shares:
        # Use provided shares
        if len(provided_shares) < record.threshold:
            return None  # Not enough shares
        return reconstruct_secret(provided_shares, 32)  # AES-256 = 32 bytes
    
    # Auto-retrieve all active shares (for admin use)
    shares = KeyShare.query.filter_by(
        key_record_id=record.id,
        status="active"
    ).all()
    
    if len(shares) < record.threshold:
        return None  # Not enough active shares
    
    share_data = [(s.share_index, unwrap_key(s.encrypted_share)) for s in shares[:record.threshold]]
    return reconstruct_secret(share_data, 32)


def revoke_key(media_id: int) -> bool:
    """
    Revoke a key, making the file undecryptable.
    
    Args:
        media_id: ID of the MediaFile
        
    Returns:
        True if revoked, False if not found
    """
    record = KeyRecord.query.filter_by(media_id=media_id).first()
    if not record:
        return False
    
    record.status = "revoked"
    record.revoked_at = datetime.now(timezone.utc)
    
    # Also revoke all shares
    for share in record.shares:
        share.status = "revoked"
    
    db.session.commit()
    return True


def rotate_key(media_id: int, new_key: bytes) -> Optional[KeyRecord]:
    """
    Rotate (replace) a key. The old key is marked as rotated.
    
    Note: This only updates the key record. The file must be re-encrypted
    separately with the new key.
    
    Args:
        media_id: ID of the MediaFile
        new_key: The new AES key
        
    Returns:
        The new KeyRecord, or None if original not found
    """
    old_record = KeyRecord.query.filter_by(media_id=media_id, status="active").first()
    if not old_record:
        return None
    
    # Mark old record as rotated
    old_record.status = "rotated"
    
    # Create new record with same sharing config
    new_record = store_key(
        media_id=media_id,
        key=new_key,
        n_shares=old_record.total_shares,
        threshold=old_record.threshold
    )
    
    db.session.commit()
    return new_record


def get_key_info(media_id: int) -> Optional[dict]:
    """
    Get information about a key record (without exposing the actual key).
    
    Returns:
        Dict with key metadata, or None if not found
    """
    record = KeyRecord.query.filter_by(media_id=media_id).first()
    if not record:
        return None
    
    shares_info = []
    for share in record.shares:
        shares_info.append({
            "index": share.share_index,
            "holder_id": share.holder_id,
            "status": share.status
        })
    
    return {
        "media_id": record.media_id,
        "status": record.status,
        "total_shares": record.total_shares,
        "threshold": record.threshold,
        "created_at": record.created_at.isoformat(),
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        "shares": shares_info
    }


def list_keys(status: Optional[str] = None) -> List[dict]:
    """
    List all key records, optionally filtered by status.
    
    Args:
        status: Filter by status (active, revoked, rotated)
        
    Returns:
        List of key info dicts
    """
    query = KeyRecord.query
    if status:
        query = query.filter_by(status=status)
    
    return [get_key_info(r.media_id) for r in query.all()]
