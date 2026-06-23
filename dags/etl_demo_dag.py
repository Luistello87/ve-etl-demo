# dags/etl_demo_dag.py
from datetime import datetime, timedelta
import os
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

# Dynamic filenames following convention: KPVSB<Monddyyyy>.txt (e.g. KPVSBJan102020.txt)
def get_kpvsb_filenames():
    now = datetime.now()
    month = now.strftime("%b")
    month_cap = month[0].upper() + month[1:].lower()
    date_str = f"{month_cap}{now.strftime('%d%Y')}"
    base_name = f"KPVSB{date_str}.txt"
    return base_name, os.path.join("/tmp", base_name), os.path.join("/tmp", base_name + ".enc")

# Generate paths
FILENAME, PLAINTEXT_FILE, ENCRYPTED_FILE = get_kpvsb_filenames()

# Accent character normalization map
ACCENT_MAP = str.maketrans(
    "àáâãäåæçèéêëìíîïðñòóôõöùúûüýþÿÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖÙÚÛÜÝÞ",
    "aaaaaæceeeeiiiiðnooooouuuuyþyAAAAAAAACEEEEIIIIÐNOOOOOUUUUYÞ"
)

def format_kpvsb_slash_date(dt):
    """Format date to MMM/dd/yyyy with Titlecase month (e.g., Jan/10/2020)"""
    month = dt.strftime("%b")
    month_cap = month[0].upper() + month[1:].lower()
    return f"{month_cap}/{dt.strftime('%d/%Y')}"

def extract_and_transform_task(**context):
    print("Connecting to Oracle Database using connection: 'oracle_demo'...")
    hook = OracleHook(oracle_conn_id="oracle_demo")
    
    # 1. Calculate KPVSB Date Window (18th of previous month to 17th of current month)
    run_date = context["data_interval_start"].date()
    first_of_current = run_date.replace(day=1)
    last_of_prev = first_of_current - timedelta(days=1)
    extract_start = last_of_prev.replace(day=18)
    extract_end = run_date.replace(day=17)
    
    print(f"Date window calculated: {extract_start} to {extract_end}")
    
    # 2. Run the SQL query matching KPVSB selection criteria (Page 4)
    sql = """
    SELECT DISTINCT 
        RG_DEATH.SURNAME, 
        RG_DEATH.FORENAME, 
        RG_DEATH.SEX, 
        RG_DEATH.DATE_OF_BIRTH, 
        RG_DEATH.DATE_OF_EVENT, 
        RG_DEATH.AGE, 
        RG_DEATH.RESIDENCE_ADDRESS, 
        RG_DEATH.RESIDENCE_CITY, 
        RG_DEATH.RESIDENCE_POSTAL_CODE, 
        RG_DEATH.BOOK_YEAR, 
        RG_DEATH.REGISTRATION_NUMBER
    FROM
        RG_DEATH
    WHERE
        TRUNC(RG_DEATH.REGISTRATION_DATE) BETWEEN :extract_start AND :extract_end
        AND RG_DEATH.STATUS_CODE = 'A'
        AND RG_DEATH.BOOK_YEAR||RG_DEATH.REGISTRATION_NUMBER NOT IN 
        (
            SELECT d.BOOK_YEAR||d.REGISTRATION_NUMBER 
            FROM REGISTRATION_INDICATOR d, RG_DEATH r 
            WHERE d.BOOK_YEAR = r.BOOK_YEAR 
              AND d.REGISTRATION_NUMBER = r.REGISTRATION_NUMBER 
              AND d.STATUS_CD = 'A' 
              AND d.EVENT_TYPE = 30 
              AND d.ACCESS_LEVEL = 9
        )
    ORDER BY RG_DEATH.SURNAME ASC
    """
    
    conn = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(sql, extract_start=extract_start, extract_end=extract_end)
    rows = cursor.fetchall()
    
    print(f"Extracted {len(rows)} records. Building KVPVSB file structure (Page 5 & 6)...")
    
    file_lines = []
    
    # Header Row 1: The date the extract was created (MMMDdYYYY, e.g. Jan102020)
    now = datetime.now()
    now_month = now.strftime("%b")
    now_month_cap = now_month[0].upper() + now_month[1:].lower()
    file_lines.append(f"{now_month_cap}{now.strftime('%d%Y')}")
    
    # Header Row 2: Always "3"
    file_lines.append("3")
    
    # Header Row 3: First date of the data being extracted (MMM/dd/yyyy)
    file_lines.append(format_kpvsb_slash_date(extract_start))
    
    # Header Row 4: Last date of the data being extracted (MMM/dd/yyyy)
    file_lines.append(format_kpvsb_slash_date(extract_end))
    
    # Header Row 5: Always "35 ORG"
    file_lines.append("35 ORG")
    
    # Data Rows
    for row in rows:
        three = "3"
        surname = (row[0] or "").upper().translate(ACCENT_MAP)
        
        # Forename rule: Up to the first period plus 1 character (Sam.Fred -> Sam.F)
        forename_raw = row[1] or ""
        dot_idx = forename_raw.find(".")
        if dot_idx >= 0:
            forename = forename_raw[:dot_idx + 2].upper()
        else:
            forename = forename_raw[:1].upper()
        forename = forename.translate(ACCENT_MAP)
        
        sex = row[2] or " "
        age = str(row[5]) if row[5] is not None else " "
        doe = row[4].strftime("%m-%d-%Y") if row[4] else " "
        
        addr = (row[6] or "").rstrip().upper().translate(ACCENT_MAP)
        pc = (row[8] or "").upper().replace(" ", "").replace("-", "")
        city = (row[7] or "").rstrip().upper().translate(ACCENT_MAP)
        dob = row[3].strftime("%b-%d").upper() if row[3] else " "
        
        # Book year and Registration number layout: Book_year-05-Registration_Number (padded to 6 digits)
        if row[9] is not None and row[10] is not None:
            reg_info = f"{int(row[9])}-05-{int(row[10]):06d}"
        else:
            reg_info = " "
            
        fields = [three, surname, forename, sex, age, doe, addr, pc, city, dob, reg_info]
        file_lines.append("|".join(fields))
        
    # Footer Row: "<N> rows selected."
    file_lines.append(f"{len(rows)} rows selected.")
    
    # Write to temporary file, applying the 300 character line limit (Page 5)
    with open(PLAINTEXT_FILE, "w", newline="", encoding="utf-8") as f:
        for line in file_lines:
            f.write(line[:300] + "\n")
            
    cursor.close()
    conn.close()
    print(f"Plaintext file successfully written to: {PLAINTEXT_FILE}")

def encrypt_file_task(**context):
    print("Performing asymmetric hybrid encryption...")
    if not os.path.exists(PUBLIC_KEY_FILE):
        raise FileNotFoundError(
            f"Public key not found at '{PUBLIC_KEY_FILE}'. "
            "Please generate keys and copy public_key.pem to the /include folder."
        )
        
    with open(PLAINTEXT_FILE, "rb") as f:
        plaintext_data = f.read()
        
    with open(PUBLIC_KEY_FILE, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())
        
    aes_key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)
    encrypted_data = aesgcm.encrypt(nonce, plaintext_data, None)
    
    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    with open(ENCRYPTED_FILE, "wb") as f:
        f.write(struct.pack(">I", len(encrypted_key)))
        f.write(encrypted_key)
        f.write(nonce)
        f.write(encrypted_data)
        
    print(f"Encrypted file saved to: {ENCRYPTED_FILE}")
    
    if os.path.exists(PLAINTEXT_FILE):
        os.remove(PLAINTEXT_FILE)
        print("Cleaned up plaintext CSV file.")

def upload_via_sftp_task(**context):
    print("Connecting to SFTP server using connection: 'sftp_demo'...")
    if not os.path.exists(ENCRYPTED_FILE):
        raise FileNotFoundError(f"Encrypted payload not found at: {ENCRYPTED_FILE}")
        
    hook = SFTPHook(ftp_conn_id="sftp_demo")
    conn = hook.get_connection("sftp_demo")
    
    # Deliver the dynamic filename: KPVSB<Monddyyyy>.txt.enc
    remote_path = conn.extra_dejson.get("remote_path", f"./{FILENAME}.enc")
    
    print(f"Uploading {ENCRYPTED_FILE} to remote SFTP path: {remote_path}...")
    hook.store_file(remote_path, ENCRYPTED_FILE)
    
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
    description="KPVSB Vital Events ETL pipeline using UI Connections (Astronomer/Podman)",
    schedule_interval=None, # Trigger manually for demo
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["demo", "vital-events", "kpvsb"],
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
