from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes
import base64
import os

def encrypt_markdown(file_path, password):
    with open(file_path, 'r', encoding='utf-8') as file:
        markdown_content = file.read()

    salt = get_random_bytes(16)
    key = PBKDF2(password, salt, dkLen=32)

    iv = get_random_bytes(AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct_bytes = cipher.encrypt(pad(markdown_content.encode(), AES.block_size))

    encrypted_content = base64.b64encode(salt + iv + ct_bytes).decode('utf-8')
    return encrypted_content

def decrypt_markdown(file_path, password):
    with open(file_path, 'r', encoding='utf-8') as file:
        encrypted_content = base64.b64decode(file.read())

    salt = encrypted_content[:16]
    iv = encrypted_content[16:32]
    ct_bytes = encrypted_content[32:]

    key = PBKDF2(password, salt, dkLen=32)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted_content = unpad(cipher.decrypt(ct_bytes), AES.block_size).decode('utf-8')
    return decrypted_content

def main():
    while True:
        print("\nMenu:")
        print("1. Encrypt a Markdown file")
        print("2. Decrypt a Markdown file")
        print("3. Exit")
        choice = input("Enter your choice (1/2/3): ")

        if choice == '1':
            file_path = input("Enter the full path of the Markdown file to encrypt: ")
            password = input("Enter the password for encryption: ")
            if not os.path.exists(file_path):
                print("File not found. Please check the path and try again.")
                continue

            encrypted_content = encrypt_markdown(file_path, password)
            encrypted_file_path = os.path.join(os.path.dirname(file_path), f"Encrypted_{os.path.basename(file_path)}")
            with open(encrypted_file_path, 'w', encoding='utf-8') as file:
                file.write(encrypted_content)

            print(f"Encrypted content saved to {encrypted_file_path}")

        elif choice == '2':
            file_path = input("Enter the full path of the encrypted Markdown file to decrypt: ")
            password = input("Enter the password for decryption: ")
            if not os.path.exists(file_path):
                print("File not found. Please check the path and try again.")
                continue

            try:
                decrypted_content = decrypt_markdown(file_path, password)
                decrypted_file_path = os.path.join(os.path.dirname(file_path), f"Decrypted_{os.path.basename(file_path)}")
                with open(decrypted_file_path, 'w', encoding='utf-8') as file:
                    file.write(decrypted_content)

                print(f"Decrypted content saved to {decrypted_file_path}")
            except (ValueError, KeyError):
                print("Decryption failed. Wrong password or corrupted file.")

        elif choice == '3':
            print("Exiting program.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()
