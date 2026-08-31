import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import auth
import voice_verifier

print("1. Loading Gemini API keys from settings...")
api_keys = auth.session_state.get_gemini_api_key()
print(f"   Found API Key length: {len(api_keys)} characters")

if not api_keys:
    print("❌ No API key found in session state.")
    sys.exit(1)

print("2. Testing live API call to models/gemini-2.5-flash...")
try:
    res = voice_verifier.call_gemini_api(
        prompt="أنت خبير توثيقي. اكتب الجملة التالية باختصار: تم اختبار الاتصال بنجاح بنسبة 100%.",
        api_key=api_keys,
        model_name="gemini-2.5-flash"
    )
    print("✅ Live Google Gemini API Response:")
    print(res)
    print("\n[VERIFICATION SUCCESSFUL] gemini-2.5-flash is 100% active, reachable, and working!")
except Exception as err:
    print(f"❌ API Call Failed: {err}")
