import sys
import os
import subprocess
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import licensing

print("=== TESTING MULTI-MACHINE OFFICE LICENSING ===")

# Simulate 3 different laptops in the same office:
machine_notary = "1111-AAAA-2222"
machine_secretary1 = "3333-BBBB-4444"
machine_secretary2 = "5555-CCCC-6666"

office_name = "Cabinet Notarial Zarai"

print(f"1. Office: '{office_name}' has 3 laptops:")
print(f"   - Laptop 1 (Notary):    {machine_notary}")
print(f"   - Laptop 2 (Secretary 1): {machine_secretary1}")
print(f"   - Laptop 3 (Secretary 2): {machine_secretary2}")

# Generate 3 keys using tools/make_licence.py
make_lic = BASE_DIR / "tools" / "make_licence.py"

def generate_key_for_machine(mach, office_label):
    res = subprocess.run([sys.executable, str(make_lic), "--machine", mach, "--office", office_label], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        if line.strip().startswith("ZARAI-LIC-1."):
            return line.strip()
    return None

key1 = generate_key_for_machine(machine_notary, f"{office_name} - Notaire")
key2 = generate_key_for_machine(machine_secretary1, f"{office_name} - Secrétaire 1")
key3 = generate_key_for_machine(machine_secretary2, f"{office_name} - Secrétaire 2")

print("\n2. Generated 3 distinct license keys:")
print(f"   - Key 1: {key1[:35]}...")
print(f"   - Key 2: {key2[:35]}...")
print(f"   - Key 3: {key3[:35]}...")

# Verify each key against its intended machine fingerprint
v1 = licensing.verify_licence(key1, fingerprint=machine_notary)
v2 = licensing.verify_licence(key2, fingerprint=machine_secretary1)
v3 = licensing.verify_licence(key3, fingerprint=machine_secretary2)

print("\n3. Verification on matching machines:")
print(f"   - Key 1 on Laptop 1: status = {v1['status']} | office = '{v1['office']}'")
print(f"   - Key 2 on Laptop 2: status = {v2['status']} | office = '{v2['office']}'")
print(f"   - Key 3 on Laptop 3: status = {v3['status']} | office = '{v3['office']}'")

assert v1['status'] == licensing.ACTIVE, "Key 1 must be ACTIVE on Laptop 1"
assert v2['status'] == licensing.ACTIVE, "Key 2 must be ACTIVE on Laptop 2"
assert v3['status'] == licensing.ACTIVE, "Key 3 must be ACTIVE on Laptop 3"
print("   [PASS] All 3 laptops activate cleanly!")

# Verify cross-machine rejection (copying Key 1 to Laptop 2)
v_cross = licensing.verify_licence(key1, fingerprint=machine_secretary1)
print("\n4. Testing anti-copy protection (using Key 1 on Laptop 2):")
print(f"   - Key 1 on Laptop 2: status = '{v_cross['status']}' | detail = '{v_cross['detail']}'")

assert v_cross['status'] == licensing.WRONG_MACHINE, "Key 1 must be rejected on Laptop 2 with WRONG_MACHINE"
print("   [PASS] Copy protection cleanly rejects copied keys across laptops!")

print("\n=== MULTI-MACHINE OFFICE LICENSING VERIFICATION: 100% SUCCESS ===")
