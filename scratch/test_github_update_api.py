import sys
import urllib.request
import json
import ssl
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import version
import updater

print("="*70)
print(" 🧪 TEST SECTION 1 & 2: REAL GITHUB API & REPO CONFIGURATION TEST")
print("="*70)

repo = version.GITHUB_REPO_RELEASES
print(f"Current version.py __version__: '{version.__version__}'")
print(f"Current version.py GITHUB_REPO_RELEASES: '{repo}'")
print(f"Is update channel configured (is_update_channel_configured)? {updater.is_update_channel_configured()}")

url = f"https://api.github.com/repos/{repo}/releases/latest"
print(f"\nMaking REAL HTTP request to: {url}...")

req = urllib.request.Request(
    url,
    headers={"User-Agent": "CabinetNotarialZarai-AutoUpdater"}
)

try:
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
        status = response.status
        body = response.read().decode('utf-8')
        print(f"Response HTTP Status: {status}")
        data = json.loads(body)
        print("API Response JSON Data:")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
except urllib.error.HTTPError as http_err:
    print(f"❌ HTTP ERROR OCCURRED: Status Code {http_err.code}")
    print(f"Reason: {http_err.reason}")
    try:
        err_body = http_err.read().decode('utf-8')
        print(f"Response Body: {err_body}")
    except Exception:
        pass
except Exception as ex:
    print(f"❌ CONNECTION ERROR: {ex}")

print("\nExecuting updater.check_for_update() directly:")
result = updater.check_for_update()
print(f"check_for_update() return value: {result}")

print("="*70)
