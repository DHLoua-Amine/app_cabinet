import sys
sys.path.insert(0, r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, r"C:\Users\amin\Desktop\zarai1_pyside\core")

import reception

with reception.get_db_cursor(commit=True) as cursor:
    cursor.execute("SELECT client_id, full_name FROM clients WHERE client_id = 'NEW'")
    row = cursor.fetchone()
    if row:
        new_real_id = reception.generate_client_id()
        cursor.execute("UPDATE clients SET client_id = ? WHERE client_id = 'NEW'", (new_real_id,))
        print(f"Updated client_id 'NEW' ({row['full_name']}) to '{new_real_id}'")
    else:
        print("No row with client_id = 'NEW' found.")

reception.clear_db_caches()
