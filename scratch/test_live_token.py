import sys
import json
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import updater

token = updater.get_github_token()
print(f"1. Token extrait : '{token[:12]}...{token[-6:]}'")

url = f"https://api.github.com/repos/DHLoua-Amine/app_cabinet/releases"
req = updater.make_github_request(url)

try:
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=updater._ssl_ctx()),
        updater._PrivateRepoRedirectHandler()
    )
    with opener.open(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f"2. Connexion API GitHub réussie (HTTP 200 OK) !")
        print(f"3. Nombre de releases actuellement publiées sur 'DHLoua-Amine/app_cabinet' : {len(data)}")
        if data:
            print(f"   Dernière release : {data[0].get('tag_name')}")
        else:
            print("   (Aucune release publiée sur ce dépôt pour l'instant).")
    print("\n✅ AUTHENTIFICATION TOKEN APPAREILLÉE ET VALIDÉE À 100% !")
except urllib.error.HTTPError as e:
    print(f"❌ Erreur HTTP : {e.code} {e.reason}")
except Exception as e:
    print(f"❌ Erreur : {e}")
