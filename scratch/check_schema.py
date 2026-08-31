import sqlite3
from pathlib import Path

db_p = Path(r"C:\Users\amin\AppData\Local\CabinetNotarialZarai\data\reception.db")
conn = sqlite3.connect(db_p)
cur = conn.cursor()
cols = cur.execute("PRAGMA table_info(case_payments)").fetchall()
print("Columns in case_payments:")
for c in cols:
    print(c)
conn.close()
