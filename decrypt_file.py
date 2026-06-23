# decrypt_file.py
import os
import struct
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTED_FILE = "extract_data.csv.enc"
PRIVATE_KEY_FILE = "private_key.pem"
DECRYPTED_CSV = "decrypted_data.csv"

def decrypt_payload():
    print("Step 1: Reading encrypted payload and private key...")
    if not os.path.exists(ENCRYPTED_FILE):
        raise FileNotFoundError(f"Encrypted file not found: {ENCRYPTED_FILE}")
    if not os.path.exists(PRIVATE_KEY_FILE):
        raise FileNotFoundError(f"Private key file not found: {PRIVATE_KEY_FILE}")
        
    # 1. Load RSA Private Key
    with open(PRIVATE_KEY_FILE, "rb") as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
        
    # 2. Parse the packed binary payload
    with open(ENCRYPTED_FILE, "rb") as f:
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
        
    print(f"🎉 Decryption Successful! File recovered at: {DECRYPTED_CSV}")
    print("Sample Output Content:")
    print("-" * 50)
    print(decrypted_bytes.decode("utf-8")[:500])  # Print first 500 chars
    print("-" * 50)

if __name__ == "__main__":
    try:
        decrypt_payload()
    except Exception as e:
        print(f"❌ Decryption Failed: {e}")
