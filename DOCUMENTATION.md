# Financial Reconciliation Application Documentation

## 1. Application Overview

This project is a local Flask application with an HTML, CSS, and JavaScript frontend for reconciling internal ledger transactions against bank statement transactions.

The application supports:

- Local email-style username and password authentication
- SQLite database storage
- CSV and XLSX file uploads
- Exact transaction matching
- Many-to-one matching
- Small amount variance detection
- Missing ledger detection
- Unknown bank transaction detection
- Manual exception status adjustments
- User activity history
- Executive KPI metrics
- Excel reconciliation report downloads

The main entry point is `app.py`. The browser client lives in the `frontend/` directory.

## 2. Project Files

### `app.py`

The Flask web server and JSON API. It handles authentication, file upload, reconciliation execution, manual exception status adjustments, activity history, KPI display, and report downloads.

### `database.py`

The SQLite database layer. It creates tables, migrates older schemas, creates accounts, stores audit events, and returns database connections.

### `parser.py`
The file parsing and validation layer. It reads CSV or Excel files, normalizes column names, validates required fields, converts amounts to integers, and adds an MD5 fingerprint.

### `engine.py`

The reconciliation engine. It loads unresolved ledger records and bank records, applies matching rules, updates ledger statuses, and returns result DataFrames.
The Excel report generator. It creates a workbook with summary, exact match, many-to-one, variance, missing, and unknown transaction sheets.

### `setup.py`

A standalone database setup script. It creates the basic database tables and ensures that the default admin account exists.

### `config.json`

Legacy configuration containing database settings, amount tolerance, column mapping information, and bank reference pattern settings. The current application uses SQLite through `database.py`.

### `recon_db.sqlite`

The local SQLite database file. It stores users, uploaded transactions, reconciliation statuses, and audit history.

### `frontend/`

The static browser client. `index.html` defines the application shell, `styles.css` provides the responsive control-room UI, and `app.js` connects the UI to the Flask API.

### Sample Excel files

The `sample_internal_ledger*.xlsx` and `sample_bank_statement*.xlsx` files are test inputs. They contain cases for exact matches, many-to-one matches, variances, missing transactions, and unknown bank entries.

## 3. Running the Application

Install the runtime dependencies once, then open PowerShell and run:

```powershell
cd D:\infy
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open the local URL in a browser on the server computer:

```text
http://localhost:8517
```

To share the same users, transactions, and activity trail across laptops, run the application on one computer only. Find that computer's IPv4 address with `ipconfig`, then open `http://SERVER_IP:8517` from the other laptops. Do not run separate copies on each laptop because each copy uses its own local `recon_db.sqlite` database.

The command remains active while the application is running. Stop it with `Ctrl+C`. The default local account is `admin` / `admin123`.

## 4. Authentication Section

The login form is implemented in `frontend/index.html` and calls the Flask authentication routes in `app.py`.

The user enters an email-style username and password. `check_login()` queries the `system_users` table and uses `bcrypt.checkpw()` to compare the supplied password with the stored password hash.

The default account is:

- Username: `admin`
- Password: `admin123`

New accounts can be registered through the `Create Account` tab. New accounts are stored with the `Operator` role. Passwords are never stored as plain text.

A successful sign-in creates a Flask session containing the authenticated user, username, full name, and role.

## 5. Database Section

`database.py` uses Python's built-in `sqlite3` module.

### Database initialization

`init_enterprise_tables()` creates the following tables:

- `system_users`: usernames, password hashes, names, and roles
- `internal_ledger`: uploaded ledger transactions and reconciliation status
- `bank_statement_feed`: uploaded bank transactions
- `reconciliation_results`: persisted exact, many-to-one, variance, missing, and unknown outcomes from each reconciliation run, including the upload `batch_id`
- `audit_log`: user actions and application activity

The initializer also checks older table schemas with `PRAGMA table_info()` and adds missing columns such as `recon_status`, `file_fingerprint`, and `last_processed`.

### User creation

`create_user()` hashes the password using bcrypt and inserts a new Operator account. Duplicate email addresses are rejected by the unique username constraint.

### Activity logging

`log_activity()` records the username, action, details, and timestamp in `audit_log`.

### Activity retrieval

`get_audit_log()` reads the audit table into a pandas DataFrame ordered from newest to oldest.

## 6. File Parsing Section

`parser.py` provides `parse_bytes_to_dataframe()`.

The function:

1. Calculates an MD5 fingerprint for the uploaded file.
2. Reads CSV, XLSX, or XLS content with pandas.
3. Converts column names to lowercase and removes surrounding whitespace.
4. Adds the file fingerprint to every row.
5. Applies ledger or bank-specific validation.

### Required ledger columns

The ledger file should contain:

- `transaction_id`
- `booking_date`
- `amount_cents`
- `counterparty`

### Required bank columns

The bank file should contain:

- `booking_date`
- `raw_description`
- `extracted_id`
- `net_amount_cents`

The parser also accepts several common column aliases. Missing text fields receive an empty value, and invalid numeric amounts become zero.

## 7. Data Ingestion Section

The Data Ingestion tab accepts one ledger file and one bank statement file.

When the user clicks the upload button:

1. Both files are parsed and validated.
2. The ledger fingerprint is checked for duplicates.
3. Ledger rows are inserted into `internal_ledger`.
4. Bank rows are inserted into `bank_statement_feed`.
5. New ledger rows receive the `UNRESOLVED` status.
6. A `Files uploaded` event is written to `audit_log`.

The insertion uses SQLite parameter placeholders (`?`) and `executemany()` for batch inserts.

Each upload receives a unique `batch_id`. Reconciliation uses that batch ID so older test uploads remain in the database history without affecting the current report.

## 8. Reconciliation Engine Section

`engine.py` contains `EnterpriseMatchingEngine`.

### Loading records

`run_reconciliation()` loads unresolved ledger rows and bank rows from the active upload batch in SQLite.

### Exact matching

A ledger row is an exact match when:

- `ledger.transaction_id` equals `bank.extracted_id`
- `ledger.amount_cents` equals `bank.net_amount_cents`

Exact matches receive the `RECONCILED_EXACT` status.

### Many-to-one matching

Remaining ledger rows are grouped by counterparty. If the sum of several ledger amounts equals one bank amount and the descriptions match, the rows receive the `RECONCILED_MANY_TO_ONE` status.

### Variance matching

Remaining ledger and bank rows are compared by amount. If the absolute difference is 5 cents or less, the ledger row receives the `VARIANCE_BREAK` status.

### Missing ledger items

Ledger rows that remain unresolved after the matching steps receive the `UNMATCHED_BREAK` status and are returned as missing items.

### Unknown bank items

Bank rows not used by exact or many-to-one matching are returned as unknown bank items.

### Database status updates

`_update_states()` updates `recon_status` and `last_processed` for the affected ledger transaction IDs.

## 9. Manual Exception Adjustment Section

The Manual Exception Adjustment Desk displays open ledger exceptions with these statuses:

- `UNRESOLVED`
- `UNMATCHED_BREAK`
- `VARIANCE_BREAK`

The user selects an exception and chooses one of these manual statuses:

- `MANUALLY_APPROVED`
- `MANUALLY_REJECTED`
- `UNDER_REVIEW`

A reason is required. Saving the adjustment updates the ledger status, records the processing timestamp, and adds a `Manual exception adjustment` event to the audit log.

## 10. User Modification History Section

The User Modification History Trail Log reads from the `audit_log` table and displays activity in a table.

The current application records:

- Successful local sign-ins
- New account creation
- File uploads
- Reconciliation runs
- Manual exception adjustments

Each event contains a timestamp, username, action, and details.

## 11. Executive KPI Dashboard Section

The Executive KPI Metrics Dashboard calculates live values from SQLite.

Displayed metrics include:

- Total ledger transactions
- Total bank transactions
- Reconciled ledger items
- Reconciliation rate
- Variance breaks
- Unresolved items
- Total recorded user activities

The reconciliation rate is calculated as:

```text
reconciled ledger items / total ledger items * 100
```

If there are no ledger rows, the rate is displayed as `0.0%` to avoid division by zero.

## 12. Excel Report Section

`reporter.py` creates an Excel workbook in memory using `openpyxl`.

The workbook contains:

- `Summary`
- `Perfect Matches`
- `Many-to-One`
- `Variance Breaks`
- `Missing Ledger`
- `Unknown Bank`

Empty result DataFrames produce a sheet containing a message such as `No variance breaks found`.

The workbook is returned as bytes and downloaded through the Flask report endpoint.

## 13. Sample Test Files

Use these files to test the complete reconciliation flow:

```text
sample_internal_ledger.xlsx
sample_bank_statement.xlsx
```

Alternative datasets are also available:

```text
sample_internal_ledger_2.xlsx
sample_bank_statement_2.xlsx
sample_internal_ledger_3.xlsx
sample_bank_statement_3.xlsx
```

Upload the matching ledger and bank files from the same dataset. Each dataset contains examples of all main reconciliation outcomes.

## 14. Recommended Test Workflow

1. Start the Flask application.
2. Sign in with `admin` and `admin123`, or create an Operator account.
3. Open `Data ingestion`.
4. Upload one internal ledger workbook.
5. Upload the matching bank statement workbook.
6. Click `Commit files`.
7. Open `Rules Engine` from the ingestion panel.
8. Click `Run engine`.
9. Review the five result counts.
10. Download the Excel report.
11. Open `Exception desk` and adjust an open exception.
12. Open `Activity trail` to verify recorded actions.
13. Return to `Overview` to review current totals.

## 15. Troubleshooting

### Port is not available

The default server uses port 8517. Change the `port` value in the `app.run()` block if needed.

### Invalid username or password

Use the default local account:

```text
Username: admin
Password: admin123
```

If a new account was registered, use the exact email address and password entered during registration.

### SQLite schema error

Run the database initializer:

```powershell
cd D:\infy
python -c "import database; database.init_enterprise_tables(); print('Database ready')"
```

The initializer migrates missing columns in the existing SQLite file.

### Missing Python package

Install the missing package with:

```powershell
python -m pip install package_name
```

For example:

```powershell
python -m pip install -r requirements.txt
```

### Syntax validation

Check the main Python modules with:

```powershell
python -m py_compile app.py database.py parser.py engine.py reporter.py setup.py
```

## 16. Important Implementation Notes

- The application currently uses SQLite, not PostgreSQL.
- The SQLite database path is relative: `recon_db.sqlite`.
- Run the Flask app from `D:\infy` so the database and configuration files are found.
- Do not delete `recon_db.sqlite` unless you intentionally want to remove stored users, transactions, and history.
- The `config.json` PostgreSQL settings are legacy and are not used by the SQLite connection functions.
- The Google OAuth URLs in the current app are placeholders unless real OAuth configuration and endpoints are supplied.
