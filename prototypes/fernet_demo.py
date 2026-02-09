from cryptography.fernet import Fernet

def encrypt_file(input_path: str, output_path: str, key_path: str) -> None:
    with open(input_path, "rb") as f:
        data = f.read()

    key = Fernet.generate_key()
    fernet = Fernet(key)
    token = fernet.encrypt(data)

    with open(output_path, "wb") as f:
        f.write(token)

    with open(key_path, "wb") as f:
        f.write(key)


def decrypt_file(input_path: str, output_path: str, key_path: str) -> None:
    with open(key_path, "rb") as f:
        key = f.read()

    fernet = Fernet(key)

    with open(input_path, "rb") as f:
        token = f.read()

    data = fernet.decrypt(token)

    with open(output_path, "wb") as f:
        f.write(data)


if __name__ == "__main__":
    # Example usage (adjust paths as needed)
    encrypt_file("sample_input.bin", "sample_encrypted.fernet", "sample_key.fernet")
    decrypt_file("sample_encrypted.fernet", "sample_decrypted.bin", "sample_key.fernet")
