import sys
import json
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import version
import updater

print("="*70)
print(" 🧪 TEST SECTION 3, 4 & 5: SIMULATING A NEW RELEASE FOUND ON GITHUB")
print("="*70)

# Test SemVer comparison logic in updater.parse_version
v_local = updater.parse_version("1.0.0")
v_remote_higher = updater.parse_version("v1.0.1")
v_remote_same = updater.parse_version("1.0.0")
v_remote_lower = updater.parse_version("v0.9.0")

print("\n--- SemVer Comparison Tests ---")
print(f"Local ('1.0.0') parsed: {v_local}")
print(f"Remote ('v1.0.1') parsed: {v_remote_higher} -> Is remote > local? {v_remote_higher > v_local}")
print(f"Remote ('1.0.0') parsed: {v_remote_same} -> Is remote > local? {v_remote_same > v_local}")
print(f"Remote ('v0.9.0') parsed: {v_remote_lower} -> Is remote > local? {v_remote_lower > v_local}")

# Simulated GitHub API release payload
mock_release_payload = {
    "version": "v1.1.0",
    "changelog": "Nouvelle version de test avec correctifs توثيقية.",
    "download_url": "https://github.com/DHLoua-Amine/cabinet-notarial-updates/releases/download/v1.1.0/update.zip",
    "sha256_url": "https://github.com/DHLoua-Amine/cabinet-notarial-updates/releases/download/v1.1.0/SHA256SUMS.txt",
    "asset_name": "update.zip",
    "asset_size": 15420000
}

print("\n--- Mocked Release Dict ---")
print(json.dumps(mock_release_payload, indent=2, ensure_ascii=False))

print("\n--- Checking UI connection in settings_page.py ---")
# Let's inspect settings_page.py on_update_checked
from ui.pages.settings_page import SettingsPage

# Let's inspect the methods on SettingsPage
methods = [m for m in dir(SettingsPage) if 'update' in m.lower()]
print(f"SettingsPage methods related to update: {methods}")

print("="*70)
