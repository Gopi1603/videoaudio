"""
Encryption module — AES-GCM for media encryption, Fernet for key wrapping.

Flow:
  1. Generate a random 256-bit AES key (the "file key").
  2. Encrypt the media bytes with AES-GCM (nonce || ciphertext || tag).
  3. Wrap the file key with a Fernet master key so it can be safely stored in the DB.
  4. On decrypt, unwrap the file key with Fernet, then decrypt media with AES-GCM.
"""

import os
import base64
import time
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Master Fernet key — in production this MUST come from env / vault.
# ---------------------------------------------------------------------------
_MASTER_KEY = os.environ.get("FERNET_MASTER_KEY")
if _MASTER_KEY is None:
    # Auto-generate for dev (printed once so the developer can persist it)
    _MASTER_KEY = Fernet.generate_key().decode()
    print(f"[DEV] Generated FERNET_MASTER_KEY={_MASTER_KEY}")

_fernet = Fernet(_MASTER_KEY.encode() if isinstance(_MASTER_KEY, str) else _MASTER_KEY)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def generate_file_key() -> bytes:
    """Return a fresh 256-bit AES key."""
    return AESGCM.generate_key(bit_length=256)


def wrap_key(file_key: bytes) -> str:
    """Fernet-encrypt the file key and return a URL-safe string for DB storage."""
    return _fernet.encrypt(file_key).decode()


def unwrap_key(wrapped: str) -> bytes:
    """Recover the raw AES key from its Fernet token."""
    return _fernet.decrypt(wrapped.encode())


# ---------------------------------------------------------------------------
# AES-GCM encrypt / decrypt
# ---------------------------------------------------------------------------

def encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt *plaintext* with AES-256-GCM.

    Returns ``nonce (12 B) || ciphertext+tag``.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ct


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    """Decrypt a blob produced by *encrypt_bytes*."""
    nonce, ct = blob[:12], blob[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, associated_data=None)


# ---------------------------------------------------------------------------
# High-level file helpers (used by the media blueprint)
# ---------------------------------------------------------------------------

def encrypt_file(src_path: str, dst_path: str) -> Tuple[str, dict]:
    """Read *src_path*, encrypt, write to *dst_path*.

    Returns:
        (wrapped_key, metadata_dict)
    """
    t0 = time.perf_counter()
    with open(src_path, "rb") as f:
        plaintext = f.read()

    file_key = generate_file_key()
    ciphertext = encrypt_bytes(plaintext, file_key)

    with open(dst_path, "wb") as f:
        f.write(ciphertext)

    wrapped = wrap_key(file_key)
    elapsed = time.perf_counter() - t0

    meta = {
        "original_size": len(plaintext),
        "encrypted_size": len(ciphertext),
        "encryption_time_s": round(elapsed, 4),
    }
    return wrapped, meta


def decrypt_file(src_path: str, dst_path: str, wrapped_key: str) -> dict:
    """Read encrypted *src_path*, decrypt, write to *dst_path*.

    Returns metadata dict.
    """
    t0 = time.perf_counter()
    file_key = unwrap_key(wrapped_key)

    with open(src_path, "rb") as f:
        blob = f.read()

    plaintext = decrypt_bytes(blob, file_key)

    with open(dst_path, "wb") as f:
        f.write(plaintext)

    elapsed = time.perf_counter() - t0
    return {
        "decrypted_size": len(plaintext),
        "decryption_time_s": round(elapsed, 4),
    }
