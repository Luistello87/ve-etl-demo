# Standalone Asymmetric ETL Demo (SQLite -> RSA/AES-GCM -> SFTP)

This repository demonstrates the core logic of the Vital Events ETL engine in a simple, self-contained Python workflow. It extracts data from a local database, cleans/normalizes the records, encrypts the file using asymmetric public/private keys, and delivers the encrypted file over SFTP to a remote target.

---

## Project Structure

*   **`setup_db.py`**: Initializes and seeds a mock SQLite database (`local_data.db`) so you can run the pipeline without an Oracle instance.
*   **`generate_keys.py`**: Generates a 2048-bit RSA keypair:
    *   `public_key.pem`: Used by the sender to encrypt the payload.
    *   `private_key.pem`: Used by the recipient to decrypt the payload.
*   **`run_etl.py`**: Queries the database, cleans accented characters, generates a CSV, encrypts it, and uploads the file via SFTP.
*   **`decrypt_file.py`**: Rebuilds the plaintext CSV from the encrypted file using the private key.

---

## 1. Installation

Install the required Python packages on both laptops:

```bash
pip install cryptography paramiko oracledb
```

---

## 1.1 Database Configuration Options

By default, the script connects to your local seeded **Oracle** container database. You can customize the behavior by creating a `.env` file in the `ve_etl_demo` folder or setting environment variables before running `run_etl.py`:

*   **`DB_TYPE`**: Connection mode. Set to `"oracle"` (local Oracle, default), `"dev_oracle"` (remote Dev environment database), or `"sqlite"`.
*   **`ETL_DB_FILE`**: Path to SQLite database (default: `local_data.db`, used if `DB_TYPE="sqlite"`).

### Local Oracle Connection Configs (DB_TYPE = "oracle")
If you are running the database locally, the default values below match the seeded developer container:
*   `ORACLE_USER` (default: `"ve_etl_user"`)
*   `ORACLE_PASSWORD` (default: `"Etl_Pass1"`)
*   `ORACLE_HOST` (default: `"localhost"`)
*   `ORACLE_PORT` (default: `"1521"`)
*   `ORACLE_SERVICE` (default: `"FREEPDB1"`)

### Dev Environment Oracle Connection Configs (DB_TYPE = "dev_oracle")
Configure these to connect to your shared remote Dev Oracle database:
*   `DEV_ORACLE_USER` (default: `"ve_etl_user"`)
*   `DEV_ORACLE_PASSWORD` (default: `"Etl_Pass1"`)
*   `DEV_ORACLE_HOST` (default: `"dev-db-server.yourdomain.com"`)
*   `DEV_ORACLE_PORT` (default: `"1521"`)
*   `DEV_ORACLE_SERVICE` (default: `"DEV_VITAL_EVENTS"`)

---

## 2. Set Up Laptop B (The Receiver / SFTP Server)

Laptop B must act as the SFTP host to receive the file. On Windows, you can enable the built-in OpenSSH server:

1.  Open an **Administrator PowerShell** on Laptop B.
2.  Install the OpenSSH Server:
    ```powershell
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    ```
3.  Start the SSH/SFTP service and configure it to run automatically:
    ```powershell
    Start-Service sshd
    Set-Service -Name sshd -StartupType 'Automatic'
    ```
4.  Allow Port 22 in the Windows Defender Firewall:
    ```powershell
    New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH SSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
    ```
5.  Find Laptop B's Local IP Address:
    ```powershell
    ipconfig
    ```
    *Look for the IPv4 Address under your active Wi-Fi or Ethernet adapter (e.g., `192.168.1.50`).*

---

## 3. Run the Demo (Laptop-to-Laptop)

### Step 1: Generate Keypair
On **Laptop B (Receiver)**, run:
```bash
python generate_keys.py
```
This generates `private_key.pem` and `public_key.pem`.
*   **Keep `private_key.pem` secure on Laptop B.**
*   **Send `public_key.pem` to Laptop A (Sender)** (via email, USB, or chat).

### Step 2: Initialize Database & Run ETL
On **Laptop A (Sender)**, place the `public_key.pem` in the project directory, then run:

1.  Create and seed the database:
    ```bash
    python setup_db.py
    ```
2.  Configure environment variables for the SFTP target (Laptop B) and execute the ETL:
    *   **Windows (Command Prompt):**
        ```cmd
        set SFTP_HOST=192.168.1.50
        set SFTP_USER=LaptopB_Username
        set SFTP_PASSWORD=LaptopB_Password
        set SFTP_REMOTE_PATH=C:/Users/LaptopB_Username/Desktop/extract_data.csv.enc
        python run_etl.py
        ```
    *   **Windows (PowerShell):**
        ```powershell
        $env:SFTP_HOST="192.168.1.50"
        $env:SFTP_USER="LaptopB_Username"
        $env:SFTP_PASSWORD="LaptopB_Password"
        $env:SFTP_REMOTE_PATH="C:/Users/LaptopB_Username/Desktop/extract_data.csv.enc"
        python run_etl.py
        ```
    *   **Mac/Linux:**
        ```bash
        SFTP_HOST="192.168.1.50" SFTP_USER="LaptopB_Username" SFTP_PASSWORD="LaptopB_Password" SFTP_REMOTE_PATH="/home/username/Desktop/extract_data.csv.enc" python run_etl.py
        ```

### Step 3: Decrypt the File
Once the SFTP transfer completes, `extract_data.csv.enc` will appear on Laptop B's desktop. On **Laptop B**, run:
```bash
python decrypt_file.py
```
This will read the encrypted file and create `decrypted_data.csv` showing the transformed, uppercase data with accents removed (e.g., `RENEE BELANGER`).

---

## 4. Run the Demo (Local Single-Machine Test)

You can test the entire pipeline locally on a single machine by using `localhost` for SFTP. Ensure the SSH Server is running on your machine:

```powershell
# 1. Generate keys
python generate_keys.py

# 2. Seed database
python setup_db.py

# 3. Configure environment and run ETL
$env:SFTP_HOST="localhost"
$env:SFTP_USER="your_windows_username"
$env:SFTP_PASSWORD="your_windows_password"
$env:SFTP_REMOTE_PATH="C:/Users/your_windows_username/Desktop/extract_data.csv.enc"
python run_etl.py

# 4. Decrypt the file
python decrypt_file.py
```

---

## 5. Push to GitHub

To save this codebase into a new repository on your GitHub account:

### Option A: Using the GitHub CLI (`gh`)
If you have the `gh` CLI tool installed and authenticated:
```bash
git init
git add .
git commit -m "Initial commit of standalone ETL demo"
gh repo create ve-etl-demo --public --source=. --remote=origin --push
```

### Option B: Using the GitHub Web Interface
1.  Go to [github.com](https://github.com/) and create a new **public** repository named `ve-etl-demo` (leave "Initialize this repository with..." options unchecked).
2.  Run the following commands in your local directory:
    ```bash
    git init
    git add .
    git commit -m "Initial commit of standalone ETL demo"
    git branch -M main
    git remote add origin https://github.com/YOUR_GITHUB_USERNAME/ve-etl-demo.git
    git push -u origin main
    ```
