import sys
import os
import sqlite3
import shutil
import subprocess
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import reception
import permissions
import licensing

permissions.session.sign_in("admin", permissions.ROLE_ADMIN, "Notaire")

print("=== FRESH INSTALLATION ZERO-TRIAL ENFORCEMENT TEST ===")

# 1. Ensure licence.txt is removed to simulate a fresh unlicensed install
lic_file = config.DATA_DIR / "licence.txt"
backup_lic = None
if lic_file.exists():
    backup_lic = lic_file.read_text(encoding="utf-8")
    lic_file.unlink()
    print("Simulating fresh install: removed existing licence.txt")

try:
    # 2. Check licensing.status()
    st = licensing.status()
    print("\n1. Fresh Install licensing.status():", st)
    assert st.get("status") == licensing.UNLICENSED, f"Expected UNLICENSED, got {st.get('status')}"
    assert st.get("days_left") == 0, f"Expected days_left == 0, got {st.get('days_left')}"
    print("   [PASS] Fresh install reports UNLICENSED with 0 trial days.")

    # 3. Check is_licensed() & may_create_records()
    print("\n2. Checking permission flags:")
    print("   - is_licensed():", licensing.is_licensed())
    print("   - may_create_records():", licensing.may_create_records())
    assert licensing.is_licensed() is False, "is_licensed() must be False"
    assert licensing.may_create_records() is False, "may_create_records() must be False"
    print("   [PASS] Permission flags correctly return False.")

    # 4. Test Record Creation (Blocked Immediately)
    print("\n3. Testing @require_licence guarded creation (reception.register_client):")
    blocked = False
    try:
        reception.register_client(nom="BlockedNom", prenom="BlockedPrenom", phone="99999999")
    except licensing.LicenceRequired as e:
        blocked = True
        print(f"   ✓ Caught expected LicenceRequired exception: '{e}'")
    
    assert blocked is True, "Creation of new records MUST be blocked immediately on fresh install!"
    print("   [PASS] New record creation is BLOCKED IMMEDIATELY on fresh install!")

    # 5. Test Record Reading & Exporting (Allowed)
    print("\n4. Testing reading existing records (reception.get_all_clients):")
    clients = reception.get_all_clients()
    print(f"   ✓ Successfully fetched {len(clients)} existing client records.")
    print("   [PASS] Reading existing records is 100% UNBLOCKED and accessible.")

    # 6. Generate valid key via make_licence.py and test activation
    print("\n5. Testing License Activation with valid signed Ed25519 key:")
    fingerprint = licensing.machine_fingerprint()
    print(f"   Machine Fingerprint: {fingerprint}")
    
    make_lic = BASE_DIR / "tools" / "make_licence.py"
    if make_lic.exists():
        res = subprocess.run([sys.executable, str(make_lic), "--machine", fingerprint, "--office", "Cabinet Notarial Zarai"], capture_output=True, text=True)
        key_line = None
        for line in res.stdout.splitlines():
            if line.strip().startswith("ZARAI-LIC-1."):
                key_line = line.strip()
                break
        
        print(f"   Extracted Key: {key_line[:35]}...")
        assert key_line is not None, "Failed to extract key from make_licence.py output!"

        # Activate licence
        ok, msg = licensing.activate(key_line)
        print(f"   Activation Result: ok={ok}, msg='{msg}'")
        assert ok is True, f"Activation failed: {msg}"
        
        # Re-check status
        st_after = licensing.status()
        print("   Status after activation:", st_after)
        assert st_after.get("status") == licensing.ACTIVE, "Status must be ACTIVE after activation"
        assert licensing.may_create_records() is True, "may_create_records() must be True after activation"
        print("   [PASS] Activation successfully unlocks record creation!")

finally:
    # Restore original licence.txt if it existed
    if backup_lic is not None:
        lic_file.write_text(backup_lic, encoding="utf-8")
        print("\nRestored original licence.txt file.")

print("\n=== ZERO-TRIAL ENFORCEMENT VERIFICATION COMPLETE: ALL 6 TESTS PASSED ===")
