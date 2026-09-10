# Standalone bootstrap script for creating the local SQLite database.
import sqlite3
from pathlib import Path

import bcrypt

DB_PATH = Path(__file__).resolve().parent / "recon_db.sqlite"

    # This legacy initializer creates the core tables and default administrator.
def setup_database():
    """Setup database and ensure admin user exists"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create system_users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)
    
    # Create internal_ledger table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS internal_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL,
            booking_date TEXT,
            amount_cents INTEGER,
            counterparty TEXT,
            file_fingerprint TEXT UNIQUE
        )
    """)
    
    # Create bank_statement_feed table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bank_statement_feed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_date TEXT,
            raw_description TEXT,
            extracted_id TEXT,
            net_amount_cents INTEGER,
            file_fingerprint TEXT UNIQUE
        )
    """)
    
    # Create reconciliation_results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ledger_id INTEGER,
            bank_id INTEGER,
            match_type TEXT,
            confidence REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Check if admin user exists
    cursor.execute("SELECT id FROM system_users WHERE username = 'admin'")
    if cursor.fetchone() is None:
        # Create admin user with default password
        password = "admin123"
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute("""
            INSERT INTO system_users (username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?)
        """, ('admin', password_hash, 'Administrator', 'Admin'))
        
        print("✅ Admin user created successfully!")
        print("   Username: admin")
        print("   Password: admin123")
    else:
        print("✅ Admin user already exists")
    
    conn.commit()
    conn.close()
    print("✅ Database setup complete!")

if __name__ == "__main__":
    setup_database()
