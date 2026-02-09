import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_file(input_path: str, output_path: str, key_path: str) -> None:
    with open(input_path, "rb") as f:
        data = f.read()

    key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, associated_data=None)

    with open(output_path, "wb") as f:
        f.write(nonce + ciphertext)

    with open(key_path, "wb") as f:
        f.write(key)


def decrypt_file(input_path: str, output_path: str, key_path: str) -> None:
    with open(input_path, "rb") as f:
        blob = f.read()

    nonce, ciphertext = blob[:12], blob[12:]

    with open(key_path, "rb") as f:
        key = f.read()

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)

    with open(output_path, "wb") as f:
        f.write(plaintext)


if __name__ == "__main__":
    # Example usage (adjust paths as needed)
    encrypt_file("sample_input.bin", "sample_encrypted.bin", "sample_key.bin")
    decrypt_file("sample_encrypted.bin", "sample_decrypted.bin", "sample_key.bin")
