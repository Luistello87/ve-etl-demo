# run_etl.py
import sqlite3
import csv
import os
import struct
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import paramiko

# Configurations (can be overridden via environment variables)
DB_FILE = os.getenv("ETL_DB_FILE", "local_data.db")
PUBLIC_KEY_FILE = os.getenv("ETL_PUBLIC_KEY", "public_key.pem")
OUTPUT_CSV = "extract_data.csv"
ENCRYPTED_FILE = "extract_data.csv.enc"

# SFTP configurations (configure these for laptop-to-laptop)
SFTP_HOST = os.getenv("SFTP_HOST", "localhost")
SFTP_PORT = int(os.getenv("SFTP_PORT", "22"))
SFTP_USER = os.getenv("SFTP_USER", "your_username")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD", "")  # Or use SSH key authentication
SFTP_REMOTE_PATH = os.getenv("SFTP_REMOTE_PATH", "./extract_data.csv.enc")

# Character map to normalize accents (mimicking production transform.py)
ACCENT_MAP = str.maketrans(
    "àáâãäåæçèéêëìíîïðñòóôõöùúûüýþÿÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖÙÚÛÜÝÞ",
    "aaaaaæceeeeiiiiðnooooouuuuyþyAAAAAAAACEEEEIIIIÐNOOOOOUUUUYÞ"
)

def transform_row(row):
    """Normalize accented characters and uppercase string values."""
    new_row = []
    for val in row:
        if isinstance(val, str):
            val = val.translate(ACCENT_MAP).upper()
        new_row.append(val)
    return new_row

def extract_and_transform():
    print("Step 1: Connecting to Database and extracting active records...")
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"Database file not found: {DB_FILE}. Please run setup_db.py first.")
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Extract only ACTIVE death records
    cursor.execute("""
        SELECT first_name, last_name, gender, address, city, province, death_date 
        FROM vital_events 
        WHERE status = 'ACTIVE'
    """)
    rows = cursor.fetchall()
    
    print(f" - Extracted {len(rows)} records. Processing transformations...")
    
    # Write to local CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Write headers
        writer.writerow(["FIRST_NAME", "LAST_NAME", "GENDER", "ADDRESS", "CITY", "PROVINCE", "DEATH_DATE"])
        
        # Apply transformation and write rows
        for row in rows:
            transformed = transform_row(row)
            writer.writerow(transformed)
            
    conn.close()
    print(f" - Plaintext CSV file written successfully: {OUTPUT_CSV}")

def encrypt_file():
    print("Step 2: Performing Asymmetric Hybrid Encryption (RSA + AES-GCM)...")
    if not os.path.exists(PUBLIC_KEY_FILE):
        raise FileNotFoundError(f"Public key not found: {PUBLIC_KEY_FILE}. Run generate_keys.py first.")
        
    # Read plaintext file
    with open(OUTPUT_CSV, "rb") as f:
        plaintext_data = f.read()
        
    # 1. Load RSA public key
    with open(PUBLIC_KEY_FILE, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())
        
    # 2. Generate a random temporary AES symmetric key (32 bytes / 256-bit)
    aes_key = AESGCM.generate_key(bit_length=256)
    
    # 3. Encrypt the file using AES-GCM
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    encrypted_data = aesgcm.encrypt(nonce, plaintext_data, None)
    
    # 4. Encrypt the AES key with the RSA Public Key (asymmetric)
    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # 5. Pack encrypted key size, encrypted key, nonce, and encrypted payload
    with open(ENCRYPTED_FILE, "wb") as f:
        # Write 4-byte big-endian integer for key length
        f.write(struct.pack(">I", len(encrypted_key)))
        f.write(encrypted_key)
        f.write(nonce)
        f.write(encrypted_data)
        
    print(f" - Encrypted file saved as: {ENCRYPTED_FILE}")
    
    # Clean up plaintext file to maintain zero-plaintext footprint
    if os.path.exists(OUTPUT_CSV):
        os.remove(OUTPUT_CSV)
        print(" - Securely cleaned up temporary plaintext CSV file.")

def upload_via_sftp():
    print(f"Step 3: Transferring encrypted file via SFTP to host: {SFTP_HOST}...")
    if not os.path.exists(ENCRYPTED_FILE):
        raise FileNotFoundError(f"Encrypted payload not found: {ENCRYPTED_FILE}")
        
    # Initialize SSH/SFTP client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Connect to SFTP server
        ssh.connect(
            hostname=SFTP_HOST,
            port=SFTP_PORT,
            username=SFTP_USER,
            password=SFTP_PASSWORD
        )
        
        sftp = ssh.open_sftp()
        print(f" - Connected! Uploading {ENCRYPTED_FILE} to {SFTP_REMOTE_PATH}...")
        sftp.put(ENCRYPTED_FILE, SFTP_REMOTE_PATH)
        sftp.close()
        print(" - SFTP Transfer Completed successfully!")
    except Exception as e:
        print(f" [ERROR] SFTP Upload Failed: {e}")
        print("   (Ensure your destination SFTP configuration and host firewall are set up correctly)")
    finally:
        ssh.close()

def main():
    try:
        extract_and_transform()
        encrypt_file()
        upload_via_sftp()
        print("\n[SUCCESS] ETL process complete!")
    except Exception as e:
        print(f"\n[ERROR] Error during ETL execution: {e}")

if __name__ == "__main__":
    main()
