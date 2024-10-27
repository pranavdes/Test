import os
import sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import base64
import json
import secrets

def generate_key(password: str, salt: bytes) -> bytes:
    """Generate encryption key from password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return kdf.derive(password.encode())

def split_data(data: bytes, chunk_size: int) -> list:
    """Split data into chunks of specified size."""
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def encrypt_file():
    # Get input file path
    input_file = input("Enter the path to the HTML file to encrypt: ").strip()
    if not os.path.exists(input_file):
        print("Error: Input file does not exist!")
        sys.exit(1)

    # Get output directory
    output_dir = input("Enter the output directory path: ").strip()
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Get password
    password = input("Enter encryption password: ").strip()
    if not password:
        print("Error: Password cannot be empty!")
        sys.exit(1)

    try:
        # Read the input file
        with open(input_file, 'r', encoding='utf-8') as f:
            plaintext = f.read()

        # Generate salt and nonce
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)

        # Generate key from password
        key = generate_key(password, salt)

        # Create AESGCM cipher
        aesgcm = AESGCM(key)

        # Encrypt the data
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

        # Split the ciphertext into chunks (4KB - overhead for metadata)
        chunk_size = 3800  # Leaving room for metadata
        chunks = split_data(ciphertext, chunk_size)

        # Prepare metadata
        metadata = {
            'total_chunks': len(chunks),
            'salt': base64.b64encode(salt).decode('utf-8'),
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'original_filename': os.path.basename(input_file)
        }

        # Write chunks to files
        for i, chunk in enumerate(chunks):
            chunk_file = os.path.join(output_dir, f'chunk_{i:05d}.enc')
            chunk_data = {
                'metadata': metadata if i == 0 else None,
                'chunk_index': i,
                'data': base64.b64encode(chunk).decode('utf-8')
            }
            
            with open(chunk_file, 'w', encoding='utf-8') as f:
                json.dump(chunk_data, f)

        print(f"\nEncryption complete! {len(chunks)} files created in {output_dir}")
        print("Please keep your password safe. You'll need it for decryption.")

    except Exception as e:
        print(f"Error during encryption: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    encrypt_file()
