# In-memory Excel report builder for reconciliation outcomes.
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

def build_excel_report_stream(perfect, many_to_one, variance, missing, unknown):
    """
    Build Excel report from reconciliation results
    
    Args:
        perfect: List of exact matches
        many_to_one: List of many-to-one matches
        variance: List of variance breaks
        missing: List of missing ledger items
        unknown: List of unknown bank items
    
    Returns:
        BytesIO object containing Excel file
    """
    # Build the workbook in memory so Flask can stream it directly to the browser.
    wb = Workbook()
    wb.remove(wb.active)  # Remove default sheet
    
    # Give each reconciliation category its own reviewable worksheet.
    # Create sheets
    _create_summary_sheet(wb, perfect, many_to_one, variance, missing, unknown)
    _create_perfect_matches_sheet(wb, perfect)
    _create_many_to_one_sheet(wb, many_to_one)
    _create_variance_sheet(wb, variance)
    _create_missing_sheet(wb, missing)
    _create_unknown_sheet(wb, unknown)
    
    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()

    # Start the report with a compact executive summary.
def _create_summary_sheet(wb, perfect, many_to_one, variance, missing, unknown):
    """Create summary sheet"""
    ws = wb.create_sheet("Summary", 0)
    
    # Title
    ws['A1'] = "Financial Reconciliation Report"
    ws['A1'].font = Font(size=16, bold=True)
    ws.merge_cells('A1:D1')
    
    # Summary metrics
    ws['A3'] = "Reconciliation Metrics"
    ws['A3'].font = Font(size=12, bold=True)
    
    metrics = [
        ('Exact Matches', len(perfect)),
        ('Many-to-One Matches', len(many_to_one)),
        ('Variance Breaks', len(variance)),
        ('Missing Ledger Items', len(missing)),
        ('Unknown Bank Items', len(unknown)),
    ]
    
    row = 4
    for label, count in metrics:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = count
        ws[f'A{row}'].font = Font(bold=True)
        row += 1
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 15

    # Exact matches are the highest-confidence reconciliation outcome.
    # Headers
def _create_perfect_matches_sheet(wb, perfect):
    """Create perfect matches sheet"""
    ws = wb.create_sheet("Perfect Matches")
    
    if perfect.empty:
        ws['A1'] = "No perfect matches found"
        return
    
    # Headers
    headers = ['Ledger ID', 'Bank ID', 'Ledger Amount', 'Bank Amount', 'Date', 'Description']
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
        ws.cell(row=1, column=col).font = Font(bold=True)
        ws.cell(row=1, column=col).fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
    
    # Data rows
    for row_idx, (_, match) in enumerate(perfect.iterrows(), 2):
        ws.cell(row=row_idx, column=1, value=match.get('transaction_id', ''))
        ws.cell(row=row_idx, column=2, value=match.get('id_bank', ''))
        ws.cell(row=row_idx, column=3, value=match.get('amount_cents', ''))
        ws.cell(row=row_idx, column=4, value=match.get('net_amount_cents', ''))
        ws.cell(row=row_idx, column=5, value=match.get('booking_date_ledger', match.get('booking_date', '')))
        ws.cell(row=row_idx, column=6, value=match.get('raw_description', ''))
    
    # Adjust column widths
    for col in range(1, 7):
        ws.column_dimensions[chr(64 + col)].width = 18

    # Headers
def _create_many_to_one_sheet(wb, many_to_one):
    """Create many-to-one matches sheet"""
    ws = wb.create_sheet("Many-to-One")
    
    if many_to_one.empty:
        ws['A1'] = "No many-to-one matches found"
        return
    
    # Headers
    headers = ['Ledger ID', 'Bank ID', 'Ledger Amount', 'Bank Amount', 'Date']
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
    
    # Data rows
    for row_idx, match in enumerate(many_to_one.to_dict('records'), 2):
        ws.cell(row=row_idx, column=1, value=match.get('transaction_id', ''))
        ws.cell(row=row_idx, column=2, value=match.get('bank_id', ''))
        ws.cell(row=row_idx, column=3, value=match.get('aggregate_amount_cents', ''))
        ws.cell(row=row_idx, column=4, value=match.get('aggregate_amount_cents', ''))
        ws.cell(row=row_idx, column=5, value=match.get('booking_date', ''))
    
    for col in range(1, 6):
        ws.column_dimensions[chr(64 + col)].width = 18

    # Headers
def _create_variance_sheet(wb, variance):
    """Create variance breaks sheet"""
    ws = wb.create_sheet("Variance Breaks")
    
    if variance.empty:
        ws['A1'] = "No variance breaks found"
        return
    
    # Headers
    headers = ['Ledger ID', 'Bank ID', 'Ledger Amount', 'Bank Amount', 'Variance', 'Date']
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
    
    # Data rows
    for row_idx, var in enumerate(variance.to_dict('records'), 2):
        ws.cell(row=row_idx, column=1, value=var.get('transaction_id', ''))
        ws.cell(row=row_idx, column=2, value=var.get('bank_id', ''))
        ws.cell(row=row_idx, column=3, value=var.get('amount_cents', ''))
        ws.cell(row=row_idx, column=4, value=var.get('net_amount_cents', ''))
        ws.cell(row=row_idx, column=5, value=abs(int(var.get('amount_cents', 0)) - int(var.get('net_amount_cents', 0))))
        ws.cell(row=row_idx, column=6, value=var.get('booking_date', ''))
    
    for col in range(1, 7):
        ws.column_dimensions[chr(64 + col)].width = 18

    # Headers
def _create_missing_sheet(wb, missing):
    """Create missing ledger items sheet"""
    ws = wb.create_sheet("Missing Ledger")
    
    if missing.empty:
        ws['A1'] = "No missing ledger items found"
        return
    
    # Headers
    headers = ['Ledger ID', 'Transaction ID', 'Amount', 'Date', 'Counterparty']
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
    
    # Data rows
    for row_idx, item in enumerate(missing.to_dict('records'), 2):
        ws.cell(row=row_idx, column=1, value=item.get('id', ''))
        ws.cell(row=row_idx, column=2, value=item.get('transaction_id', ''))
        ws.cell(row=row_idx, column=3, value=item.get('amount_cents', ''))
        ws.cell(row=row_idx, column=4, value=item.get('booking_date', ''))
        ws.cell(row=row_idx, column=5, value=item.get('counterparty', ''))
    
    for col in range(1, 6):
        ws.column_dimensions[chr(64 + col)].width = 18

    # Headers
def _create_unknown_sheet(wb, unknown):
        # Headers
    """Create unknown bank items sheet"""
    ws = wb.create_sheet("Unknown Bank")
    
    if unknown.empty:
        ws['A1'] = "No unknown bank items found"
        return
    
    # Headers
    headers = ['Bank ID', 'Description', 'Amount', 'Date', 'Extracted ID']
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="7030A0", end_color="7030A0", fill_type="solid")
    
    # Data rows
    for row_idx, item in enumerate(unknown.to_dict('records'), 2):
        ws.cell(row=row_idx, column=1, value=item.get('id', ''))
        ws.cell(row=row_idx, column=2, value=item.get('raw_description', ''))
        ws.cell(row=row_idx, column=3, value=item.get('net_amount_cents', ''))
        ws.cell(row=row_idx, column=4, value=item.get('booking_date', ''))
        ws.cell(row=row_idx, column=5, value=item.get('extracted_id', ''))
    
    for col in range(1, 6):
        ws.column_dimensions[chr(64 + col)].width = 18
