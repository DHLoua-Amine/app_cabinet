import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import voice_verifier

raw_keys = config.load_saved_api_keys("gemini")
keys_list = [k.strip() for k in raw_keys.replace('\n', ',').replace(';', ',').split(',') if k.strip()]

print(f"Testing all {len(keys_list)} keys in pool against gemini-2.5-flash:")
for idx, key in enumerate(keys_list, 1):
    try:
        res = voice_verifier.call_gemini_api(
            prompt="اختبار الجاهزية على gemini-2.5-flash",
            api_key=key,
            model_name="gemini-2.5-flash"
        )
        print(f"  ✅ Key #{idx} ({key[:8]}...{key[-4:]}): SUCCESS! Response: {res}")
    except Exception as err:
        print(f"  ❌ Key #{idx} ({key[:8]}...{key[-4:]}): FAILED with error: {err}")
