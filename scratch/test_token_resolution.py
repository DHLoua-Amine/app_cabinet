import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import updater

token = updater.get_github_token()
if token:
    masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "***"
    print(f"✅ Token GitHub détecté et prêt : {masked} (Longueur: {len(token)} caractères)")
else:
    print("⚠️ Aucun token GitHub renseigné dans version.py pour le moment (ENCODED_GITHUB_TOKEN = \"\").")
