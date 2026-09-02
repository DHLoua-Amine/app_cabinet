import os
import sys
import json
import shutil
import urllib.request
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
SRC_EXE = BASE_DIR / "dist_installer" / "CabinetNotarial_Setup_v1.0.0.exe"
TEMP_EXE = BASE_DIR / "scratch" / "CabinetNotarial_Setup_v1.0.0.exe"

shutil.copy2(SRC_EXE, TEMP_EXE)

TOKEN = "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"
REPO = "DHLoua-Amine/app_cabinet"
TAG = "v1.0.1"

headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Get release
get_url = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}"
req = urllib.request.Request(get_url, headers=headers)
with urllib.request.urlopen(req) as resp:
    rel_data = json.loads(resp.read().decode('utf-8'))

upload_url_template = rel_data.get("upload_url", "")
upload_url = upload_url_template.split("{")[0] + f"?name=CabinetNotarial_Setup_v1.0.0.exe"

print(f"Uploading asset {TEMP_EXE.name} ({os.path.getsize(TEMP_EXE) / (1024*1024):.1f} MB) to GitHub Release {TAG}...")
with open(TEMP_EXE, "rb") as f:
    asset_data = f.read()

upload_headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/octet-stream",
    "Content-Length": str(len(asset_data))
}

up_req = urllib.request.Request(upload_url, data=asset_data, headers=upload_headers, method="POST")
with urllib.request.urlopen(up_req) as up_resp:
    asset_res = json.loads(up_resp.read().decode('utf-8'))
    print(f"✅ ASSET UPLOADED SUCCESSFULLY! {asset_res.get('browser_download_url')}")

print(f"🎉 RELEASE {TAG} IS LIVE ON GITHUB!")
