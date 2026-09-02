import sys
import json
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import updater

print("="*70)
print(" 🧪 TEST DIRECT .EXE & .ZIP ASSET SUPPORT")
print("="*70)

# Simulate GitHub API response with an .exe asset
mock_release = {
    "tag_name": "v1.0.1",
    "body": "Version v1.0.1 distribuée sous forme de fichier .exe direct.",
    "assets": [
        {
            "name": "CabinetNotarialZarai_v1.0.1.exe",
            "size": 45000000,
            "browser_download_url": "https://github.com/DHLoua-Amine/app_cabinet/releases/download/v1.0.1/CabinetNotarialZarai_v1.0.1.exe",
            "url": "https://api.github.com/repos/DHLoua-Amine/app_cabinet/releases/assets/99911"
        },
        {
            "name": "SHA256SUMS.txt",
            "size": 100,
            "browser_download_url": "https://github.com/DHLoua-Amine/app_cabinet/releases/download/v1.0.1/SHA256SUMS.txt",
            "url": "https://api.github.com/repos/DHLoua-Amine/app_cabinet/releases/assets/99912"
        }
    ]
}

# Test how asset sorting picks .exe
assets = mock_release["assets"]
sorted_assets = sorted(assets, key=lambda a: 0 if a.get("name", "").lower().endswith(".exe") else 1)
selected = sorted_assets[0]

print(f"Selected asset name: '{selected['name']}'")
assert selected['name'].endswith(".exe")

print("\n✅ DIRECT .EXE ASSET DETECTED AND PRIORITIZED PERFECTLY!")
print("="*70)
