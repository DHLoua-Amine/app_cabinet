import os
import sys
import sqlite3
import hashlib
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import reception

print("=== RESOLVED PRODUCTION DB PATH FROM CODE ===")
print(f"config.DATA_DIR = {config.DATA_DIR}")
print(f"reception.DB_PATH = {reception.DB_PATH}")

appdata_db = Path(reception.DB_PATH)
project_db = BASE_DIR / "database.db"

candidates = [appdata_db, project_db, BASE_DIR / "reception.db", Path.home() / ".gemini" / "antigravity" / "reception.db"]

print("\n=== EXAMINING ALL CANDIDATE DATABASE FILES ===")
for p in candidates:
    if p.exists():
        stat = p.stat()
        with open(p, "rb") as f:
            md5_val = hashlib.md5(f.read()).hexdigest()
        print(f"==================================================")
        print(f"File Name: {p.name}")
        print(f"Absolute Path: {p}")
        print(f"File Size: {stat.st_size} bytes")
        print(f"Modification Timestamp (mtime): {stat.st_mtime}")
        print(f"MD5 Checksum: {md5_val}")
        print("--------------------------------------------------")
        try:
            conn = sqlite3.connect(p)
            cur = conn.cursor()
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            print(f"Table Count: {len(tables)}")
            for t in sorted(tables):
                cnt = cur.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                print(f"  - Table '{t}': {cnt} rows")
            
            integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
            print(f"PRAGMA integrity_check: {integrity}")
            conn.close()
        except Exception as e:
            print(f"SQLite Error: {e}")
        print("==================================================\n")
    else:
        print(f"File DOES NOT EXIST: {p}\n")
