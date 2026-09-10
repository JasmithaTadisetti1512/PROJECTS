# engine.py
# Rule-based reconciliation engine for ledger and bank transaction streams.
import pandas as pd
from datetime import datetime
from database import get_connection, release_connection


class EnterpriseMatchingEngine:
    def run_reconciliation(self, batch_id=None):
        # Use one connection for the complete run so status updates and result history stay consistent.
        conn = get_connection()
        try:
            ledger_query = "SELECT * FROM internal_ledger WHERE COALESCE(recon_status, 'UNRESOLVED') = 'UNRESOLVED'"
            bank_query = "SELECT * FROM bank_statement_feed"
            params = ()
            if batch_id:
                ledger_query += " AND batch_id = ?"
                bank_query += " WHERE batch_id = ?"
                params = (batch_id,)
            df_ledger = pd.read_sql_query(ledger_query, conn, params=params)
            df_bank = pd.read_sql_query(bank_query, conn, params=params)

            if df_ledger.empty or df_bank.empty:
                return (
                    pd.DataFrame(columns=['transaction_id', 'booking_date', 'amount_cents', 'counterparty']),
                    pd.DataFrame(columns=['transaction_id', 'booking_date', 'aggregate_amount_cents', 'bank_id']),
                    pd.DataFrame(columns=['transaction_id', 'booking_date', 'amount_cents', 'net_amount_cents']),
                    pd.DataFrame(columns=['transaction_id', 'booking_date', 'amount_cents', 'counterparty']),
                    pd.DataFrame(columns=['id', 'booking_date', 'raw_description', 'net_amount_cents']),
                )

            # First apply the strongest rule: matching identifier and amount.
            exact_matches = pd.merge(
                df_ledger,
                df_bank,
                left_on=['transaction_id', 'amount_cents'],
                right_on=['extracted_id', 'net_amount_cents'],
                how='inner',
                suffixes=('_ledger', '_bank'),
            )
            self._update_states(conn, exact_matches['transaction_id'].tolist(), 'RECONCILED_EXACT')

            remaining_ledger = df_ledger[~df_ledger['transaction_id'].isin(exact_matches['transaction_id'])].copy()
            remaining_bank = df_bank[~df_bank['id'].isin(exact_matches['id_bank'])].copy()

            # Next look for several ledger rows that add up to one bank posting.
            many_to_one_records = []
            matched_ledger_ids = []
            matched_bank_ids = []
            if not remaining_ledger.empty and not remaining_bank.empty:
                for _, bank_row in remaining_bank.iterrows():
                    group = remaining_ledger[remaining_ledger['counterparty'].fillna('') == (bank_row['raw_description'] or '')]
                    if group.empty:
                        continue
                    total_amount = int(group['amount_cents'].sum())
                    if total_amount == int(bank_row['net_amount_cents']):
                        for _, ledger_row in group.iterrows():
                            many_to_one_records.append({
                                'transaction_id': ledger_row['transaction_id'],
                                'booking_date': ledger_row['booking_date'],
                                'aggregate_amount_cents': total_amount,
                                'bank_id': bank_row['id'],
                            })
                            matched_ledger_ids.append(ledger_row['transaction_id'])
                        matched_bank_ids.append(bank_row['id'])

            many_to_one = pd.DataFrame(many_to_one_records)
            self._update_states(conn, matched_ledger_ids, 'RECONCILED_MANY_TO_ONE')

            remaining_ledger = remaining_ledger[~remaining_ledger['transaction_id'].isin(matched_ledger_ids)].copy()
            remaining_bank = remaining_bank[~remaining_bank['id'].isin(matched_bank_ids)].copy()

            # Remaining pairs within the five-cent tolerance become variance breaks.
            variance_rows = []
            variance_ids = []
            variance_bank_ids = []
            if not remaining_ledger.empty and not remaining_bank.empty:
                for _, ledger_row in remaining_ledger.iterrows():
                    for _, bank_row in remaining_bank.iterrows():
                        diff = abs(int(ledger_row['amount_cents']) - int(bank_row['net_amount_cents']))
                        if diff <= 5:
                            variance_rows.append({
                                'transaction_id': ledger_row['transaction_id'],
                                'booking_date': ledger_row['booking_date'],
                                'amount_cents': ledger_row['amount_cents'],
                                'net_amount_cents': bank_row['net_amount_cents'],
                                'bank_id': bank_row['id'],
                            })
                            variance_ids.append(ledger_row['transaction_id'])
                            variance_bank_ids.append(bank_row['id'])
                            break
            variance = pd.DataFrame(variance_rows)
            self._update_states(conn, variance_ids, 'VARIANCE_BREAK')

            resolved_ids = set(exact_matches['transaction_id'].tolist()) | set(matched_ledger_ids) | set(variance_ids)
            missing = remaining_ledger[~remaining_ledger['transaction_id'].isin(resolved_ids)].copy()
            self._update_states(conn, missing['transaction_id'].tolist(), 'UNMATCHED_BREAK')

            # Any bank rows still unused are unknown postings requiring review.
            unknown = remaining_bank[~remaining_bank['id'].isin(matched_bank_ids + variance_bank_ids)].copy()
            self._persist_results(conn, exact_matches, many_to_one, variance, missing, unknown, batch_id)
            return exact_matches, many_to_one, variance, missing, unknown
        finally:
            release_connection(conn)

        # Store outcomes independently of current ledger status so every run remains auditable.
    def _persist_results(self, conn, exact, many_to_one, variance, missing, unknown, batch_id=None):
        """Store one audit row for every outcome produced by a reconciliation run."""
        rows = []

        for match in exact.itertuples(index=False):
            rows.append((match.id_ledger, match.id_bank, 'EXACT', 1.0, batch_id))

        ledger_ids = {}
        transaction_ids = set(many_to_one.get('transaction_id', pd.Series(dtype=object)).tolist()) | set(variance.get('transaction_id', pd.Series(dtype=object)).tolist())
        if transaction_ids:
            placeholders = ','.join('?' for _ in transaction_ids)
            records = conn.execute(
                f"SELECT id, transaction_id FROM internal_ledger WHERE transaction_id IN ({placeholders})",
                tuple(transaction_ids),
            ).fetchall()
            ledger_ids = {transaction_id: ledger_id for ledger_id, transaction_id in records}

        for match in many_to_one.itertuples(index=False):
            rows.append((ledger_ids.get(match.transaction_id), match.bank_id, 'MANY_TO_ONE', 1.0, batch_id))

        for match in variance.itertuples(index=False):
            rows.append((ledger_ids.get(match.transaction_id), match.bank_id, 'VARIANCE', .95, batch_id))

        for match in missing.itertuples(index=False):
            rows.append((match.id, None, 'MISSING_LEDGER', 0.0, batch_id))

        for match in unknown.itertuples(index=False):
            rows.append((None, match.id, 'UNKNOWN_BANK', 0.0, batch_id))

        if rows:
            conn.executemany(
                "INSERT INTO reconciliation_results (ledger_id, bank_id, match_type, confidence, batch_id) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

        # Update each affected ledger transaction once and stamp the processing time.
    def _update_states(self, conn, id_list, status):
        if not id_list:
            return
        timestamp = datetime.now().isoformat(timespec='seconds')
        cursor = conn.cursor()
        for item in set(id_list):
            cursor.execute(
                "UPDATE internal_ledger SET recon_status = ?, last_processed = ? WHERE transaction_id = ?",
                (status, timestamp, str(item)),
            )
        conn.commit()

