import os
import sys
import json
import zipfile
import urllib.request
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
DIST_DIR = BASE_DIR / "dist" / "CabinetNotarialZarai"
ZIP_OUT = BASE_DIR / "scratch" / "CabinetNotarial_v1.0.5.zip"

print(f"1. Compressing fresh build {DIST_DIR} into v1.0.5...")
with zipfile.ZipFile(ZIP_OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(DIST_DIR):
        for f in files:
            full_p = Path(root) / f
            rel_p = full_p.relative_to(DIST_DIR)
            zf.write(full_p, arcname=rel_p)

print(f"   Created {ZIP_OUT.name} ({os.path.getsize(ZIP_OUT) / (1024*1024):.1f} MB)")

TOKEN = "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"
REPO = "DHLoua-Amine/app_cabinet"
TAG = "v1.0.5"

headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

print(f"2. Creating Release {TAG} on GitHub repo {REPO}...")
create_url = f"https://api.github.com/repos/{REPO}/releases"
payload = {
    "tag_name": TAG,
    "name": f"Release {TAG} — Jaliss Fields & Simplified Arabic Word Exports",
    "body": "Mise à jour v1.0.5 :\n- Champs الجليس (Co-notaire) 100% visibles dans Section 0 des Paramètres\n- Exportations Microsoft Word au format Simplified Arabic 14pt Justifié",
    "draft": False,
    "prerelease": False
}

req = urllib.request.Request(create_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
with urllib.request.urlopen(req) as resp:
    rel_data = json.loads(resp.read().decode('utf-8'))
    print(f"   Release {TAG} created successfully! (ID: {rel_data.get('id')})")

upload_url_template = rel_data.get("upload_url", "")
upload_url = upload_url_template.split("{")[0] + f"?name=CabinetNotarial_v1.0.5.zip"

print(f"3. Uploading {ZIP_OUT.name} to GitHub...")
with open(ZIP_OUT, "rb") as f:
    asset_data = f.read()

upload_headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/zip",
    "Content-Length": str(len(asset_data))
}

up_req = urllib.request.Request(upload_url, data=asset_data, headers=upload_headers, method="POST")
with urllib.request.urlopen(up_req) as up_resp:
    asset_res = json.loads(up_resp.read().decode('utf-8'))
    print(f"ASSET UPLOADED SUCCESSFULLY! {asset_res.get('browser_download_url')}")

print(f"RELEASE {TAG} IS NOW LIVE ON GITHUB!")
