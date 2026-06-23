# dags/generate_keys_dag.py
from datetime import datetime
import os
from airflow import DAG
from airflow.operators.python import PythonOperator
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

INCLUDE_DIR = "/usr/local/airflow/include"
PRIVATE_KEY_FILE = os.path.join(INCLUDE_DIR, "private_key.pem")
PUBLIC_KEY_FILE = os.path.join(INCLUDE_DIR, "public_key.pem")

def generate_keys_task(**context):
    print(f"Generating RSA asymmetric keypair (2048-bit) under {INCLUDE_DIR}...")
    
    # Ensure include dir exists
    os.makedirs(INCLUDE_DIR, exist_ok=True)
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Serialize public key
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Write to files
    with open(PRIVATE_KEY_FILE, "wb") as f:
        f.write(private_pem)
    with open(PUBLIC_KEY_FILE, "wb") as f:
        f.write(public_pem)
        
    print(f"Keys successfully created:")
    print(f" - Private Key: {PRIVATE_KEY_FILE}")
    print(f" - Public Key:  {PUBLIC_KEY_FILE}")

with DAG(
    dag_id="ve_generate_keys_helper",
    description="Helper DAG to generate RSA asymmetric keys in include folder",
    schedule_interval=None, # Manual trigger only
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["helper", "security"],
) as dag:

    t_keygen = PythonOperator(
        task_id="generate_asymmetric_keys",
        python_callable=generate_keys_task,
    )
