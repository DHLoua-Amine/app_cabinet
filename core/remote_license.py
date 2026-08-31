"""
core/remote_license.py — Contrôle de licence à distance via GitHub.
Permet d'activer/désactiver l'accès d'un client à distance et d'obtenir des réglages personnalisés.
"""

import json
import urllib.request
import ssl
from pathlib import Path
from version import GITHUB_REPO_RELEASES, LICENSE_KEY, APP_NAME
from config import LOGS_DIR

CACHE_FILE = LOGS_DIR / "license_cache.json"

def _get_ssl_context():
    try:
        import config
        return config.get_ssl_context()
    except Exception:
        return ssl.create_default_context()

MAX_OFFLINE_SECONDS = 7 * 86400  # Max 7 jours d'utilisation hors-ligne

def check_remote_license() -> tuple[bool, str, dict]:
    """
    Vérifie la validité de la licence actuelle auprès du fichier licenses.json sur GitHub.
    Retourne (is_active: bool, message: str, client_info: dict).
    """
    import time
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO_RELEASES}/main/licenses.json"
    
    remote_data = None
    network_error = False

    try:
        req = urllib.request.Request(
            raw_url,
            headers={"User-Agent": "CabinetNotarialZarai-LicenseChecker"}
        )
        with urllib.request.urlopen(req, timeout=5, context=_get_ssl_context()) as response:
            if response.status == 200:
                remote_data = json.loads(response.read().decode('utf-8'))
                remote_data["_last_online_ts"] = int(time.time())
                try:
                    LOGS_DIR.mkdir(parents=True, exist_ok=True)
                    CACHE_FILE.write_text(json.dumps(remote_data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
    except Exception as e:
        network_error = True
        if CACHE_FILE.exists():
            try:
                remote_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                remote_data = None

    if remote_data is None:
        if network_error:
            return True, "Mode hors-ligne", {"client_name": "Client", "active": True}
        return True, "Licence active par défaut", {"client_name": "Cabinet Zarai", "active": True}

    # Contrôle anti-truquage d'horloge (Clock Rollback Detection)
    if network_error:
        last_online = remote_data.get("_last_online_ts", 0)
        current_ts = int(time.time())
        if last_online > 0 and current_ts < (last_online - 3600):
            return (
                False,
                "<b>Modification suspecte de l'horloge système détectée</b><br><br>"
                "L'heure de l'ordinateur a été modifiée vers le passé. Une connexion internet est requise.",
                {}
            )
        if last_online > 0 and (current_ts - last_online) > MAX_OFFLINE_SECONDS:
            days_offline = (current_ts - last_online) // 86400
            return (
                False,
                f"<b>Période hors-ligne expirée ({days_offline} jours sans connexion)</b><br><br>"
                "Une connexion internet est requise pour vérifier la licence et réactiver l'accès.",
                {}
            )

    licenses = remote_data.get("licenses", {})
    client_entry = licenses.get(LICENSE_KEY)

    if not client_entry:
        if remote_data.get("strict_mode", False):
            return False, "Clé de licence invalide ou non répertoriée.", {}
        return True, "Licence active", {"client_name": "Client", "active": True}

    is_active = client_entry.get("active", True)
    client_name = client_entry.get("client_name", "Client")

    if not is_active:
        reason = client_entry.get("revoke_reason", "L'accès à cette application a été suspendu par l'administrateur.")
        msg = f"<b>Accès Désactivé pour {client_name}</b><br><br>{reason}"
        return False, msg, client_entry

    return True, f"Licence active pour {client_name}", client_entry


_CURRENT_CLIENT_FEATURES = {}

def set_client_features(features: dict):
    global _CURRENT_CLIENT_FEATURES
    _CURRENT_CLIENT_FEATURES = features or {}

def get_client_features() -> dict:
    return _CURRENT_CLIENT_FEATURES

def has_feature(feature_name: str, default: bool = False) -> bool:
    """
    Vérifie si le client actuel a accès à une fonctionnalité spécifique.
    Exemple: has_feature("custom_tax_calculator")
    """
    return bool(_CURRENT_CLIENT_FEATURES.get(feature_name, default))
