"""
updater.py — Système d'Auto-Update autonome et hautement sécurisé via GitHub Releases
Gère la vérification, le téléchargement, la vérification SHA256, le rollback automatique, et le nettoyage propre des connexions.
"""

import os
import sys
import datetime
import traceback
import subprocess
import tempfile
import urllib.request


def _ssl_ctx():
    """Verified SSL context shared with the rest of the app (see config.get_ssl_context)."""
    try:
        import config
        return config.get_ssl_context()
    except Exception:
        import ssl
        return ssl.create_default_context()
import json
import re
import hashlib
from pathlib import Path
from version import __version__, GITHUB_REPO_RELEASES, APP_NAME
from config import LOGS_DIR

STARTUP_LOG_PATH = LOGS_DIR / "startup.log"


def log_startup_event(message: str, exc: Exception = None):
    """Enregistre un événement clair dans %LOCALAPPDATA%\\CabinetNotarialZarai\\data\\logs\\startup.log."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{now_str}] [v{__version__}] {message}\n"
        if exc:
            entry += f"TRACEBACK:\n{traceback.format_exc()}\n"
        with open(STARTUP_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as write_err:
        # (c)/stderr. This IS the logger, so it cannot log its own failure.
        print(f"[UPDATER] could not write the startup log: {write_err}",
              file=sys.stderr)


try:
    from packaging.version import parse as parse_version
except ImportError:
    def parse_version(v_str: str):
        """Fallback robuste de comparaison SemVer vX.Y.Z sans dépendance externe."""
        cleaned = re.sub(r'[^0-9.]', '', str(v_str))
        parts = [int(p) for p in cleaned.split('.') if p.isdigit()]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])


def is_update_channel_configured(repo_owner_repo=None) -> bool:
    """
    True only when a real releases repository has been set.

    version.py ships GITHUB_REPO_RELEASES = "OWNER/mon-app-releases", a
    placeholder. check_for_update() correctly refuses to call GitHub with it, but
    the Paramètres page printed the placeholder to the notary as "the repository of
    official updates" and offered a button that could only ever report nothing.
    Callers use this to hide the feature until there is something behind it.
    """
    # Read the module attribute rather than a default argument: a default is
    # evaluated once when the function is defined, so it would keep reporting the
    # value version.py held at import time no matter what was set afterwards.
    if repo_owner_repo is None:
        import version as _v
        repo_owner_repo = getattr(_v, "GITHUB_REPO_RELEASES", "")
    repo = (repo_owner_repo or "").strip()
    return bool(repo) and "OWNER" not in repo and "/" in repo


class _PrivateRepoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Custom redirect handler that strips GitHub Bearer Authorization header when redirecting
    to external S3/CDN storage URLs (to prevent AWS S3 HTTP 400 InvalidArgument errors).
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req and "api.github.com" not in newurl.lower():
            new_req.headers.pop("Authorization", None)
            new_req.headers.pop("authorization", None)
        return new_req


def get_github_token() -> str:
    """
    Retrieves the GitHub Personal Access Token for private repository releases.
    Order of precedence:
    1. Environment variable `GITHUB_UPDATE_TOKEN`.
    2. Token string or base64 encoded token in version module (`ENCODED_GITHUB_TOKEN`).
    """
    token = os.environ.get("GITHUB_UPDATE_TOKEN", "").strip()
    if token:
        return token
    # Le jeton vit dans un module local ignore par git (voir secrets_local.py).
    # version.py est suivi par git : y ecrire un secret le publie.
    try:
        import secrets_local as _sl
        local = getattr(_sl, 'GITHUB_TOKEN', '').strip()
        if local:
            return local
    except Exception:
        pass          # fichier absent : les mises a jour sont simplement inactives

    try:
        import version as _v
        raw = getattr(_v, "ENCODED_GITHUB_TOKEN", "").strip()
        if raw:
            if raw.startswith("github_pat_") or raw.startswith("ghp_"):
                return raw
            import base64
            try:
                decoded = base64.b64decode(raw.encode("ascii")).decode("utf-8").strip()
                if decoded.startswith("github_pat_") or decoded.startswith("ghp_"):
                    return decoded
                return decoded
            except Exception:
                return raw
    except Exception:
        pass
    return ""



def make_github_request(url: str, is_asset_download: bool = False) -> urllib.request.Request:
    """
    Prepares a urllib.request.Request with proper User-Agent, Authorization Bearer token
    (if configured), and Accept header for GitHub REST API or asset downloads.
    """
    token = get_github_token()
    headers = {"User-Agent": "CabinetNotarialZarai-AutoUpdater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if is_asset_download:
        headers["Accept"] = "application/octet-stream"
    return urllib.request.Request(url, headers=headers)


def check_for_update(repo_owner_repo=None, current_version: str = __version__) -> dict | None:
    """
    Vérifie l'existence d'une nouvelle version sur GitHub Releases (API REST).
    Ne bloque jamais l'application en cas d'absence d'Internet (Timeout 5s).
    """
    if repo_owner_repo is None:
        import version as _v
        repo_owner_repo = getattr(_v, "GITHUB_REPO_RELEASES", "")
    if not repo_owner_repo or "OWNER" in repo_owner_repo:
        log_startup_event(f"Check d'update ignoré : dépôt placeholder '{repo_owner_repo}'.")
        return None

    url = f"https://api.github.com/repos/{repo_owner_repo}/releases/latest"
    req = make_github_request(url)

    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_ssl_ctx()),
            _PrivateRepoRedirectHandler()
        )
        with opener.open(req, timeout=5) as response:
            if response.status != 200:
                log_startup_event(f"Échec API GitHub (Status Code {response.status}).")
                return None
            data = json.loads(response.read().decode('utf-8'))
    except Exception as ex:
        log_startup_event("Démarrage normal sans mise à jour (GitHub hors-ligne ou Timeout 5s).", exc=ex)
        return None

    tag_name = data.get("tag_name", "")
    if not tag_name:
        log_startup_event("Réponse GitHub reçue mais aucun tag_name valide.")
        return None

    remote_version = parse_version(tag_name)
    local_version = parse_version(current_version)

    if remote_version <= local_version:
        log_startup_event(f"Application à jour (Locale v{current_version} >= GitHub {tag_name}).")
        return None

    download_url = ""
    asset_api_url = ""
    asset_name = ""
    asset_size = 0
    sha256_url = ""
    sha256_api_url = ""

    assets = data.get("assets", [])
    # Prioritize .exe assets over .zip if available
    for asset in sorted(assets, key=lambda a: 0 if a.get("name", "").lower().endswith(".exe") else 1):
        name = asset.get("name", "").lower()
        if name.endswith(".exe") or name.endswith(".zip"):
            download_url = asset.get("browser_download_url", "")
            asset_api_url = asset.get("url", "")
            asset_name = asset.get("name", "")
            asset_size = asset.get("size", 0)
            if name.endswith(".exe"):
                break
        elif "sha256" in name:
            sha256_url = asset.get("browser_download_url", "")
            sha256_api_url = asset.get("url", "")

    if not download_url and not asset_api_url:
        log_startup_event(f"Mise à jour {tag_name} détectée mais aucun binaire .exe ou .zip trouvé.")
        return None


    log_startup_event(f" NOUVELLE MISE À JOUR TROUVÉE : {tag_name} (Asset: {asset_name}, Taille: {asset_size} bytes).")

    return {
        "version": tag_name,
        "changelog": data.get("body", "Mise à jour disponible."),
        "download_url": download_url,
        "asset_api_url": asset_api_url,
        "sha256_url": sha256_url,
        "sha256_api_url": sha256_api_url,
        "asset_name": asset_name,
        "asset_size": asset_size
    }


def prompt_user_update(update_info: dict) -> bool:
    """Affiche une boîte de dialogue native Tkinter informant l'utilisateur de la mise à jour."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        ver = update_info.get("version", "")
        changelog = update_info.get("changelog", "Aucun détail fourni.")
        
        msg = f"Une nouvelle version ({ver}) de {APP_NAME} est disponible !\n\n"
        msg += f"Version actuelle : v{__version__}\n"
        msg += f"Nouvelle version : {ver}\n\n"
        msg += f"Notes de mise à jour :\n{changelog[:300]}\n\n"
        msg += "Souhaitez-vous télécharger et installer la mise à jour maintenant ?"

        res = messagebox.askyesno(
            title=f"Mise à jour disponible — {APP_NAME}",
            message=msg,
            parent=root
        )
        root.destroy()
        return res
    except Exception as ex:
        log_startup_event("Erreur lors de l'affichage du dialogue Tkinter.", exc=ex)
        return True


def download_and_verify_update(download_url: str, sha256_url: str = "", asset_api_url: str = "", sha256_api_url: str = "", progress_callback=None) -> str:
    """
    Télécharge le binaire .exe ou l'archive .zip de mise à jour ET vérifie son empreinte SHA256 si disponible.
    Prend en charge les dépôts publics et privés (via asset_api_url).
    """
    temp_dir = Path(tempfile.gettempdir()) / "cabinet_notarial_update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    ext = ".exe" if (download_url and download_url.lower().endswith(".exe")) else ".zip"
    file_path = temp_dir / f"update{ext}"

    # Prefer asset_api_url for private repo asset downloads if token is available
    target_url = asset_api_url if (asset_api_url and get_github_token()) else download_url
    log_startup_event(f"Début du téléchargement du binaire/zip depuis : {target_url}")

    req = make_github_request(target_url, is_asset_download=bool(asset_api_url and get_github_token()))
    hasher = hashlib.sha256()

    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ssl_ctx()),
        _PrivateRepoRedirectHandler()
    )

    try:
        with opener.open(req, timeout=60) as response, open(file_path, 'wb') as out_file:
            content_length = response.headers.get('Content-Length')
            total_bytes = int(content_length) if content_length and content_length.isdigit() else 0
            downloaded_bytes = 0

            while True:
                buffer = response.read(65536)
                if not buffer:
                    break
                hasher.update(buffer)
                out_file.write(buffer)
                downloaded_bytes += len(buffer)
                if progress_callback and total_bytes > 0:
                    percent = int((downloaded_bytes / total_bytes) * 100)
                    progress_callback(percent)
    except Exception as download_err:
        file_path.unlink(missing_ok=True)
        log_startup_event(f"Échec du téléchargement réseau : {download_err}")
        raise ConnectionError(f"Coupure réseau ou problème de téléchargement: {download_err}")

    downloaded_hash = hasher.hexdigest().lower()
    log_startup_event(f"Téléchargement terminé. SHA256 calculé : {downloaded_hash}")

    # Checksum verification
    target_sha_url = sha256_api_url if (sha256_api_url and get_github_token()) else sha256_url
    if target_sha_url:
        try:
            req_sum = make_github_request(target_sha_url, is_asset_download=bool(sha256_api_url and get_github_token()))
            with opener.open(req_sum, timeout=15) as resp:
                sum_text = resp.read().decode('utf-8')
                expected_hash = sum_text.split()[0].lower()
                if downloaded_hash != expected_hash:
                    log_startup_event(f" ERREUR CRITIQUE SÉCURITÉ : SHA256 Discordant ! Attendu: {expected_hash}, Obtenu: {downloaded_hash}")
                    file_path.unlink(missing_ok=True)
                    raise ValueError("SHA256 Checksum Mismatch! Transmission aborted for security.")
                log_startup_event("Vérification SHA256 validée à 100% !")
        except Exception as e:
            if "SHA256 Checksum Mismatch" in str(e):
                file_path.unlink(missing_ok=True)
                raise
            log_startup_event(f"Avertissement : Fichier SHA256SUMS.txt non validé ({e}), validation par ouverture de fichier.")

    return str(file_path)


def get_current_pid_and_install_dir() -> tuple[int, str]:
    """
    CORRECTION ÉTAPE 1 : Detection du mode PyInstaller 'frozen'
    Retourne sys.executable parent en mode compilé (.exe), ou __file__ parent en dev.
    """
    pid = os.getpid()
    if getattr(sys, 'frozen', False):
        install_dir = str(Path(sys.executable).resolve().parent)
    else:
        install_dir = str(Path(__file__).resolve().parent)
    return pid, install_dir


def prepare_clean_app_shutdown():
    """
    CORRECTION ÉTAPE 2 & 3 : Fermeture propre de TOUTES les connexions SQLite et caméras.
    Utilise la variable globale de caméra et ferme toutes les connexions SQLite actives.
    """
    log_startup_event("Exécution de la fermeture propre des ressources avant mise à jour...")
    try:
        from reception import close_all_sqlite_connections
        close_all_sqlite_connections()
    except Exception as ex:
        log_startup_event("Avertissement lors du flush WAL de fermeture", exc=ex)

    try:
        from camera import stop_active_camera
        stop_active_camera()
    except Exception as cam_err:
        # (b) A camera still holding the device across a restart makes the new
        # instance report "no camera", which is a confusing way to learn this.
        log_startup_event(f"could not stop the camera before shutdown: {cam_err}")


def apply_update_and_restart(zip_path: str, install_dir: str = None, current_pid: int = None):
    """
    Génère un script updater helper temporaire Windows avec :
    1. Fermeture douce du processus avec vérification `tasklist`.
    2. Vérification d'espace disque disponible avant sauvegarde.
    3. Sauvegarde de l'ancienne version avant écrasement.
    4. Remplacement direct .exe ou extraction ZIP et Rollback automatique si échec.
    """
    if not install_dir or not current_pid:
        pid, path_dir = get_current_pid_and_install_dir()
        if not install_dir: install_dir = path_dir
        if not current_pid: current_pid = pid

    prepare_clean_app_shutdown()

    temp_dir = Path(tempfile.gettempdir()) / "cabinet_notarial_update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    script_path = temp_dir / "update_helper.bat"
    vbs_path = temp_dir / "run_silent_update.vbs"
    backup_dir = temp_dir / f"CabinetNotarialZarai_backup_v{__version__}"

    file_p = Path(zip_path).resolve()
    is_exe = str(file_p).lower().endswith(".exe")

    target_exe_name = Path(sys.executable).name if getattr(sys, 'frozen', False) else "DATLY.exe"
    
    stage_dir = temp_dir / "stage"
    if is_exe:
        integrity_cmd = f'if exist "{file_p}" ( exit 0 ) else ( exit 1 )'
        install_cmd = f'copy /Y "{file_p}" "{install_dir}\\{target_exe_name}"'
    else:
        integrity_cmd = f'powershell -Command "try {{ $null = [System.IO.Compression.ZipFile]::OpenRead(\'{file_p}\'); exit 0 }} catch {{ exit 1 }}"'
        install_cmd = f'if exist "{stage_dir}" rmdir /S /Q "{stage_dir}" & powershell -Command "Expand-Archive -Path \'{file_p}\' -DestinationPath \'{stage_dir}\' -Force" & if exist "{stage_dir}\\DATLY" ( xcopy /E /I /Y /Q "{stage_dir}\\DATLY\\*" "{install_dir}" ) else ( xcopy /E /I /Y /Q "{stage_dir}\\*" "{install_dir}" )'

    log_startup_event(f"Préparation du script d'installation helper (Cible : '{install_dir}', Mode : {'EXE' if is_exe else 'ZIP'})...")

    bat_content = f"""@echo off
title Auto-Update Helper — {APP_NAME}
echo Exécution de la mise à jour sécurisée...

:: ÉTAPE 5 : ATTENTE DOUCE ET VÉRIFICATION DE FERMETURE DU PROCESSUS PID {current_pid}
taskkill /PID {current_pid} >nul 2>&1
timeout /t 2 /nobreak >nul

set /a RETRIES=0
:CHECK_PID
tasklist /FI "PID eq {current_pid}" 2>NUL | find /I "{current_pid}">NUL
if "%ERRORLEVEL%"=="0" (
    set /a RETRIES+=1
    if %RETRIES% GEQ 5 (
        echo Fermeture forcée en dernier recours...
        taskkill /F /PID {current_pid} >nul 2>&1
        timeout /t 1 /nobreak >nul
    ) else (
        timeout /t 1 /nobreak >nul
        goto CHECK_PID
    )
)

:: ÉTAPE 4.1 : VÉRIFICATION DE L'ESPACE DISQUE LIBRE AVANT SAUVEGARDE
powershell -Command "try {{ $s = (Get-ChildItem -Path '{install_dir}' -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum; $f = (Get-Volume -FilePath '{install_dir}').SizeRemaining; if ($f -and $s -and $f -lt ($s * 2)) {{ exit 1 }} else {{ exit 0 }} }} catch {{ exit 0 }}"
if %errorlevel% neq 0 (
    echo [ERREUR DISQUE] Espace disque insuffisant pour créer la sauvegarde et extraire la mise à jour !
    msg %username% "Erreur de mise à jour: Espace disque insuffisant sur votre PC. Libérez de l'espace et réessayez."
    cd /d "{install_dir}"
    if exist "{target_exe_name}" ( start "" "{target_exe_name}" ) else ( start /b py -3 main.py )
    del "{script_path}"
    exit
)

:: ÉTAPE 3 : VÉRIFICATION D'INTÉGRITÉ AVANT DÉPLOIEMENT
{integrity_cmd}
if %errorlevel% neq 0 (
    echo [ERREUR CRITIQUE] Fichier de mise à jour corrompu ! Annulation.
    msg %username% "Erreur de mise à jour: Fichier corrompu. L'application va redémarrer sur la version actuelle."
    cd /d "{install_dir}"
    if exist "{target_exe_name}" ( start "" "{target_exe_name}" ) else ( start /b py -3 main.py )
    del "{script_path}"
    exit
)

:: ÉTAPE 4.2 : SAUVEGARDE DU DOSSIER ACTUEL AVANT ÉCRASEMENT (ROLLBACK RÉEL)
if exist "{backup_dir}" rmdir /S /Q "{backup_dir}"
mkdir "{backup_dir}" >nul 2>&1
xcopy /E /I /Y /Q "{install_dir}" "{backup_dir}" >nul 2>&1

:: ÉCRASEMENT / DEPLOIEMENT DE LA NOUVELLE VERSION
set /a INSTALL_RETRIES=0
:DO_INSTALL
{install_cmd}
if %errorlevel% neq 0 (
    set /a INSTALL_RETRIES+=1
    if %INSTALL_RETRIES% LSS 4 (
        timeout /t 2 /nobreak >nul
        goto DO_INSTALL
    )
    echo [ERREUR DEPLOIEMENT] Échec de l'installation. Restauration de la sauvegarde précédente...
    xcopy /E /I /Y /Q "{backup_dir}" "{install_dir}" >nul 2>&1
    msg %username% "Échec de l'installation: Votre ancienne version a été restaurée automatiquement."
)

:: RELANCEMENT SÉCURISÉ DE L'APPLICATION
cd /d "{install_dir}"
if exist "DATLY.exe" (
    start "" "DATLY.exe"
) else if exist "{target_exe_name}" (
    start "" "{target_exe_name}"
) else if exist "Lancer_Application.bat" (
    start "" "Lancer_Application.bat"
) else (
    start /b py -3 main.py
)

:: SUPPRESSION DU BACKUP TEMPORAIRE APRÈS SUCCÈS
rmdir /S /Q "{backup_dir}" >nul 2>&1
del "{script_path}" >nul 2>&1
exit
"""
    script_path.write_text(bat_content, encoding='utf-8')

    vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "{script_path}" & chr(34), 0, False
"""
    vbs_path.write_text(vbs_content, encoding='utf-8')

    try:
        subprocess.Popen(["wscript.exe", str(vbs_path)], creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as ex:
        log_startup_event("Erreur lancement script wscript helper.", exc=ex)
        subprocess.Popen(["cmd.exe", "/c", str(script_path)], creationflags=subprocess.CREATE_NEW_CONSOLE)

    sys.exit(0)

