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

models_to_test = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.5-pro"]

print("Testing Key #2 and Key #3 across models:\n")
for idx in [1, 2]: # index 1 and 2 = Key #2 and Key #3
    key = keys_list[idx]
    print(f"--- Key #{idx+1} ({key[:8]}...{key[-4:]}) ---")
    for m in models_to_test:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": "اختبار الجاهزية"}]}]}
        try:
            r = requests.post(url, json=payload, verify=False, timeout=10)
            if r.status_code == 200:
                print(f"  ✅ Model '{m}': Status 200 SUCCESS!")
                res_txt = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                print(f"     Response: {res_txt[:100]}")
                break
            else:
                print(f"  ❌ Model '{m}': Status {r.status_code} -> {r.text[:120]}")
        except Exception as err:
            print(f"  ❌ Model '{m}': Exception {err}")
