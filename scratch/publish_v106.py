import os
import sys
import json
import zipfile
import subprocess
import urllib.request
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
VERSION_FILE = BASE_DIR / "core" / "version.py"
DIST_DIR = BASE_DIR / "dist" / "DATLY"
ZIP_OUT = BASE_DIR / "scratch" / "DATLY_v1.0.6.zip"

TAG = "v1.0.6"
REPO = "DHLoua-Amine/app_cabinet"
TOKEN = "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"

print("1. Bumping version in core/version.py to 1.0.6...")
ver_content = VERSION_FILE.read_text(encoding="utf-8")
ver_content = ver_content.replace('__version__ = "1.0.4"', '__version__ = "1.0.6"')
ver_content = ver_content.replace('__version__ = "1.0.5"', '__version__ = "1.0.6"')
VERSION_FILE.write_text(ver_content, encoding="utf-8")

print(f"2. Compressing fresh DATLY build into {ZIP_OUT.name}...")
with zipfile.ZipFile(ZIP_OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(DIST_DIR):
        for f in files:
            full_p = Path(root) / f
            rel_p = full_p.relative_to(DIST_DIR)
            zf.write(full_p, arcname=rel_p)

print(f"   Created {ZIP_OUT.name} ({os.path.getsize(ZIP_OUT) / (1024*1024):.1f} MB)")

print("3. Committing git tag and pushing to GitHub...")
try:
    subprocess.run(["git", "add", "."], cwd=str(BASE_DIR), check=True)
    subprocess.run(["git", "commit", "-m", f"Release {TAG}: Card auto-crop & zoom, photo reset fix, camera RTSP TCP"], cwd=str(BASE_DIR), check=False)
    subprocess.run(["git", "tag", TAG], cwd=str(BASE_DIR), check=False)
    subprocess.run(["git", "push", "origin", "main", "--tags"], cwd=str(BASE_DIR), check=False)
except Exception as e:
    print(f"Git push warning: {e}")

headers = {
    "User-Agent": "CabinetNotarialZarai-Publisher",
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

print(f"4. Creating Release {TAG} on GitHub repo {REPO}...")
create_url = f"https://api.github.com/repos/{REPO}/releases"
payload = {
    "tag_name": TAG,
    "name": f"Release {TAG} — Auto-Crop CIN & Camera RTSP Fixes",
    "body": "Mise à jour v1.0.6 :\n- Détection et découpage automatique des petites cartes CIN sur pages scannées (Auto-Crop & Zoom)\n- Correction de la réinitialisation de la photo lors de la création d'un nouveau client\n- Stabilité et transport TCP pour les flux caméra RTSP (Dahua/Hikvision)",
    "draft": False,
    "prerelease": False
}

req = urllib.request.Request(create_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
with urllib.request.urlopen(req) as resp:
    rel_data = json.loads(resp.read().decode('utf-8'))
    print(f"   Release {TAG} created successfully! (ID: {rel_data.get('id')})")

upload_url_template = rel_data.get("upload_url", "")
upload_url = upload_url_template.split("{")[0] + f"?name=DATLY_v1.0.6.zip"

print(f"5. Uploading {ZIP_OUT.name} to GitHub Releases...")
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

print(f"\n✨ RELEASE {TAG} IS NOW LIVE ON GITHUB!")
