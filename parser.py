# File-ingestion and normalization helpers for ledger and bank source files.
import pandas as pd
import hashlib
from io import BytesIO

def parse_bytes_to_dataframe(file_bytes, filename, file_type):
    """
    Parse uploaded file bytes into DataFrame and generate file fingerprint
    
    Args:
        file_bytes: Raw file bytes
        filename: Name of the file
        file_type: Type of file ('internal_ledger' or 'bank_statement')
    
    Returns:
        tuple: (DataFrame, file_fingerprint)
    """
    # Fingerprint the complete source file so duplicate uploads can be detected.
    # Generate file fingerprint (MD5 hash)
    file_fingerprint = hashlib.md5(file_bytes).hexdigest()
    
    # Parse from memory; the API does not need to write temporary upload files.
    # Detect file type and parse accordingly
    if filename.endswith('.csv'):
        df = pd.read_csv(BytesIO(file_bytes))
    elif filename.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(BytesIO(file_bytes))
    elif filename.endswith(('.html', '.htm')):
        tables = pd.read_html(BytesIO(file_bytes))
        if not tables:
            raise ValueError(f"No table found in HTML file: {filename}")
        df = tables[0]
    else:
        raise ValueError(f"Unsupported file format: {filename}")
    
    # Normalize headers before applying aliases and validation rules.
    # Standardize column names to lowercase
    df.columns = [col.lower().strip() for col in df.columns]
    
    # Add file fingerprint to dataframe
    df['file_fingerprint'] = file_fingerprint
    
    # Data validation and transformation based on file type
    if file_type == 'internal_ledger':
        df = _validate_ledger(df)
    elif file_type == 'bank_statement':
        df = _validate_bank_statement(df)
    
    return df, file_fingerprint

    # Ledger records must expose these canonical fields to the matching engine.
def _validate_ledger(df):
    """Validate and transform internal ledger data"""
    # Ensure required columns exist
    required_cols = ['transaction_id', 'booking_date', 'amount_cents', 'counterparty']
    
    # Accept common ERP header variations without changing the engine contract.
    # Map common column name variations
    col_mapping = {
        'transactionid': 'transaction_id',
        'transaction_id': 'transaction_id',
        'bookingdate': 'booking_date',
        'booking_date': 'booking_date',
        'amount': 'amount_cents',
        'amount_cents': 'amount_cents',
        'party': 'counterparty',
        'counterparty': 'counterparty',
        'partner': 'counterparty',
    }
    
    # Rename columns based on mapping
    for old_col in df.columns:
        for key, new_col in col_mapping.items():
            if old_col.lower() == key:
                df = df.rename(columns={old_col: new_col})
                break
    
    # Keep malformed source files processable while making missing values explicit.
    # Fill missing required columns with defaults
    for col in required_cols:
        if col not in df.columns:
            if col == 'amount_cents':
                df[col] = 0
            else:
                df[col] = ''
    
    # Convert amount to cents (integer)
    if 'amount_cents' in df.columns:
        df['amount_cents'] = pd.to_numeric(df['amount_cents'], errors='coerce').fillna(0).astype(int)
    
    return df[required_cols + ['file_fingerprint']]

    # Bank records use a separate canonical schema from ledger records.
def _validate_bank_statement(df):
    """Validate and transform bank statement data"""
    required_cols = ['booking_date', 'raw_description', 'extracted_id', 'net_amount_cents']
    
    # Map common column name variations
    col_mapping = {
        'date': 'booking_date',
        'booking_date': 'booking_date',
        'bookingdate': 'booking_date',
        'description': 'raw_description',
        'raw_description': 'raw_description',
        'id': 'extracted_id',
        'extracted_id': 'extracted_id',
        'transactionid': 'extracted_id',
        'amount': 'net_amount_cents',
        'net_amount': 'net_amount_cents',
        'net_amount_cents': 'net_amount_cents',
    }
    
    # Rename columns based on mapping
    for old_col in df.columns:
        for key, new_col in col_mapping.items():
            if old_col.lower() == key:
                df = df.rename(columns={old_col: new_col})
                break
    
    # Fill missing required columns with defaults
    for col in required_cols:
        if col not in df.columns:
            if col == 'net_amount_cents':
                df[col] = 0
            else:
                df[col] = ''
    
    # Convert amount to cents (integer)
    if 'net_amount_cents' in df.columns:
        df['net_amount_cents'] = pd.to_numeric(df['net_amount_cents'], errors='coerce').fillna(0).astype(int)
    
    return df[required_cols + ['file_fingerprint']]
