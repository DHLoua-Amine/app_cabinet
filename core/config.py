import os
import sys
import ssl
import shutil
import urllib3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ── Where the read-only files that SHIP WITH the app live ────────────────────
# Running from source, the stylesheet and the face models sit in the checkout.
# Inside a PyInstaller build they are unpacked to sys._MEIPASS, which is a
# different directory from both the executable and this module. Resolving them
# from __file__ therefore worked in development and silently found nothing in
# the packaged app: the window opened unstyled and face recognition had no
# models to load.
FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    # PyInstaller unpacks bundled data here (onedir: <exe>/_internal).
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    # Anything the office WRITES belongs next to the executable, not inside the
    # bundle, which a one-file build deletes on exit.
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    RESOURCE_ROOT = BASE_DIR.parent          # the repository root
    APP_ROOT = BASE_DIR


def resource_path(*parts) -> Path:
    """A file that ships with the application, in source and packaged builds alike."""
    return RESOURCE_ROOT.joinpath(*parts)


# Support persistent user data directory isolated from app source code
local_appdata = os.environ.get("LOCALAPPDATA")
portable_marker = APP_ROOT / "data" / ".portable"
custom_path_file = APP_ROOT / "portable_data_path.txt"
env_data_dir = os.environ.get("NOTARY_DATA_DIR")

if env_data_dir and Path(env_data_dir).exists():
    DATA_DIR = Path(env_data_dir)
elif custom_path_file.exists() and custom_path_file.read_text(encoding="utf-8").strip():
    custom_path = Path(custom_path_file.read_text(encoding="utf-8").strip())
    if custom_path.exists():
        DATA_DIR = custom_path
    else:
        DATA_DIR = APP_ROOT / "data" if (portable_marker.exists() or not local_appdata) else Path(local_appdata) / "CabinetNotarialZarai" / "data"
elif portable_marker.exists() or not local_appdata:
    DATA_DIR = APP_ROOT / "data"
else:
    DATA_DIR = Path(local_appdata) / "CabinetNotarialZarai" / "data"

PROFILES_DIR = DATA_DIR / "profiles"
DOCUMENTS_DIR = DATA_DIR / "documents"
LOGS_DIR = DATA_DIR / "logs"

for d in [DATA_DIR, PROFILES_DIR, DOCUMENTS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Auto-migrate existing project data if AppData is new and project data exists
local_data = APP_ROOT / "data"
if local_data.exists() and local_data != DATA_DIR:
    # If project reception.db exists, copy it over if AppData db is empty/new
    local_db = local_data / "reception.db"
    appdata_db = DATA_DIR / "reception.db"
    if local_db.exists() and (not appdata_db.exists() or appdata_db.stat().st_size < 20000):
        try:
            shutil.copy2(local_db, appdata_db)
        except Exception as mig_err:
            # (b) If this fails the office opens an EMPTY database while its real
            # one sits in the old location. It cannot be shown - config runs before
            # any window exists - but it must not vanish.
            print(f"[CONFIG] could not migrate the existing database "
                  f"({local_db} -> {appdata_db}): {mig_err}", file=sys.stderr)

    # Copy profiles and documents folders if any
    for sub in ["profiles", "documents", "backups"]:
        src_sub = local_data / sub
        dst_sub = DATA_DIR / sub
        if src_sub.exists():
            for item in src_sub.glob("*"):
                dst_item = dst_sub / item.name
                if not dst_item.exists():
                    try:
                        if item.is_dir():
                            shutil.copytree(item, dst_item)
                        else:
                            shutil.copy2(item, dst_item)
                    except Exception as mig_err:
                        # (b) A profile photo or client document that did not come
                        # across is a missing record, not a cosmetic loss.
                        print(f"[CONFIG] could not migrate {item}: {mig_err}",
                              file=sys.stderr)

DEFAULT_SENTRY_DSN = "https://2f433aa28c2d86facfc824097bfb5d56@o4511956275757056.ingest.us.sentry.io/4511956282048512"
SENTRY_DSN = os.environ.get("SENTRY_DSN", DEFAULT_SENTRY_DSN).strip()

STATUS_NEW_VISIT = "جديد"
STATUS_IN_PROGRESS = "قيد الإنجاز"
STATUS_WAITING_SIGNATURE = "في انتظار التوقيع"
STATUS_FINALIZED = "تام ومسجل"

# ── TLS trust policy ──────────────────────────────────────────────────────
# Identity-card images and notarial deed content travel over these connections,
# so certificates are verified by default. Some office machines run an antivirus
# or corporate proxy that re-signs TLS with a private CA; on those, verification
# fails with CERTIFICATE_VERIFY_FAILED. Rather than disabling verification for
# the whole process, the callers try verified first and only fall back when the
# office has explicitly opted in via the marker below.
INSECURE_TLS_MARKER = DATA_DIR / "allow_insecure_tls.txt"


CA_BUNDLE_PATH = DATA_DIR / "ca_bundle.pem"
_ca_bundle_cache = None


def _build_ca_bundle() -> str:
    """
    Builds a CA bundle combining certifi's public roots with the roots Windows trusts.

    This office runs AVG Antivirus, whose "Web/Mail Shield" intercepts HTTPS and
    re-signs it with a locally generated root CA. That root is installed in the
    Windows certificate store but is absent from certifi, which is why every request
    failed with CERTIFICATE_VERIFY_FAILED and why verification was previously turned
    off process-wide. Merging the Windows ROOT store in fixes the actual cause, so
    certificates stay verified while scanned identity cards are in transit.
    """
    pem_parts = []

    try:
        import certifi
        pem_parts.append(Path(certifi.where()).read_text(encoding="utf-8"))
    except Exception:
        # (c) Safe. The bundle is assembled from several sources and the Windows
        # trust store below covers this one; certifi is simply not always present.
        pass

    if sys.platform == "win32":
        for store in ("ROOT", "CA"):
            try:
                for cert_bytes, encoding, _trust in ssl.enum_certificates(store):
                    if encoding == "x509_asn":
                        try:
                            pem_parts.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
                        except Exception:
                            continue
            except Exception:
                continue

    bundle = "\n".join(p.strip() for p in pem_parts if p and p.strip())
    if not bundle:
        raise RuntimeError("empty CA bundle")

    CA_BUNDLE_PATH.write_text(bundle + "\n", encoding="utf-8")
    return str(CA_BUNDLE_PATH)


# ── Reglages du cabinet ─────────────────────────────────────────────────────
# Un simple fichier JSON dans le dossier de donnees. Il ne contient QUE des
# preferences : rien de secret n'a le droit d'y entrer (les cles API sont
# scellees ailleurs, par DPAPI).
SETTINGS_FILE = DATA_DIR / "settings.json"

_settings_cache = None


def _lire_reglages() -> dict:
    """Le contenu du fichier, ou un dictionnaire vide. Ne leve jamais."""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    try:
        # config.py n'importe json qu'a l'interieur de ses fonctions ; on suit
        # la meme convention plutot que d'ajouter un import global.
        import json
        if SETTINGS_FILE.exists():
            donnees = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            _settings_cache = donnees if isinstance(donnees, dict) else {}
        else:
            _settings_cache = {}
    except Exception:
        # Fichier illisible ou corrompu : on repart des defauts plutot que
        # d'empecher l'application de demarrer pour une preference.
        _settings_cache = {}
    return _settings_cache


def get_setting(nom: str, defaut=None):
    """Une preference du cabinet, ou `defaut` si elle n'a jamais ete posee."""
    valeur = _lire_reglages().get(nom, defaut)
    return defaut if valeur is None else valeur


def set_setting(nom: str, valeur) -> bool:
    """Ecrit une preference. Rend True si elle est bien arrivee sur le disque.

    L'appelant DOIT regarder ce retour : une page qui annonce « enregistre »
    alors que l'ecriture a echoue est un defaut qu'on a deja rencontre deux
    fois dans ce projet (source camera, disque de sauvegarde)."""
    reglages = dict(_lire_reglages())
    reglages[nom] = valeur
    try:
        import json
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporaire = SETTINGS_FILE.with_suffix(".json.tmp")
        temporaire.write_text(json.dumps(reglages, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        # Remplacement atomique : une coupure de courant en pleine ecriture ne
        # doit pas laisser un fichier de reglages tronque.
        temporaire.replace(SETTINGS_FILE)
    except Exception:
        return False
    global _settings_cache
    _settings_cache = reglages
    return True


def load_remote_server_ip() -> str:
    return get_setting("server_ip", "127.0.0.1")


def save_remote_server_ip(ip: str) -> bool:
    set_setting("mode", "remote")
    return set_setting("server_ip", str(ip).strip())


def set_mode_local() -> bool:
    return set_setting("mode", "local")


def get_ca_bundle():
    """Returns the CA bundle path requests should verify against, or True for its default."""
    global _ca_bundle_cache
    if _ca_bundle_cache:
        return _ca_bundle_cache
    try:
        _ca_bundle_cache = _build_ca_bundle()
        return _ca_bundle_cache
    except Exception:
        try:
            import certifi
            _ca_bundle_cache = certifi.where()
            return _ca_bundle_cache
        except Exception:
            return True


def get_ssl_context():
    """
    An SSL context trusting the same merged bundle requests uses.

    urllib callers (the updater) need this explicitly: they would otherwise fall back
    to the default context, which does not know the locally installed AVG root and
    fails on this machine. Verification stays enabled either way.
    """
    try:
        bundle = get_ca_bundle()
        ctx = ssl.create_default_context(cafile=bundle) if isinstance(bundle, str) \
            else ssl.create_default_context()
    except Exception:
        ctx = ssl.create_default_context()

    # Python 3.13 turns on VERIFY_X509_STRICT by default. The AVG Web/Mail Shield root
    # installed on this machine does not mark Basic Constraints critical, so strict
    # RFC 5280 checking rejects it even though Windows trusts it. Relax only that flag:
    # the certificate chain is still fully verified against the trusted bundle.
    try:
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    except Exception:
        # (c) Safe. The flag does not exist on every Python build; when it cannot
        # be cleared the context simply keeps the stricter default, and the
        # certificate chain is verified either way.
        pass

    return ctx


def disable_insecure_tls() -> tuple:
    """
    Turns the certificate-verification opt-out back off.

    Returns (ok, note). The marker file is removed here; an opt-out set through
    the ZARAI_ALLOW_INSECURE_TLS environment variable cannot be cleared from
    inside the process, so that case is reported rather than silently ignored.
    """
    env_set = os.environ.get("ZARAI_ALLOW_INSECURE_TLS", "").strip() == "1"
    removed = False
    try:
        if INSECURE_TLS_MARKER.exists():
            INSECURE_TLS_MARKER.unlink()
            removed = True
    except Exception as e:
        return (False, f"could not remove {INSECURE_TLS_MARKER}: {e}")
    if env_set:
        return (False, "env")
    return (True, "removed" if removed else "already off")


def insecure_tls_allowed() -> bool:
    """True only if this office has explicitly opted into skipping certificate checks."""
    if os.environ.get("ZARAI_ALLOW_INSECURE_TLS", "").strip() == "1":
        return True
    try:
        return INSECURE_TLS_MARKER.exists()
    except Exception:
        return False


try:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    # (c) Safe. Purely cosmetic console-warning suppression.
    pass


# ── How this machine reaches the office database ─────────────────────────────
# Three modes, stored in one small json file beside the data:
#
#   standalone  — one machine, its own database. The default, and correct for a
#                 notary working alone.
#   server      — this machine holds the office database and serves it to the
#                 others. It is the only process that opens the file.
#   workstation — this machine keeps NO database of its own; every read and
#                 write goes to the server.
#
# Before this existed, installing on two machines silently produced two separate
# offices: the secretary registered a client into her own database and the
# notary's app never saw it.
NETWORK_CONFIG_PATH = DATA_DIR / "network.json"

MODE_STANDALONE = "standalone"
MODE_SERVER = "server"
MODE_WORKSTATION = "workstation"
DEFAULT_DB_PORT = 8765


def _default_network() -> dict:
    return {"mode": MODE_STANDALONE, "host": "", "port": DEFAULT_DB_PORT,
            "token": ""}


def load_network_config() -> dict:
    cfg = _default_network()
    try:
        if NETWORK_CONFIG_PATH.exists():
            import json
            raw = json.loads(NETWORK_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update({k: raw.get(k, v) for k, v in cfg.items()})
    except Exception as e:
        # (b) A damaged network.json must not lock the office out of its own
        # data. Falling back to standalone keeps the machine working on its
        # local database, and the mode is visible in Paramètres.
        print(f"[CONFIG] could not read network.json, using standalone: {e}",
              file=sys.stderr)
    if cfg.get("mode") not in (MODE_STANDALONE, MODE_SERVER, MODE_WORKSTATION):
        cfg["mode"] = MODE_STANDALONE
    try:
        cfg["port"] = int(cfg.get("port") or DEFAULT_DB_PORT)
    except Exception:
        cfg["port"] = DEFAULT_DB_PORT
    return cfg


def save_network_config(cfg: dict) -> bool:
    try:
        import json
        current = load_network_config()
        current.update({k: cfg[k] for k in ("mode", "host", "port", "token")
                        if k in cfg})
        NETWORK_CONFIG_PATH.write_text(
            json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[CONFIG] could not save network.json: {e}", file=sys.stderr)
        return False


# ── Verification de l'adresse du serveur ─────────────────────────────────────
# Un cabinet a perdu une heure sur ceci : le notaire etait sur 192.168.43.94 et
# la secretaire avait saisi 192.162.43.94 — un seul chiffre. L'application
# repondait « no answer from 192.162.43.94:8765 (TimeoutError) », ce qui est
# exact et parfaitement inutile : ca ressemble a un pare-feu, a un serveur
# eteint, a n'importe quoi sauf a une faute de frappe.
#
# La machine qui saisit l'adresse connait son propre reseau. Si l'adresse tapee
# n'y appartient pas, on peut le dire AVANT d'attendre un delai d'expiration, et
# meme proposer la correction.

_BLOCS_PRIVES = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")


def _adresses_locales() -> list:
    """Les adresses IPv4 de cette machine, hors boucle locale."""
    import socket
    trouvees = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            trouvees.append(probe.getsockname()[0])
        finally:
            probe.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in trouvees:
                trouvees.append(ip)
    except Exception:
        pass
    return trouvees


def est_adresse_privee(hote: str) -> bool:
    """True si l'adresse appartient a un reseau local (RFC 1918) ou a la machine."""
    try:
        import ipaddress
        a = ipaddress.ip_address(str(hote).strip())
    except Exception:
        return False
    if a.is_loopback or a.is_link_local:
        return True
    import ipaddress as _ip
    return any(a in _ip.ip_network(b) for b in _BLOCS_PRIVES)


def verifier_adresse_serveur(hote: str) -> tuple:
    """
    Examine l'adresse saisie AVANT toute tentative de connexion.

    Retourne (niveau, message, suggestion) ou niveau vaut :
        "ok"      — rien a signaler
        "attention" — l'adresse est douteuse, la connexion echouera sans doute
        "erreur"  — l'adresse est inutilisable telle quelle

    `suggestion` est une adresse corrigee quand on peut la deviner, sinon "".
    """
    h = (hote or "").strip()
    if not h:
        return ("erreur", "Aucune adresse saisie.", "")

    try:
        import ipaddress
        ipaddress.ip_address(h)
    except Exception:
        # Un nom de machine reste possible sur un domaine ; on n'interdit pas.
        return ("ok", "", "")

    locales = [x for x in _adresses_locales() if est_adresse_privee(x)]

    if not est_adresse_privee(h):
        # Cas le plus courant : une faute de frappe dans un 192.168.x.x. On
        # cherche l'adresse locale dont elle ne differe que d'un caractere.
        for mienne in locales:
            a, b = h.split("."), mienne.split(".")
            if len(a) == len(b) == 4:
                differents = [i for i in range(4) if a[i] != b[i]]
                if len(differents) == 1:
                    i = differents[0]
                    # meme longueur et un seul chiffre change => faute de frappe
                    if len(a[i]) == len(b[i]) and sum(
                            1 for x, y in zip(a[i], b[i]) if x != y) == 1:
                        propose = ".".join(
                            b[:i] + [b[i]] + a[i + 1:]) if i < 3 else mienne
                        propose = ".".join(
                            [b[j] if j <= i else a[j] for j in range(4)])
                        return ("erreur",
                                f"{h} n'est pas une adresse de réseau local. "
                                f"Cet ordinateur est sur le réseau {mienne}. "
                                f"Vouliez-vous écrire {propose} ?",
                                propose)
        return ("erreur",
                f"{h} n'est pas une adresse de réseau local. Une adresse de "
                f"cabinet commence par 192.168., 10. ou 172.16. à 172.31."
                + (f" Cet ordinateur est sur le réseau {locales[0]}."
                   if locales else ""),
                "")

    # L'adresse est privee : est-elle sur le MEME sous-reseau que nous ?
    if locales:
        prefixe = ".".join(h.split(".")[:3])
        miens = {".".join(x.split(".")[:3]) for x in locales}
        if prefixe not in miens:
            autres = ", ".join(sorted(miens))
            return ("attention",
                    f"{h} n'est pas sur le même réseau que cet ordinateur "
                    f"({autres}.x). Les deux machines doivent être sur le même "
                    f"Wi-Fi ou le même routeur.",
                    "")
    return ("ok", "", "")


def generate_db_token() -> str:
    """A shared secret for the office LAN. Readable enough to be typed once."""
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no O/0, no I/1
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5))
                    for _ in range(4))


def network_mode() -> str:
    return load_network_config().get("mode", MODE_STANDALONE)


def is_workstation() -> bool:
    return network_mode() == MODE_WORKSTATION


def local_ip_addresses() -> list:
    """The addresses a workstation could be pointed at. Best effort."""
    out = []
    try:
        import socket as _s
        hostname = _s.gethostname()
        for info in _s.getaddrinfo(hostname, None, _s.AF_INET):
            ip = info[4][0]
            if ip not in out and not ip.startswith("127."):
                out.append(ip)
    except Exception:
        # (c) Safe: this only populates a hint in Paramètres.
        pass
    return out


# ── API keys, stored separately per provider ──────────────────────────────
# Gemini accepts a comma-separated pool of keys; OpenAI takes a single key.
# Keeping one file per provider means switching provider no longer sends the
# wrong credential to the wrong service.
KEYS_FILE_PATH = DATA_DIR / "saved_api_keys.txt"              # gemini (legacy name, kept for continuity)
OPENAI_KEYS_FILE_PATH = DATA_DIR / "saved_openai_api_key.txt"

_PROVIDER_FILES = {
    "gemini": KEYS_FILE_PATH,
    "openai": OPENAI_KEYS_FILE_PATH,
}
_PROVIDER_ENV = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


AI_PREFS_FILE_PATH = DATA_DIR / "ai_engine.txt"

_VALID_PROVIDERS = ("gemini", "openai")
_DEFAULT_MODEL = {"gemini": "gemini-3.6-flash", "openai": "gpt-4o"}


def load_ai_engine():
    """
    Returns the saved (provider, model) tuple for the AI engine.

    Persisted because the engine is configured on the Settings page while the Scanner
    page is the one that uses it; without this the Scanner would fall back to Gemini
    on every restart no matter what was chosen.
    """
    try:
        if AI_PREFS_FILE_PATH.exists():
            raw = AI_PREFS_FILE_PATH.read_text(encoding="utf-8").strip()
            parts = [p.strip() for p in raw.split("|", 1)]
            provider = parts[0].lower() if parts and parts[0] else "gemini"
            if provider not in _VALID_PROVIDERS:
                provider = "gemini"
            model = parts[1] if len(parts) > 1 and parts[1] else _DEFAULT_MODEL[provider]
            if provider == "gemini" and model not in ("gemini-3.6-flash", "gemini-2.5-flash"):
                model = "gemini-3.6-flash"
                save_ai_engine("gemini", "gemini-3.6-flash")
            return provider, model
    except Exception as read_err:
        print(f"[CONFIG] could not read the AI engine preference: {read_err}",
              file=sys.stderr)
    return "gemini", _DEFAULT_MODEL["gemini"]


def save_ai_engine(provider: str, model: str = ""):
    """Persists the chosen provider and model."""
    try:
        provider = (provider or "gemini").lower()
        if provider not in _VALID_PROVIDERS:
            provider = "gemini"
        model = (model or _DEFAULT_MODEL[provider]).strip()
        AI_PREFS_FILE_PATH.write_text(f"{provider}|{model}", encoding="utf-8")
        return True
    except Exception as write_err:
        # (b) Returning the outcome lets the screen say the choice was not kept.
        print(f"[CONFIG] could not save the AI engine preference: {write_err}",
              file=sys.stderr)
        return False


# ── API keys at rest ─────────────────────────────────────────────────────────
# These were written to disk as plain text. Anyone with the machine -- a
# secretary, a technician, whoever borrows the laptop -- could open the file in
# Notepad and read a working key that bills to the office's account.
#
# They are now sealed with Windows DPAPI, which encrypts under the signed-in
# Windows account: another account on the same machine, or the file copied to a
# different machine, cannot decrypt it. Where DPAPI is unavailable the value is
# still obfuscated rather than left as readable text, and that weaker state is
# recorded so Paramètres can say so honestly.

_KEYSTORE_MAGIC = "ZKEY1:"          # DPAPI-sealed
_KEYSTORE_MAGIC_B64 = "ZKEY0:"      # obfuscated fallback


def keystore_is_encrypted() -> bool:
    """True when this machine can seal keys under the Windows account."""
    try:
        import win32crypt  # noqa: F401
        return True
    except Exception:
        return False


def _seal(plain: str) -> str:
    """Encrypts a key blob for storage. Never raises."""
    try:
        import win32crypt, base64
        blob = win32crypt.CryptProtectData(plain.encode("utf-8"),
                                           "CabinetNotarialZarai API keys",
                                           None, None, None, 0)
        return _KEYSTORE_MAGIC + base64.b64encode(blob).decode("ascii")
    except Exception:
        try:
            import base64
            return _KEYSTORE_MAGIC_B64 + base64.b64encode(
                plain.encode("utf-8")).decode("ascii")
        except Exception:
            # (b) Refusing to store is worse than storing: the notary would lose
            # the key on restart with no explanation. Fall back to the old form.
            return plain


def _unseal(stored: str) -> str:
    """Decrypts whatever form the file is in, including the old plain text."""
    stored = (stored or "").strip()
    if not stored:
        return ""
    if stored.startswith(_KEYSTORE_MAGIC):
        try:
            import win32crypt, base64
            blob = base64.b64decode(stored[len(_KEYSTORE_MAGIC):])
            return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode("utf-8")
        except Exception as e:
            print(f"[CONFIG] could not decrypt the stored API keys: {e}", file=sys.stderr)
            return ""
    if stored.startswith(_KEYSTORE_MAGIC_B64):
        try:
            import base64
            return base64.b64decode(stored[len(_KEYSTORE_MAGIC_B64):]).decode("utf-8")
        except Exception:
            return ""
    # A file written by an older build: plain text. Readable, and re-sealed on
    # the next save.
    return stored


def load_saved_api_keys(provider: str = "gemini") -> str:
    """Loads the saved API key(s) for one provider so they survive restarts."""
    provider = (provider or "gemini").lower()
    path = _PROVIDER_FILES.get(provider, KEYS_FILE_PATH)
    try:
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                plain = _unseal(content)
                # An old plain-text file is upgraded in place the first time it
                # is read, so an existing install stops being readable too.
                if plain and not content.startswith((_KEYSTORE_MAGIC, _KEYSTORE_MAGIC_B64)):
                    try:
                        path.write_text(_seal(plain), encoding="utf-8")
                    except Exception:
                        # (c) Safe: the key still works this session; the upgrade
                        # is retried on the next read or save.
                        pass
                return plain
    except Exception as read_err:
        # (b) An unreadable key file silently means "no AI configured", which the
        # Scanner then reports as a missing key rather than a broken file.
        print(f"[CONFIG] could not read the saved API keys: {read_err}",
              file=sys.stderr)
    return os.environ.get(_PROVIDER_ENV.get(provider, "GEMINI_API_KEY"), "").strip()


def save_api_keys(keys_str: str, provider: str = "gemini"):
    """Persists the API key(s) for one provider. Empty input clears the stored value."""
    provider = (provider or "gemini").lower()
    path = _PROVIDER_FILES.get(provider, KEYS_FILE_PATH)
    try:
        if keys_str is None:
            return
        cleaned = keys_str.strip()
        if cleaned:
            path.write_text(_seal(cleaned), encoding="utf-8")
        elif path.exists():
            path.unlink()
        return True
    except Exception as write_err:
        # (a)/(b) The notary types API keys and presses nothing else; if the write
        # fails the keys are gone on the next launch. The caller now gets False and
        # tells them.
        print(f"[CONFIG] could not save the API keys: {write_err}", file=sys.stderr)
        return False
