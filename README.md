# Astronomer Apache Airflow ETL Demo (Oracle -> RSA/AES-GCM -> SFTP)

This repository replicates the core Vital Events ETL workflow as a containerized Apache Airflow project running on **Astronomer CLI** and **Podman**.

---

## Project Structure

*   **`Dockerfile`**: Standard Astro Runtime image extender.
*   **`requirements.txt`**: Container library dependencies, including Oracle and SFTP providers.
*   **`dags/etl_demo_dag.py`**: The core ETL pipeline DAG (`ve_etl_demo_pipeline`) using `OracleHook` and `SFTPHook`.
*   **`dags/generate_keys_dag.py`**: A helper DAG (`ve_generate_keys_helper`) to generate the RSA keypair inside the mounted `/include` folder.
*   **`decrypt_file.py`**: The standalone decryption script to run on Laptop B.

---

## 1. Setup & Installation

### Step 1: Install Astronomer CLI
Download and install the Astronomer CLI (`astro`) on your laptop:
*   **Windows (PowerShell):**
    ```powershell
    iex (iwr -UseBasicParsing https://astronomer.io/install.ps1)
    ```
*   **macOS (Homebrew):**
    ```bash
    brew install astronomer/tap/astro
    ```

### Step 2: Configure Astronomer to use Podman
Since you are using Podman as your container engine, you must set an environment variable before starting the stack:
*   **Windows (PowerShell):**
    ```powershell
    $env:ASTRO_CONTAINER_ENGINE="podman"
    ```
*   **Windows (Command Prompt):**
    ```cmd
    set ASTRO_CONTAINER_ENGINE=podman
    ```
*   **macOS / Linux:**
    ```bash
    export ASTRO_CONTAINER_ENGINE=podman
    ```

---

## 2. Start the Airflow Stack

Navigate to the project directory and run:
```bash
astro dev start
```
This command spins up the Airflow webserver, scheduler, and database containers inside Podman. Once completed, access the Airflow UI at:
*   **URL:** [http://localhost:8080](http://localhost:8080)
*   **Credentials:** `admin` / `admin`

To stop the environment later, run `astro dev stop`.

---

## 3. Configure Connections in the Airflow UI

To decouple database/SFTP credentials from code, you must configure two connections in the Airflow Web UI:

### Connection 1: Oracle Database (`oracle_demo`)
1.  In the Airflow Web UI, navigate to **Admin -> Connections** and click **+** to add a new connection.
2.  Set the following fields:
    *   **Connection Id:** `oracle_demo`
    *   **Connection Type:** `Oracle`
    *   **Host:** `host.containers.internal` *(This special hostname allows the Podman container to connect to port 1521 on your host machine)*
    *   **Port:** `1521`
    *   **Schema/Service Name:** `FREEPDB1`
    *   **Login/Username:** `ve_etl_user`
    *   **Password:** `Etl_Pass1`
3.  Click **Save**.

### Connection 2: SFTP Server Target (`sftp_demo`)
1.  Navigate to **Admin -> Connections** and click **+**.
2.  Set the following fields:
    *   **Connection Id:** `sftp_demo`
    *   **Connection Type:** `SFTP`
    *   **Host:** IP address of Laptop B (e.g., `192.168.1.50` or `host.containers.internal` for local testing)
    *   **Port:** `22`
    *   **Login/Username:** SSH username of Laptop B
    *   **Password:** SSH password of Laptop B
    *   **Extra:** `{"remote_path": "C:/Users/Username/Desktop/extract_data.csv.enc"}` *(This defines the destination path on Laptop B)*
3.  Click **Save**.

---

## 4. Run the Pipeline

### Step 1: Generate Keypair
1.  In the Airflow UI, find the **`ve_generate_keys_helper`** DAG.
2.  Unpause the DAG and click the **Play** button (Trigger DAG).
3.  This writes `public_key.pem` and `private_key.pem` into the `include/` directory on your laptop (which mounts dynamically to the container).
4.  **Send the `private_key.pem` file to Laptop B (Receiver).**

### Step 2: Trigger the ETL
1.  Ensure Laptop B is running its SSH/SFTP server.
2.  In the Airflow UI, find the **`ve_etl_demo_pipeline`** DAG.
3.  Unpause and **Trigger** the DAG.
4.  Monitor the task execution boxes: `extract_and_transform` -> `encrypt_file` -> `upload_via_sftp`.

### Step 3: Decrypt on Laptop B
Once the file `extract_data.csv.enc` appears on Laptop B, place it in the same directory as `decrypt_file.py` and `private_key.pem`, then run:
```bash
python decrypt_file.py
```
This recovers the transformed uppercase vital events records back to `decrypted_data.csv`.
