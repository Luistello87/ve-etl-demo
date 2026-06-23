# run_etl.py
import sqlite3
import csv
import os
import struct
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import paramiko

def load_env():
    """Manually parse a local .env file in the current directory if it exists."""
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v

load_env()

# Configurations (can be overridden via environment variables or .env)
DB_TYPE = os.getenv("DB_TYPE", "oracle") # "oracle", "dev_oracle", or "sqlite"
DB_FILE = os.getenv("ETL_DB_FILE", "local_data.db") # used if DB_TYPE is "sqlite"
PUBLIC_KEY_FILE = os.getenv("ETL_PUBLIC_KEY", "public_key.pem")
OUTPUT_CSV = "extract_data.csv"
ENCRYPTED_FILE = "extract_data.csv.enc"

# Local Oracle Connection Configs (DB_TYPE = "oracle")
ORACLE_USER = os.getenv("ORACLE_USER", "ve_etl_user")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "Etl_Pass1")
ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "FREEPDB1")

# Dev Environment Oracle Connection Configs (DB_TYPE = "dev_oracle")
DEV_ORACLE_USER = os.getenv("DEV_ORACLE_USER", "ve_etl_user")
DEV_ORACLE_PASSWORD = os.getenv("DEV_ORACLE_PASSWORD", "Etl_Pass1")
DEV_ORACLE_HOST = os.getenv("DEV_ORACLE_HOST", "dev-db-server.yourdomain.com")
DEV_ORACLE_PORT = os.getenv("DEV_ORACLE_PORT", "1521")
DEV_ORACLE_SERVICE = os.getenv("DEV_ORACLE_SERVICE", "DEV_VITAL_EVENTS")

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
    db_mode = DB_TYPE.lower()
    
    if db_mode in ("oracle", "dev_oracle"):
        # Select correct configurations based on mode
        if db_mode == "oracle":
            u, p, h, pt, s = ORACLE_USER, ORACLE_PASSWORD, ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE
            print(f"Step 1: Connecting to Local Oracle Database ({h}:{pt}/{s}) and extracting records...")
        else:
            u, p, h, pt, s = DEV_ORACLE_USER, DEV_ORACLE_PASSWORD, DEV_ORACLE_HOST, DEV_ORACLE_PORT, DEV_ORACLE_SERVICE
            print(f"Step 1: Connecting to Dev Environment Oracle Database ({h}:{pt}/{s}) and extracting records...")
            
        try:
            import oracledb
        except ImportError:
            raise ImportError(
                "The 'oracledb' package is required to connect to Oracle. "
                "Please run: pip install oracledb"
            )
            
        dsn = oracledb.makedsn(h, pt, service_name=s)
        conn = oracledb.connect(user=u, password=p, dsn=dsn)
        cursor = conn.cursor()
        
        # Extract from the vital events table
        cursor.execute("""
            SELECT first_name, last_name, gender, address, city, province, death_date 
            FROM vital_events_death
        """)
        rows = cursor.fetchall()
        
    elif db_mode == "sqlite":
        print(f"Step 1: Connecting to SQLite Database ({DB_FILE}) and extracting active records...")
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
    else:
        raise ValueError(f"Unsupported DB_TYPE: {DB_TYPE}. Choose 'oracle', 'dev_oracle', or 'sqlite'.")

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
