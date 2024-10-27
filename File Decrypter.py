import os
import sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import base64
import json

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

def decrypt_files():
    # Get input directory path
    input_dir = input("Enter the directory containing encrypted files: ").strip()
    if not os.path.exists(input_dir):
        print("Error: Input directory does not exist!")
        sys.exit(1)

    # Get password
    password = input("Enter decryption password: ").strip()
    if not password:
        print("Error: Password cannot be empty!")
        sys.exit(1)

    try:
        # Find all encrypted files
        encrypted_files = sorted([f for f in os.listdir(input_dir) if f.endswith('.enc')])
        if not encrypted_files:
            print("Error: No encrypted files found in the directory!")
            sys.exit(1)

        # Read the first file to get metadata
        with open(os.path.join(input_dir, encrypted_files[0]), 'r', encoding='utf-8') as f:
            first_chunk = json.load(f)

        metadata = first_chunk['metadata']
        if not metadata:
            print("Error: Metadata not found in the first chunk!")
            sys.exit(1)

        # Extract metadata
        total_chunks = metadata['total_chunks']
        salt = base64.b64decode(metadata['salt'])
        nonce = base64.b64decode(metadata['nonce'])
        original_filename = metadata['original_filename']

        # Generate key from password
        key = generate_key(password, salt)

        # Create AESGCM cipher
        aesgcm = AESGCM(key)

        # Read and combine all chunks
        ciphertext = bytearray()
        for i in range(total_chunks):
            chunk_file = os.path.join(input_dir, f'chunk_{i:05d}.enc')
            
            if not os.path.exists(chunk_file):
                print(f"Error: Missing chunk file {chunk_file}")
                sys.exit(1)

            with open(chunk_file, 'r', encoding='utf-8') as f:
                chunk_data = json.load(f)
                if chunk_data['chunk_index'] != i:
                    print(f"Error: Chunk index mismatch in {chunk_file}")
                    sys.exit(1)
                chunk = base64.b64decode(chunk_data['data'])
                ciphertext.extend(chunk)

        try:
            # Decrypt the combined data
            plaintext = aesgcm.decrypt(nonce, bytes(ciphertext), None)
            
            # Create output file
            output_file = os.path.join(os.path.dirname(input_dir), f'decrypted_{original_filename}')
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(plaintext.decode('utf-8'))

            print(f"\nDecryption successful!")
            print(f"Decrypted file saved as: {output_file}")

        except Exception as e:
            print(f"Error during decryption: {str(e)}")
            print("This could be due to an incorrect password or corrupted files.")
            sys.exit(1)

    except Exception as e:
        print(f"Error during decryption process: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    decrypt_files()
