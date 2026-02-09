"""Tests for the encryption module (AES-GCM + Fernet key wrapping)."""

import os
import tempfile
import pytest

# Set a stable Fernet master key before importing encryption module
os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="

from app.encryption import (
    generate_file_key,
    wrap_key,
    unwrap_key,
    encrypt_bytes,
    decrypt_bytes,
    encrypt_file,
    decrypt_file,
)


class TestKeyHelpers:
    def test_generate_key_length(self):
        key = generate_file_key()
        assert len(key) == 32  # 256 bits

    def test_wrap_unwrap_roundtrip(self):
        key = generate_file_key()
        wrapped = wrap_key(key)
        assert isinstance(wrapped, str)
        recovered = unwrap_key(wrapped)
        assert recovered == key


class TestEncryptDecryptBytes:
    def test_roundtrip_small(self):
        key = generate_file_key()
        data = b"Hello, SecureMedia!"
        ct = encrypt_bytes(data, key)
        assert ct != data
        pt = decrypt_bytes(ct, key)
        assert pt == data

    def test_roundtrip_large(self):
        key = generate_file_key()
        data = os.urandom(5 * 1024 * 1024)  # 5 MB
        ct = encrypt_bytes(data, key)
        pt = decrypt_bytes(ct, key)
        assert pt == data

    def test_wrong_key_fails(self):
        key1 = generate_file_key()
        key2 = generate_file_key()
        ct = encrypt_bytes(b"secret", key1)
        with pytest.raises(Exception):
            decrypt_bytes(ct, key2)

    def test_tampered_ciphertext_fails(self):
        key = generate_file_key()
        ct = encrypt_bytes(b"important data", key)
        tampered = bytearray(ct)
        tampered[-1] ^= 0xFF
        with pytest.raises(Exception):
            decrypt_bytes(bytes(tampered), key)


class TestEncryptDecryptFile:
    def test_file_roundtrip(self, tmp_path):
        src = tmp_path / "original.bin"
        enc = tmp_path / "encrypted.bin"
        dec = tmp_path / "decrypted.bin"

        original_data = os.urandom(1024 * 100)  # 100 KB
        src.write_bytes(original_data)

        wrapped_key, meta = encrypt_file(str(src), str(enc))

        assert enc.exists()
        assert meta["original_size"] == len(original_data)
        assert meta["encrypted_size"] > len(original_data)  # nonce + tag overhead
        assert meta["encryption_time_s"] >= 0

        dec_meta = decrypt_file(str(enc), str(dec), wrapped_key)
        assert dec.read_bytes() == original_data
        assert dec_meta["decrypted_size"] == len(original_data)

    def test_file_roundtrip_empty(self, tmp_path):
        src = tmp_path / "empty.bin"
        enc = tmp_path / "empty_enc.bin"
        dec = tmp_path / "empty_dec.bin"
        src.write_bytes(b"")

        wrapped_key, meta = encrypt_file(str(src), str(enc))
        decrypt_file(str(enc), str(dec), wrapped_key)
        assert dec.read_bytes() == b""
