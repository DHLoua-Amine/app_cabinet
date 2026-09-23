@echo off
echo Resetting DATLY passwords to zarai1234...
py -c "import sqlite3, os, hashlib, secrets; salt=secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac('sha256', b'zarai1234', salt, 260000); h=f'pbkdf2_sha256$260000${salt.hex()}${digest.hex()}'; db=os.path.expandvars(r'%%LOCALAPPDATA%%\CabinetNotarialZarai\data\reception.db'); conn=sqlite3.connect(db); conn.execute('UPDATE app_users SET password_hash=?, must_change=0, failed_attempts=0 WHERE username in (\'patron\',\'secretaire\')', (h,)); conn.commit(); print('SUCCESS: Passwords for patron and secretaire have been reset to zarai1234!')"
pause
