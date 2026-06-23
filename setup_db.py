# setup_db.py
import sqlite3
import os

DB_FILE = "local_data.db"

def init_db():
    print(f"Initializing database: {DB_FILE}")
    
    # Remove existing db if running again
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create mock Vital Events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vital_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            gender TEXT,
            address TEXT,
            city TEXT,
            province TEXT,
            death_date TEXT,
            status TEXT
        )
    """)
    
    # Seed mock records (some with accents for testing)
    mock_records = [
        ("Jean", "Tremblay", "M", "123 Main St", "Toronto", "ON", "2026-04-15", "ACTIVE"),
        ("Renée", "Bélanger", "F", "456 Oak Ave", "Ottawa", "ON", "2026-04-20", "ACTIVE"),
        ("François", "Côté", "M", "789 Elm Rd", "Hamilton", "ON", "2026-05-01", "ACTIVE"),
        ("Marie", "Gagnon", "F", "22 Pine Blvd", "London", "ON", "2026-05-10", "ACTIVE"),
        ("John", "Doe", "M", "99 Spruce Ln", "Sudbury", "ON", "2026-05-18", "INACTIVE")
    ]
    
    cursor.executemany("""
        INSERT INTO vital_events (first_name, last_name, gender, address, city, province, death_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, mock_records)
    
    conn.commit()
    conn.close()
    print("Database successfully initialized and seeded with mock records!")

if __name__ == "__main__":
    init_db()
