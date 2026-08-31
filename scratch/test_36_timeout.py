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

for idx, key in enumerate(keys_list, 1):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "مرحباً"}]}]}
    try:
        r = requests.post(url, json=payload, verify=False, timeout=30)
        print(f"Key #{idx} ({key[:8]}...{key[-4:]}): Status = {r.status_code}")
        if r.status_code == 200:
            res_txt = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            print(f"  ✅ SUCCESS! Response: {res_txt[:100]}")
        else:
            print(f"  ❌ Error: {r.text[:200]}")
    except Exception as err:
        print(f"  ❌ Exception: {err}")
