# Flask API entry point for the browser-based reconciliation workspace.
import io
import json
import os
import secrets
from datetime import datetime
from functools import wraps

import bcrypt
from flask import Flask, jsonify, render_template, request, send_file, session

from database import create_user, get_audit_log, get_connection, init_enterprise_tables, log_activity, release_connection
from engine import EnterpriseMatchingEngine
from parser import parse_bytes_to_dataframe
from reporter import build_excel_report_stream

# Serve the frontend and API from one local process.
app = Flask(__name__, template_folder="frontend", static_folder="frontend", static_url_path="/assets")
app.secret_key = secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
report_cache = {}


# Read the current operator from Flask's signed session cookie.
def current_user():
    return session.get("user")


# Protect data and mutation routes from unauthenticated requests.
def require_auth(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "Authentication required."}), 401
        return handler(*args, **kwargs)
    return wrapped


# Convert Pandas results into JSON-safe records for the browser.
def dataframe_records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso")) if not frame.empty else []


# Verify credentials against the bcrypt hash stored in SQLite.
def check_login(username, password):
    conn = get_connection()
    try:
        user = conn.execute(
            "SELECT username, password_hash, full_name, role FROM system_users WHERE lower(username) = lower(?)",
            (username.strip(),),
        ).fetchone()
        if user and bcrypt.checkpw(password.encode("utf-8"), user[1].encode("utf-8")):
            return {"username": user[0], "full_name": user[2], "role": user[3]}
    finally:
        release_connection(conn)
    return None


# Build the KPI payload displayed by the overview screen.
def dashboard_data():
    conn = get_connection()
    try:
        ledger_total = conn.execute("SELECT COUNT(*) FROM internal_ledger").fetchone()[0]
        bank_total = conn.execute("SELECT COUNT(*) FROM bank_statement_feed").fetchone()[0]
        reconciled_total = conn.execute("SELECT COUNT(*) FROM internal_ledger WHERE recon_status LIKE 'RECONCILED_%'").fetchone()[0]
        variance_total = conn.execute("SELECT COUNT(*) FROM internal_ledger WHERE recon_status = 'VARIANCE_BREAK'").fetchone()[0]
        unresolved_total = conn.execute("SELECT COUNT(*) FROM internal_ledger WHERE COALESCE(recon_status, 'UNRESOLVED') IN ('UNRESOLVED', 'UNMATCHED_BREAK')").fetchone()[0]
        activity_total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    finally:
        release_connection(conn)
    return {"ledger_total": ledger_total, "bank_total": bank_total, "reconciled_total": reconciled_total, "variance_total": variance_total, "unresolved_total": unresolved_total, "activity_total": activity_total, "reconciliation_rate": round(reconciled_total / ledger_total * 100, 1) if ledger_total else 0}


@app.get("/")
def index():
    # Render the single-page frontend shell.
    return render_template("index.html")


@app.post("/api/auth/login")
def login():
    # Establish a session after successful local authentication.
    payload = request.get_json(silent=True) or {}
    user = check_login(payload.get("username", ""), payload.get("password", ""))
    if not user:
        return jsonify({"error": "Invalid email or password."}), 401
    session["user"] = user
    log_activity(user["username"], "Sign in", "Local account authenticated")
    return jsonify({"user": user})


@app.post("/api/auth/register")
def register():
    # Validate and create a new operator account.
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    full_name = payload.get("full_name", "").strip()
    password = payload.get("password", "")
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return jsonify({"error": "Enter a valid email address."}), 400
    if not full_name or len(password) < 6:
        return jsonify({"error": "Enter your full name and a password of at least 6 characters."}), 400
    if payload.get("password_confirmation") != password:
        return jsonify({"error": "Passwords do not match."}), 400
    if not create_user(email, password, full_name):
        return jsonify({"error": "That email address is already registered."}), 409
    return jsonify({"message": "Account created. You can now sign in."}), 201


@app.post("/api/auth/logout")
def logout():
    # Remove the current operator session.
    session.clear()
    return jsonify({"message": "Signed out."})


@app.get("/api/session")
def session_info():
    # Let the frontend restore a previous login on page load.
    return jsonify({"user": current_user()})


@app.get("/api/dashboard")
@require_auth
def dashboard():
    # Return current transaction and reconciliation totals.
    return jsonify(dashboard_data())


@app.post("/api/upload")
@require_auth
def upload():
    # Parse, fingerprint, and stage both source files in SQLite.
    ledger = request.files.get("ledger")
    bank = request.files.get("bank")
    if not ledger or not bank:
        return jsonify({"error": "Both ledger and bank files are required."}), 400
    conn = get_connection()
    batch_id = secrets.token_urlsafe(12)
    try:
        ledger_frame, ledger_hash = parse_bytes_to_dataframe(ledger.read(), ledger.filename, "internal_ledger")
        bank_frame, _ = parse_bytes_to_dataframe(bank.read(), bank.filename, "bank_statement")
        bank_hash = bank_frame["file_fingerprint"].iloc[0]
        existing_ledger_count = conn.execute("SELECT COUNT(*) FROM internal_ledger WHERE file_fingerprint = ? OR file_fingerprint LIKE ?", (ledger_hash, f"{ledger_hash}:%")).fetchone()[0]
        if existing_ledger_count >= len(ledger_frame):
            return jsonify({"error": "Duplicate ledger file detected. Upload blocked."}), 409
        if existing_ledger_count:
            conn.execute("DELETE FROM internal_ledger WHERE file_fingerprint = ? OR file_fingerprint LIKE ?", (ledger_hash, f"{ledger_hash}:%"))
            conn.execute("DELETE FROM bank_statement_feed WHERE file_fingerprint = ? OR file_fingerprint LIKE ?", (bank_hash, f"{bank_hash}:%"))
        ledger_rows = []
        for index, row in enumerate(ledger_frame[["transaction_id", "booking_date", "amount_cents", "counterparty"]].itertuples(index=False, name=None)):
            ledger_rows.append((*row, ledger_hash if index == 0 else f"{ledger_hash}:{index}", "UNRESOLVED", batch_id))
        bank_rows = []
        for index, row in enumerate(bank_frame[["booking_date", "raw_description", "extracted_id", "net_amount_cents"]].itertuples(index=False, name=None)):
            bank_rows.append((*row, bank_hash if index == 0 else f"{bank_hash}:{index}", batch_id))
        conn.executemany("INSERT OR IGNORE INTO internal_ledger (transaction_id, booking_date, amount_cents, counterparty, file_fingerprint, recon_status, batch_id) VALUES (?, ?, ?, ?, ?, ?, ?)", ledger_rows)
        conn.executemany("INSERT OR IGNORE INTO bank_statement_feed (booking_date, raw_description, extracted_id, net_amount_cents, file_fingerprint, batch_id) VALUES (?, ?, ?, ?, ?, ?)", bank_rows)
        conn.commit()
    except Exception as error:
        return jsonify({"error": str(error)}), 400
    finally:
        release_connection(conn)
    log_activity(session["user"]["username"], "Files uploaded", f"Ledger rows: {len(ledger_frame)}; Bank rows: {len(bank_frame)}")
    session["batch_id"] = batch_id
    return jsonify({"message": "Batch records ingested successfully.", "ledger_rows": len(ledger_frame), "bank_rows": len(bank_frame), "batch_id": batch_id})


@app.post("/api/reconcile")
@require_auth
def reconcile():
    # Run matching and cache the generated workbook for download.
    perfect, many_to_one, variance, missing, unknown = EnterpriseMatchingEngine().run_reconciliation(session.get("batch_id"))
    summary = {"exact": len(perfect), "many_to_one": len(many_to_one), "variance": len(variance), "missing": len(missing), "unknown": len(unknown)}
    report_id = secrets.token_urlsafe(16)
    report_cache[report_id] = build_excel_report_stream(perfect, many_to_one, variance, missing, unknown)
    session["report_id"] = report_id
    log_activity(session["user"]["username"], "Reconciliation run", "; ".join(f"{key.title()}: {value}" for key, value in summary.items()))
    return jsonify({"summary": summary, "report_url": "/api/report"})


@app.get("/api/report")
@require_auth
def report():
    # Stream the latest in-memory workbook as an Excel download.
    report_bytes = report_cache.get(session.get("report_id"))
    if not report_bytes:
        return jsonify({"error": "Run reconciliation before downloading a report."}), 404
    return send_file(io.BytesIO(report_bytes), as_attachment=True, download_name="Certified_Financial_Audit.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/exceptions")
@require_auth
def exceptions():
    # Return ledger items that still need operator attention.
    conn = get_connection()
    try:
        rows = conn.execute("SELECT transaction_id, booking_date, amount_cents, counterparty, recon_status FROM internal_ledger WHERE COALESCE(recon_status, 'UNRESOLVED') IN ('UNRESOLVED', 'UNMATCHED_BREAK', 'VARIANCE_BREAK') ORDER BY booking_date, transaction_id").fetchall()
    finally:
        release_connection(conn)
    columns = ["transaction_id", "booking_date", "amount_cents", "counterparty", "recon_status"]
    return jsonify([dict(zip(columns, row)) for row in rows])


@app.patch("/api/exceptions/<transaction_id>")
@require_auth
def adjust_exception(transaction_id):
    # Apply and audit a human decision for one open exception.
    payload = request.get_json(silent=True) or {}
    status = payload.get("status", "")
    reason = payload.get("reason", "").strip()
    if status not in {"MANUALLY_APPROVED", "MANUALLY_REJECTED", "UNDER_REVIEW"} or not reason:
        return jsonify({"error": "Choose a valid status and provide a reason."}), 400
    conn = get_connection()
    try:
        conn.execute("UPDATE internal_ledger SET recon_status = ?, last_processed = ? WHERE transaction_id = ?", (status, datetime.now().isoformat(timespec="seconds"), transaction_id))
        conn.commit()
    finally:
        release_connection(conn)
    log_activity(session["user"]["username"], "Manual exception adjustment", f"{transaction_id}: {status}; {reason}")
    return jsonify({"message": f"Adjustment saved for {transaction_id}."})


@app.get("/api/audit")
@require_auth
def audit():
    # Return the newest user and system actions for traceability.
    return jsonify(dataframe_records(get_audit_log()))


if __name__ == "__main__":
    # Initialize the local schema before starting the development server.
    init_enterprise_tables()
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8517")), debug=True)
