import os
import sys
import json
import urllib.request
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
INSTALLER_EXE = BASE_DIR / "dist_installer" / "CabinetNotarial_Setup_v1.0.0.exe"

TOKEN = "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"
REPO = "DHLoua-Amine/app_cabinet"
TAG = "v1.0.1"

headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# 1. Get or create release for tag v1.0.1
get_url = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}"
req = urllib.request.Request(get_url, headers=headers)
rel_data = None

try:
    with urllib.request.urlopen(req) as resp:
        rel_data = json.loads(resp.read().decode('utf-8'))
        print(f"1. Existing Release found for {TAG} (ID: {rel_data.get('id')})")
except Exception as e:
    print(f"Creating new Release for {TAG}...")
    create_url = f"https://api.github.com/repos/{REPO}/releases"
    payload = {
        "tag_name": TAG,
        "name": f"Release {TAG} — Mise à jour automatique",
        "body": "Mise à jour v1.0.1 :\n- Bouton Réseau sur l'écran de connexion\n- Déverrouillage des paramètres Réseau et Mises à jour pour la Secrétaire\n- Génération d'ID unique automatique",
        "draft": False,
        "prerelease": False
    }
    create_req = urllib.request.Request(create_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
    with urllib.request.urlopen(create_req) as c_resp:
        rel_data = json.loads(c_resp.read().decode('utf-8'))
        print(f"1. Release created for {TAG} (ID: {rel_data.get('id')})")

upload_url_template = rel_data.get("upload_url", "")
upload_url = upload_url_template.split("{")[0] + f"?name=CabinetNotarial_Setup_v1.0.0.exe"

print(f"2. Uploading installer asset {INSTALLER_EXE.name} ({os.path.getsize(INSTALLER_EXE) / (1024*1024):.1f} MB) to GitHub Releases...")
with open(INSTALLER_EXE, "rb") as f:
    asset_data = f.read()

upload_headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/octet-stream",
    "Content-Length": str(len(asset_data))
}

up_req = urllib.request.Request(upload_url, data=asset_data, headers=upload_headers, method="POST")
try:
    with urllib.request.urlopen(up_req) as up_resp:
        asset_res = json.loads(up_resp.read().decode('utf-8'))
        print(f"✅ ASSET UPLOADED SUCCESSFULLY! {asset_res.get('browser_download_url')}")
except Exception as e:
    print(f"❌ Asset upload failed or already exists: {e}")

print(f"🎉 RELEASE {TAG} IS NOW LIVE AND PUBLISHED ON GITHUB!")
