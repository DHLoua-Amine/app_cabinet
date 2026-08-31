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
clean_k = keys.split(',')[0].strip().strip("'").strip('"')

models_to_test = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-flash-latest"]

print("="*70)
print(" 🧪 TESTING ACTIVE GEMINI MODELS DIRECTLY AGAINST API KEY")
print("="*70)

for m in models_to_test:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={clean_k}"
    payload = {"contents": [{"parts": [{"text": "Hello, respond with OK"}]}]}
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
        print(f"Model [{m}]: Status HTTP {r.status_code}")
        if r.status_code == 200:
            txt = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            print(f"   -> Response: {txt}")
        else:
            print(f"   -> Error: {r.text[:200]}")
    except Exception as ex:
        print(f"Model [{m}]: Exception: {ex}")
print("="*70)
