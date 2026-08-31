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

if not keys:
    print("No keys found!")
    sys.exit(1)

clean_k = keys.split(',')[0].strip().strip("'").strip('"')

print(f"Testing key against Google's ListModels API...")
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_k}"

try:
    r = requests.get(url, verify=False, timeout=10)
    if r.status_code == 200:
        data = r.json()
        models = [m["name"].replace("models/", "") for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        print(f"✅ WORKING ACTIVE MODELS ON YOUR KEY ({len(models)} found):")
        for m in models:
            print(f"  - {m}")
    else:
        print(f"ListModels failed: HTTP {r.status_code}: {r.text}")
except Exception as ex:
    print(f"Error: {ex}")
