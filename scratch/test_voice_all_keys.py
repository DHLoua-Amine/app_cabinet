import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import voice_verifier

raw_keys = config.load_saved_api_keys("gemini")
keys_list = [k.strip() for k in raw_keys.replace('\n', ',').replace(';', ',').split(',') if k.strip()]

print(f"Testing call_gemini_api with all {len(keys_list)} keys in pool:")
for idx, key in enumerate(keys_list, 1):
    try:
        res = voice_verifier.call_gemini_api(
            prompt="مرحباً، تم الاختبار بنجاح",
            api_key=key
        )
        print(f"  ✅ Key #{idx} ({key[:8]}...{key[-4:]}): SUCCESS! Response: {res[:80]}")
    except Exception as err:
        print(f"  ❌ Key #{idx} ({key[:8]}...{key[-4:]}): FAILED with error: {err}")
