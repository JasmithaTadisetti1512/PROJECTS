# database.py
# SQLite persistence layer for users, transactions, reconciliation history, and audit events.
import sqlite3
from pathlib import Path

import bcrypt

# Keep the database beside the application so local runs use the same data file.
DB_PATH = Path(__file__).resolve().parent / "recon_db.sqlite"


    # Open a short-lived connection while creating or migrating the schema.
def init_enterprise_tables():
    """Initialize SQLite tables used by the reconciliation app."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS internal_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL,
            booking_date TEXT,
            amount_cents INTEGER,
            counterparty TEXT,
            recon_status TEXT DEFAULT 'UNRESOLVED',
            file_fingerprint TEXT,
            last_processed TEXT,
            batch_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bank_statement_feed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_date TEXT,
            raw_description TEXT,
            extracted_id TEXT,
            net_amount_cents INTEGER,
            file_fingerprint TEXT,
            batch_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ledger_id INTEGER,
            bank_id INTEGER,
            match_type TEXT,
            confidence REAL,
            batch_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add columns required by newer versions when an older database is reused.
    for table_name, required_columns in {
        "internal_ledger": ["recon_status", "file_fingerprint", "last_processed", "batch_id"],
        "bank_statement_feed": ["file_fingerprint", "batch_id"],
        "reconciliation_results": ["batch_id"],
        "system_users": ["role"],
    }.items():
        existing_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
        for column_name in required_columns:
            if column_name not in existing_columns:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT")
                if column_name == "recon_status":
                    cursor.execute(
                        f"UPDATE {table_name} SET recon_status = 'UNRESOLVED' WHERE recon_status IS NULL"
                    )
                if column_name == "role":
                    cursor.execute(f"UPDATE {table_name} SET role = 'Admin' WHERE role IS NULL")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_ledger_status ON internal_ledger(recon_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_extracted_id ON bank_statement_feed(extracted_id)")

    # Ensure the local demonstration administrator exists without overwriting it.
    password_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode("utf-8")
    cursor.execute(
        "INSERT OR IGNORE INTO system_users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
        ("admin", password_hash, "Administrator", "Admin"),
    )

    conn.commit()
    conn.close()


    # Callers own the returned connection and must release it when finished.
def get_connection():
    return sqlite3.connect(DB_PATH)


    # Hash passwords before they ever reach SQLite.
def create_user(email, password, full_name):
    """Create a regular operator account using an email address as username."""
    conn = get_connection()
    try:
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute(
            "INSERT INTO system_users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (email, password_hash, full_name, "Operator"),
        )
        conn.execute(
            "INSERT INTO audit_log (username, action, details) VALUES (?, ?, ?)",
            (email, "Account created", "New Operator account registered"),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        release_connection(conn)


    # Audit events provide traceability for both automated and manual actions.
def log_activity(username, action, details=""):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO audit_log (username, action, details) VALUES (?, ?, ?)",
            (username, action, details),
        )
        conn.commit()
    finally:
        release_connection(conn)


    # Return newest events first for the activity-trail screen.
def get_audit_log():
    conn = get_connection()
    try:
        return __import__("pandas").read_sql_query(
            "SELECT created_at, username, action, details FROM audit_log ORDER BY id DESC",
            conn,
        )
    finally:
        release_connection(conn)


    # Make connection cleanup safe for callers using finally blocks.
def release_connection(conn):
    if conn:
        conn.close()
