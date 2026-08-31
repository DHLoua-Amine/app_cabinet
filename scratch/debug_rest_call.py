import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import requests
import json

raw_keys = config.load_saved_api_keys("gemini")
keys_list = [k.strip() for k in raw_keys.replace('\n', ',').replace(';', ',').split(',') if k.strip()]

print(f"Testing REST API directly for key #1 ({keys_list[0][:8]}...):")
clean_k = keys_list[0]
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={clean_k}"
payload = {"contents": [{"parts": [{"text": "مرحباً"}]}]}

r = requests.post(url, json=payload, verify=False)
print("Status Code:", r.status_code)
print("Response Text:", r.text[:400])
