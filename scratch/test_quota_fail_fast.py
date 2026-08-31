import sys
import time
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import voice_verifier

# Invalid / Quota key
dummy_keys = "AIzaSyDummyKeyQuotaExhausted1, AIzaSyDummyKeyQuotaExhausted2, AIzaSyDummyKeyQuotaExhausted3"

print("="*70)
print(" ⚡ TESTING INSTANT FAIL-FAST ON EXHAUSTED / INVALID API KEYS")
print("="*70)

t0 = time.time()
try:
    voice_verifier.call_gemini_api("اختبار الحصة", api_key=dummy_keys)
except ValueError as e:
    elapsed = time.time() - t0
    print(f"\n⏱️ Quota Exhaustion / Key Failure Detected & Reported in: {elapsed:.2f} seconds!")
    print(f"Error Message Shown: {e}")
    assert elapsed < 5.0, f"FAIL: Fast-fail took too long ({elapsed:.2f}s)!"
    print("✅ Fail-Fast Test Passed (< 5 seconds target achieved!)")

print("="*70)
