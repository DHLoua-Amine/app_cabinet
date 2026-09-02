import os
import sys
import json
import zipfile
import urllib.request
from pathlib import Path

# Project paths
BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
DIST_DIR = BASE_DIR / "dist" / "CabinetNotarialZarai"
ZIP_OUT = BASE_DIR / "CabinetNotarial_v1.0.1.zip"

TOKEN = "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"
REPO = "DHLoua-Amine/app_cabinet"
TAG = "v1.0.1"

print(f"1. Compressing {DIST_DIR} into {ZIP_OUT}...")
with zipfile.ZipFile(ZIP_OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(DIST_DIR):
        for f in files:
            full_p = Path(root) / f
            rel_p = full_p.relative_to(DIST_DIR)
            zf.write(full_p, arcname=rel_p)

zip_size = os.path.getsize(ZIP_OUT)
print(f"   Created {ZIP_OUT.name} ({zip_size / (1024*1024):.1f} MB)")

headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Create Release
print(f"2. Creating Release {TAG} on GitHub repo {REPO}...")
create_url = f"https://api.github.com/repos/{REPO}/releases"
payload = {
    "tag_name": TAG,
    "target_commitish": "main",
    "name": f"Release {TAG} — Mise à jour automatique",
    "body": "Mise à jour v1.0.1 :\n- Bouton شبكة المكتب (Réseau) sur l'écran de connexion\n- Déverrouillage des paramètres Réseau pour la Secrétaire\n- Génération d'ID unique automatique pour les clients",
    "draft": False,
    "prerelease": False
}

req = urllib.request.Request(create_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        rel_data = json.loads(resp.read().decode('utf-8'))
        upload_url_template = rel_data.get("upload_url", "")
        print(f"   Release created successfully! (ID: {rel_data.get('id')})")
except Exception as e:
    print(f"❌ Failed to create release: {e}")
    sys.exit(1)

# Upload Asset
upload_url = upload_url_template.split("{")[0] + f"?name={ZIP_OUT.name}"
print(f"3. Uploading asset {ZIP_OUT.name} to GitHub Releases...")

with open(ZIP_OUT, "rb") as f:
    asset_data = f.read()

upload_headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/zip",
    "Content-Length": str(len(asset_data))
}

up_req = urllib.request.Request(upload_url, data=asset_data, headers=upload_headers, method="POST")
try:
    with urllib.request.urlopen(up_req) as up_resp:
        asset_res = json.loads(up_resp.read().decode('utf-8'))
        print(f"✅ ASSET UPLOADED SUCCESSFULLY! {asset_res.get('browser_download_url')}")
except Exception as e:
    print(f"❌ Asset upload failed: {e}")
    sys.exit(1)

print(f"🎉 RELEASE {TAG} IS NOW PUBLISHED AND LIVE ON GITHUB!")
