import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import auth
import office_profile

print("Checking loaded Gemini API keys from office_profile / settings:")
raw_keys = office_profile.get_gemini_api_key()
print(f"Raw keys string length: {len(raw_keys)}")

keys_list = [k.strip() for k in raw_keys.replace('\n', ',').replace(';', ',').split(',') if k.strip()]
print(f"Parsed total active keys in pool: {len(keys_list)}")

for idx, k in enumerate(keys_list, 1):
    print(f"  Key #{idx}: {k[:8]}...{k[-4:]} (Length: {len(k)})")
