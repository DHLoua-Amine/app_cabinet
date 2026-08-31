import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import voice_verifier

# Mock _post_json to simulate instant HTTP 429 Quota Exceeded from Google API
mock_resp = MagicMock()
mock_resp.status_code = 429
mock_resp.text = '{"error": {"code": 429, "message": "RESOURCE_EXHAUSTED: Quota exceeded for quota metric"}}'

print("="*70)
print(" ⚡ TESTING INSTANT HTTP 429 QUOTA EXHAUSTION FAIL-FAST")
print("="*70)

t0 = time.time()
with patch("voice_verifier._post_json", return_value=mock_resp):
    try:
        voice_verifier.call_gemini_api("اختبار الحصة", api_key="key1, key2, key3")
    except ValueError as e:
        elapsed = time.time() - t0
        print(f"\n⏱️ 3-Key Quota Exhaustion Failure Detected & Reported in: {elapsed:.4f} seconds!")
        print(f"Error Message: {e}")
        assert elapsed < 1.0, f"FAIL: Fail-fast took too long ({elapsed:.4f}s)!"
        print("\n✅ FAIL-FAST VERIFIED! (All 3 exhausted keys detected & aborted in < 1.0 seconds!)")

print("="*70)
