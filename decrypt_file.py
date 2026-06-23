# decrypt_file.py
import os
import struct
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Path search order (checks current directory first, then include/ subdirectory)
ENCRYPTED_FILE = "extract_data.csv.enc"
PRIVATE_KEY_FILE = "private_key.pem"
DECRYPTED_CSV = "decrypted_data.csv"

def find_file(filename):
    """Checks current directory, then include/ subdirectory."""
    if os.path.exists(filename):
        return filename
    include_path = os.path.join("include", filename)
    if os.path.exists(include_path):
        return include_path
    return filename

def decrypt_payload():
    print("Step 1: Reading encrypted payload and private key...")
    encrypted_path = find_file(ENCRYPTED_FILE)
    private_key_path = find_file(PRIVATE_KEY_FILE)
    
    if not os.path.exists(encrypted_path):
        raise FileNotFoundError(f"Encrypted file not found: {encrypted_path} (checked current dir and include/)")
    if not os.path.exists(private_key_path):
        raise FileNotFoundError(f"Private key file not found: {private_key_path} (checked current dir and include/)")
        
    # 1. Load RSA Private Key
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
        
    # 2. Parse the packed binary payload
    with open(encrypted_path, "rb") as f:
        # Read the 4-byte key length
        key_len_bytes = f.read(4)
        if len(key_len_bytes) < 4:
            raise ValueError("Invalid encrypted file format (too short)")
        key_len = struct.unpack(">I", key_len_bytes)[0]
        
        # Read the encrypted AES key
        encrypted_key = f.read(key_len)
        
        # Read the 12-byte AES-GCM nonce
        nonce = f.read(12)
        
        # Read the remainder of the file as encrypted CSV payload
        encrypted_data = f.read()
        
    print("Step 2: Decrypting AES key using RSA Private Key...")
    # 3. Decrypt the AES key
    aes_key = private_key.decrypt(
        encrypted_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    print("Step 3: Decrypting payload using AES-GCM...")
    # 4. Decrypt the CSV payload
    aesgcm = AESGCM(aes_key)
    decrypted_bytes = aesgcm.decrypt(nonce, encrypted_data, None)
    
    # 5. Save the output
    with open(DECRYPTED_CSV, "wb") as f:
        f.write(decrypted_bytes)
        
    print(f"[SUCCESS] Decryption Successful! File recovered at: {DECRYPTED_CSV}")
    print("Sample Output Content:")
    print("-" * 50)
    print(decrypted_bytes.decode("utf-8")[:500])  # Print first 500 chars
    print("-" * 50)

if __name__ == "__main__":
    try:
        decrypt_payload()
    except Exception as e:
        print(f"[ERROR] Decryption Failed: {e}")
