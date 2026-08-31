import sys
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import reception
import permissions

permissions.session.sign_in("admin", permissions.ROLE_ADMIN, "Notaire")

print("=== INFLOWS GROUND TRUTH VERIFICATION ===")

# Query cases table directly via SQL
conn = sqlite3.connect(reception.DB_PATH)
cur = conn.cursor()

sql_cases = cur.execute("SELECT case_id, client_id, total_amount, avance_amount, created_at FROM cases WHERE avance_amount > 0").fetchall()
print(f"Direct SQL Query found {len(sql_cases)} cases with avance_amount > 0:")
total_sql_avances = 0.0
for c in sql_cases:
    print(f"  - Case ID: {c[0]} | Client: {c[1]} | Total: {c[2]} TND | Avance: {c[3]} TND | Date: {c[4]}")
    total_sql_avances += float(c[3] or 0)

print(f"\nDirect SQL Total Avances: {total_sql_avances:,.3f} TND")

# Call API get_case_inflows_between
api_inflows = reception.get_case_inflows_between("2020-01-01", "2030-12-31")
print(f"\nreception.get_case_inflows_between() returned {len(api_inflows)} inflow records:")
total_api_avances = 0.0
for inf in api_inflows:
    print(f"  - Inflow Case: {inf['case_id']} | Client: {inf['client_name']} | Avance: {inf['avance_amount']:,.3f} TND | Notes: {inf.get('payment_notes', '')}")
    total_api_avances += float(inf.get('avance_amount', 0))

print(f"\nAPI Total Inflow Avances: {total_api_avances:,.3f} TND")

assert abs(total_sql_avances - total_api_avances) < 0.01, "Mismatch between SQL ground truth and get_case_inflows_between API!"
print("\n[SUCCESS] Ground Truth 1:1 Match Verified for Revenue Inflows!")
