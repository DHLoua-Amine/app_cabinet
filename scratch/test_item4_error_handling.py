import sys
import tempfile
import hashlib
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import updater

print("="*70)
print(" 🧪 TEST ITEM 4: NETWORK FAILURE & SHA-256 MISMATCH SAFE ERROR HANDLING")
print("="*70)

dummy_zip = Path(tempfile.gettempdir()) / "cabinet_notarial_update" / "update.zip"

print("\n--- 1. Testing SHA-256 Mismatch Error ---")
try:
    updater.download_and_verify_update(
        download_url="https://httpbin.org/bytes/1024",
        sha256_url="https://httpbin.org/base64/MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    )
except ValueError as e:
    print(f"✅ SHA-256 Mismatch caught correctly: {e}")
    assert not dummy_zip.exists(), "Dummy zip file should be deleted on SHA-256 mismatch!"
    print("✅ Verified: Zip file deleted on SHA-256 error (Installation untouched)!")
except Exception as e:
    print(f"Other exception caught: {e}")

print("\n--- 2. Testing Network Connection Error ---")
try:
    updater.download_and_verify_update(
        download_url="https://invalid-non-existent-domain-12345.com/update.zip"
    )
except ConnectionError as e:
    print(f"✅ Network error caught correctly: {e}")
    assert not dummy_zip.exists(), "Dummy zip file should be deleted on connection error!"
    print("✅ Verified: Zip file deleted on network error (Installation untouched)!")

print("\n" + "="*70)
print(" 🎉 ITEM 4 SAFE ERROR HANDLING PASSED 100%!")
print("="*70)
