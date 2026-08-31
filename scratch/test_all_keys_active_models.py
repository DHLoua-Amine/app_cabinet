import sys
import json
import urllib3
from pathlib import Path
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config

provider, model = config.load_ai_engine()
keys = config.load_saved_api_keys(provider)

key_list = [k.strip() for k in keys.replace('\n', ',').replace(';', ',').split(',') if k.strip()]

print(f"Key Pool has {len(key_list)} key(s):")

for idx, key in enumerate(key_list):
    clean_k = key.strip().strip("'").strip('"')
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={clean_k}"
    payload = {"contents": [{"parts": [{"text": "Hello, respond with OK"}]}]}
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
        print(f"Key #{idx+1} ({clean_k[:10]}...): HTTP {r.status_code}")
        if r.status_code == 200:
            txt = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            print(f"   ✅ SUCCESS! Response: {txt}")
        else:
            print(f"   ❌ Failed: {r.text[:180]}")
    except Exception as ex:
        print(f"Key #{idx+1}: Exception: {ex}")
