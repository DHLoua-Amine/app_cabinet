import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config

raw_key_string = config.load_saved_api_keys("gemini")
print(f"Raw Gemini API key string length: {len(raw_key_string)}")

keys_list = [k.strip() for k in raw_key_string.replace('\n', ',').replace(';', ',').split(',') if k.strip()]
print(f"Total active Gemini API keys in pool: {len(keys_list)}")

for idx, k in enumerate(keys_list, 1):
    print(f"  Key #{idx}: {k[:8]}...{k[-4:]} (Length: {len(k)})")
