# dags/etl_demo_dag.py
from datetime import datetime, timedelta
import os
import csv
import struct
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.oracle.hooks.oracle import OracleHook
from airflow.providers.sftp.hooks.sftp import SFTPHook
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Paths inside the Astro runtime container
INCLUDE_DIR = "/usr/local/airflow/include"
PUBLIC_KEY_FILE = os.path.join(INCLUDE_DIR, "public_key.pem")
PLAINTEXT_CSV = "/tmp/extract_data.csv"
ENCRYPTED_FILE = "/tmp/extract_data.csv.enc"

# Accent character normalization map
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

def extract_and_transform_task(**context):
    print("Connecting to Oracle Database using connection: 'oracle_demo'...")
    # Fetch connection hook
    hook = OracleHook(oracle_conn_id="oracle_demo")
    
    # Establish connection and run query
    conn = hook.get_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT first_name, last_name, gender, address, city, province, death_date 
        FROM vital_events_death
    """)
    rows = cursor.fetchall()
    
    print(f"Extracted {len(rows)} records. Processing transforms...")
    
    # Write to temporary plaintext CSV
    with open(PLAINTEXT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["FIRST_NAME", "LAST_NAME", "GENDER", "ADDRESS", "CITY", "PROVINCE", "DEATH_DATE"])
        for row in rows:
            transformed = transform_row(row)
            writer.writerow(transformed)
            
    cursor.close()
    conn.close()
    print(f"Plaintext CSV written successfully to: {PLAINTEXT_CSV}")

def encrypt_file_task(**context):
    print("Performing asymmetric hybrid encryption...")
    if not os.path.exists(PUBLIC_KEY_FILE):
        raise FileNotFoundError(
            f"Public key not found at '{PUBLIC_KEY_FILE}'. "
            "Please generate keys and copy public_key.pem to the /include folder."
        )
        
    with open(PLAINTEXT_CSV, "rb") as f:
        plaintext_data = f.read()
        
    # Load RSA Public Key
    with open(PUBLIC_KEY_FILE, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())
        
    # Generate temporary AES key & encrypt CSV data (AES-GCM)
    aes_key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)
    encrypted_data = aesgcm.encrypt(nonce, plaintext_data, None)
    
    # Encrypt AES key using RSA public key
    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # Pack key size, encrypted key, nonce, and encrypted payload
    with open(ENCRYPTED_FILE, "wb") as f:
        f.write(struct.pack(">I", len(encrypted_key)))
        f.write(encrypted_key)
        f.write(nonce)
        f.write(encrypted_data)
        
    print(f"Encrypted file saved to: {ENCRYPTED_FILE}")
    
    # Clean up plaintext file
    if os.path.exists(PLAINTEXT_CSV):
        os.remove(PLAINTEXT_CSV)
        print("Cleaned up plaintext CSV file.")

def upload_via_sftp_task(**context):
    print("Connecting to SFTP server using connection: 'sftp_demo'...")
    if not os.path.exists(ENCRYPTED_FILE):
        raise FileNotFoundError(f"Encrypted payload not found at: {ENCRYPTED_FILE}")
        
    # Initialize SFTPHook
    hook = SFTPHook(ftp_conn_id="sftp_demo")
    
    # Determine remote destination path (default to local folder inside SFTP account home)
    conn = hook.get_connection("sftp_demo")
    # Read custom remote path from connection extra field, or default to "./extract_data.csv.enc"
    remote_path = conn.extra_dejson.get("remote_path", "./extract_data.csv.enc")
    
    print(f"Uploading {ENCRYPTED_FILE} to remote SFTP path: {remote_path}...")
    hook.store_file(remote_path, ENCRYPTED_FILE)
    
    # Clean up encrypted local file
    if os.path.exists(ENCRYPTED_FILE):
        os.remove(ENCRYPTED_FILE)
        print("Cleaned up local encrypted file.")
    print("SFTP Transfer completed successfully!")


# DAG definition
default_args = {
    "owner": "ve-demo",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="ve_etl_demo_pipeline",
    default_args=default_args,
    description="Demo Vital Events ETL pipeline using UI Connections (Astronomer/Podman)",
    schedule_interval=None, # Trigger manually for demo
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["demo", "vital-events"],
) as dag:

    t_extract = PythonOperator(
        task_id="extract_and_transform",
        python_callable=extract_and_transform_task,
    )

    t_encrypt = PythonOperator(
        task_id="encrypt_file",
        python_callable=encrypt_file_task,
    )

    t_sftp = PythonOperator(
        task_id="upload_via_sftp",
        python_callable=upload_via_sftp_task,
    )

    t_extract >> t_encrypt >> t_sftp
