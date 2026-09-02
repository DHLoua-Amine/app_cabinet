import os
import sys
import json
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import updater
import version

print("="*70)
print(" 🧪 TEST ITEM 1: PRIVATE GITHUB REPOSITORY AUTHENTICATION & REDIRECTS")
print("="*70)

token = updater.get_github_token()
print(f"Token detected by updater.get_github_token(): {'YES (masked: ' + token[:4] + '...)' if token else 'NO (empty)'}")

req = updater.make_github_request("https://api.github.com/repos/DHLoua-Amine/cabinet-notarial-updates/releases/latest")
print(f"Request User-Agent: {req.get_header('User-agent')}")
print(f"Request Authorization header: {req.get_header('Authorization')}")

res = updater.check_for_update()
print(f"\nResult of updater.check_for_update():")
print(json.dumps(res, indent=2, ensure_ascii=False))

print("="*70)
