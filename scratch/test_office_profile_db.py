import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import reception
import office_profile
import permissions

permissions.session.sign_in("admin", permissions.ROLE_ADMIN, "Notaire")

print("=== CHECKING OFFICE PROFILE IN DB ===")
prof = office_profile.load()
for k, v in prof.items():
    print(f"  {k} = '{v}'")

print("\nDirect SQL Query on system_settings table:")
conn = sqlite3.connect(reception.DB_PATH)
cur = conn.cursor()
rows = cur.execute("SELECT setting_key, setting_value FROM system_settings").fetchall()
print(f"Total rows in system_settings: {len(rows)}")
for r in rows:
    print(f"  - {r[0]} = '{r[1]}'")
conn.close()

print("\nTesting office_profile.notary_block():")
print(office_profile.notary_block())

print("\nTesting office_profile.header_html():")
print(office_profile.header_html())
