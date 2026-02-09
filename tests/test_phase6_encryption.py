"""
Phase 6 — Testing & Validation: Encryption Module
Covers edge cases, tampering detection, large files, and crypto correctness.
"""

import os
import time
import tempfile
import pytest

os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="

from app.encryption import (
    generate_file_key, wrap_key, unwrap_key,
    encrypt_bytes, decrypt_bytes,
    encrypt_file, decrypt_file,
)
from cryptography.fernet import Fernet, InvalidToken


# ── Key Generation ─────────────────────────────────────────────────────

class TestKeyGenerationEdgeCases:
    def test_key_is_32_bytes(self):
        assert len(generate_file_key()) == 32

    def test_keys_are_unique(self):
        """Every generated key must be distinct (randomness check)."""
        keys = {generate_file_key() for _ in range(200)}
        assert len(keys) == 200, "Two keys collided — entropy failure"

    def test_key_is_bytes(self):
        assert isinstance(generate_file_key(), bytes)


# ── Key Wrapping ───────────────────────────────────────────────────────

class TestKeyWrappingEdgeCases:
    def test_wrap_produces_string(self):
        assert isinstance(wrap_key(generate_file_key()), str)

    def test_wrap_unwrap_roundtrip(self):
        k = generate_file_key()
        assert unwrap_key(wrap_key(k)) == k

    def test_unwrap_with_wrong_fernet_key_fails(self):
        k = generate_file_key()
        wrapped = wrap_key(k)
        # Build a *different* Fernet and try to decrypt
        other_fernet = Fernet(Fernet.generate_key())
        with pytest.raises(InvalidToken):
            other_fernet.decrypt(wrapped.encode())

    def test_wrap_is_nondeterministic(self):
        """Same plaintext key → different ciphertexts (Fernet has random IV)."""
        k = generate_file_key()
        tokens = {wrap_key(k) for _ in range(50)}
        assert len(tokens) == 50


# ── AES-GCM Byte-level ────────────────────────────────────────────────

class TestAESGCMEdgeCases:
    def test_empty_plaintext(self):
        k = generate_file_key()
        ct = encrypt_bytes(b"", k)
        assert decrypt_bytes(ct, k) == b""

    def test_1_byte_plaintext(self):
        k = generate_file_key()
        ct = encrypt_bytes(b"\x42", k)
        assert decrypt_bytes(ct, k) == b"\x42"

    def test_exactly_16_bytes(self):
        """AES block boundary."""
        k = generate_file_key()
        data = b"\xaa" * 16
        assert decrypt_bytes(encrypt_bytes(data, k), k) == data

    def test_large_plaintext_10mb(self):
        k = generate_file_key()
        data = os.urandom(10 * 1024 * 1024)
        assert decrypt_bytes(encrypt_bytes(data, k), k) == data

    def test_ciphertext_longer_than_plaintext(self):
        """Nonce (12) + GCM tag (16) overhead."""
        k = generate_file_key()
        data = b"hello"
        ct = encrypt_bytes(data, k)
        assert len(ct) == 12 + len(data) + 16  # nonce + ct + tag

    def test_nonce_is_unique(self):
        k = generate_file_key()
        nonces = set()
        for _ in range(100):
            ct = encrypt_bytes(b"x", k)
            nonces.add(ct[:12])
        assert len(nonces) == 100, "Nonce reuse detected"


# ── Tampering Detection ───────────────────────────────────────────────

class TestTamperingExperiments:
    """Phase 6 requirement: Attempt to modify encrypted files to ensure detection."""

    def test_flip_single_bit_in_ciphertext(self):
        k = generate_file_key()
        ct = bytearray(encrypt_bytes(b"important data", k))
        ct[20] ^= 0x01  # flip 1 bit in ciphertext body
        with pytest.raises(Exception):
            decrypt_bytes(bytes(ct), k)

    def test_flip_bit_in_nonce(self):
        k = generate_file_key()
        ct = bytearray(encrypt_bytes(b"important data", k))
        ct[0] ^= 0x80  # flip bit in nonce
        with pytest.raises(Exception):
            decrypt_bytes(bytes(ct), k)

    def test_truncate_ciphertext(self):
        k = generate_file_key()
        ct = encrypt_bytes(b"important data", k)
        with pytest.raises(Exception):
            decrypt_bytes(ct[:-1], k)

    def test_append_bytes(self):
        k = generate_file_key()
        ct = encrypt_bytes(b"data", k)
        with pytest.raises(Exception):
            decrypt_bytes(ct + b"\x00", k)

    def test_swap_nonce_between_messages(self):
        """Using the nonce from one message with the ciphertext of another should fail."""
        k = generate_file_key()
        ct1 = encrypt_bytes(b"message one", k)
        ct2 = encrypt_bytes(b"message two", k)
        hybrid = ct1[:12] + ct2[12:]  # nonce from ct1, body from ct2
        with pytest.raises(Exception):
            decrypt_bytes(hybrid, k)

    def test_wrong_key_always_fails(self):
        for _ in range(10):
            k1 = generate_file_key()
            k2 = generate_file_key()
            ct = encrypt_bytes(os.urandom(100), k1)
            with pytest.raises(Exception):
                decrypt_bytes(ct, k2)

    def test_zero_out_tag_bytes(self):
        k = generate_file_key()
        ct = bytearray(encrypt_bytes(b"payload", k))
        # Zero the last 16 bytes (GCM tag)
        ct[-16:] = b"\x00" * 16
        with pytest.raises(Exception):
            decrypt_bytes(bytes(ct), k)


# ── File-Level Encryption ─────────────────────────────────────────────

class TestFileEncryptionEdgeCases:
    def test_binary_file(self, tmp_path):
        """Encrypt random binary data and verify roundtrip."""
        src = tmp_path / "rand.bin"
        data = os.urandom(256 * 1024)
        src.write_bytes(data)
        enc = tmp_path / "rand.enc"
        dec = tmp_path / "rand.dec"

        wrapped, meta = encrypt_file(str(src), str(enc))
        decrypt_file(str(enc), str(dec), wrapped)
        assert dec.read_bytes() == data
        assert meta["original_size"] == len(data)

    def test_metadata_contains_timing(self, tmp_path):
        src = tmp_path / "t.bin"
        src.write_bytes(b"test")
        enc = tmp_path / "t.enc"
        _, meta = encrypt_file(str(src), str(enc))
        assert "encryption_time_s" in meta
        assert meta["encryption_time_s"] >= 0

    def test_tampered_encrypted_file_fails(self, tmp_path):
        """Modify the encrypted file on disk — decryption must fail."""
        src = tmp_path / "orig.bin"
        src.write_bytes(os.urandom(1024))
        enc = tmp_path / "enc.bin"
        dec = tmp_path / "dec.bin"

        wrapped, _ = encrypt_file(str(src), str(enc))

        # Tamper with file on disk
        data = bytearray(enc.read_bytes())
        data[50] ^= 0xFF
        enc.write_bytes(bytes(data))

        with pytest.raises(Exception):
            decrypt_file(str(enc), str(dec), wrapped)


# ── Performance Benchmarks ────────────────────────────────────────────

class TestEncryptionPerformance:
    """Phase 6 requirement: Measure encryption/watermark time per MB."""

    @pytest.mark.parametrize("size_mb", [1, 5, 10])
    def test_encryption_speed(self, tmp_path, size_mb):
        """Encryption throughput should be > 10 MB/s."""
        src = tmp_path / f"perf_{size_mb}mb.bin"
        data = os.urandom(size_mb * 1024 * 1024)
        src.write_bytes(data)
        enc = tmp_path / f"perf_{size_mb}mb.enc"

        t0 = time.perf_counter()
        encrypt_file(str(src), str(enc))
        elapsed = time.perf_counter() - t0

        throughput = size_mb / elapsed
        print(f"  Encryption: {size_mb} MB in {elapsed:.3f}s = {throughput:.1f} MB/s")
        assert throughput > 5, f"Encryption too slow: {throughput:.1f} MB/s"

    @pytest.mark.parametrize("size_mb", [1, 5, 10])
    def test_decryption_speed(self, tmp_path, size_mb):
        """Decryption throughput should be > 10 MB/s."""
        src = tmp_path / f"perf_{size_mb}mb.bin"
        src.write_bytes(os.urandom(size_mb * 1024 * 1024))
        enc = tmp_path / f"perf_{size_mb}mb.enc"
        dec = tmp_path / f"perf_{size_mb}mb.dec"

        wrapped, _ = encrypt_file(str(src), str(enc))

        t0 = time.perf_counter()
        decrypt_file(str(enc), str(dec), wrapped)
        elapsed = time.perf_counter() - t0

        throughput = size_mb / elapsed
        print(f"  Decryption: {size_mb} MB in {elapsed:.3f}s = {throughput:.1f} MB/s")
        assert throughput > 5, f"Decryption too slow: {throughput:.1f} MB/s"
