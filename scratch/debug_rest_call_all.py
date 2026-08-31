import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import requests

raw_keys = config.load_saved_api_keys("gemini")
keys_list = [k.strip() for k in raw_keys.replace('\n', ',').replace(';', ',').split(',') if k.strip()]

print(f"Testing all {len(keys_list)} keys in pool directly against gemini-2.5-flash:\n")
for idx, key in enumerate(keys_list, 1):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "اختبار"}]}]}
    try:
        r = requests.post(url, json=payload, verify=False, timeout=10)
        print(f"Key #{idx} ({key[:8]}...{key[-4:]}): Status Code = {r.status_code}")
        if r.status_code == 200:
            print("  ✅ Status 200 SUCCESS! Model responded cleanly!")
        else:
            print(f"  ❌ Response: {r.text[:200]}")
    except Exception as err:
        print(f"  ❌ Exception: {err}")
    print("-" * 60)
