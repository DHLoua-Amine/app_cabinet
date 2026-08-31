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


def check_for_update(repo_owner_repo=None, current_version: str = __version__) -> dict | None:
    """
    Vérifie l'existence d'une nouvelle version sur GitHub Releases (API publique REST).
    Ne bloque jamais l'application en cas d'absence d'Internet (Timeout 5s).
    """
    if repo_owner_repo is None:
        import version as _v
        repo_owner_repo = getattr(_v, "GITHUB_REPO_RELEASES", "")
    if not repo_owner_repo or "OWNER" in repo_owner_repo:
        log_startup_event(f"Check d'update ignoré : dépôt placeholder '{repo_owner_repo}'.")
        return None

    url = f"https://api.github.com/repos/{repo_owner_repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CabinetNotarialZarai-AutoUpdater"}
    )

    try:
        with urllib.request.urlopen(req, timeout=5, context=_ssl_ctx()) as response:
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
    asset_name = ""
    asset_size = 0
    sha256_url = ""

    assets = data.get("assets", [])
    for asset in assets:
        name = asset.get("name", "").lower()
        if name.endswith(".zip"):
            download_url = asset.get("browser_download_url", "")
            asset_name = asset.get("name", "")
            asset_size = asset.get("size", 0)
        elif "sha256" in name:
            sha256_url = asset.get("browser_download_url", "")

    if not download_url:
        log_startup_event(f"Mise à jour {tag_name} détectée mais aucun binaire .zip trouvé.")
        return None

    log_startup_event(f" NOUVELLE MISE À JOUR TROUVÉE : {tag_name} (Asset: {asset_name}, Taille: {asset_size} bytes).")

    return {
        "version": tag_name,
        "changelog": data.get("body", "Mise à jour disponible."),
        "download_url": download_url,
        "sha256_url": sha256_url,
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


def download_and_verify_update(download_url: str, sha256_url: str = "") -> str:
    """
    Télécharge l'archive .zip de mise à jour ET vérifie son empreinte SHA256 si disponible.
    """
    temp_dir = Path(tempfile.gettempdir()) / "cabinet_notarial_update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = temp_dir / "update.zip"

    log_startup_event(f"Début du téléchargement du zip depuis : {download_url}")

    req = urllib.request.Request(download_url, headers={"User-Agent": "CabinetNotarialZarai-AutoUpdater"})
    hasher = hashlib.sha256()

    with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx()) as response, open(zip_path, 'wb') as out_file:
        while True:
            buffer = response.read(65536)
            if not buffer:
                break
            hasher.update(buffer)
            out_file.write(buffer)

    downloaded_hash = hasher.hexdigest().lower()
    log_startup_event(f"Téléchargement terminé. SHA256 calculé : {downloaded_hash}")

    # Vérification du SHA256 via SHA256SUMS.txt si fourni
    if sha256_url:
        try:
            req_sum = urllib.request.Request(sha256_url, headers={"User-Agent": "CabinetNotarialZarai-AutoUpdater"})
            with urllib.request.urlopen(req_sum, timeout=10, context=_ssl_ctx()) as resp:
                sum_text = resp.read().decode('utf-8')
                expected_hash = sum_text.split()[0].lower()
                if downloaded_hash != expected_hash:
                    log_startup_event(f" ERREUR CRITIQUE SÉCURITÉ : SHA256 Discordant ! Attendu: {expected_hash}, Obtenu: {downloaded_hash}")
                    zip_path.unlink(missing_ok=True)
                    raise ValueError("SHA256 Checksum Mismatch! Transmission aborted for security.")
                log_startup_event("Vérification SHA256 validée à 100% !")
        except Exception as e:
            if "SHA256" in str(e):
                raise
            log_startup_event("Avertissement : Fichier SHA256SUMS.txt introuvable ou illisible sur la release, validation par zipfile::OpenRead.")

    return str(zip_path)


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
    4. Test d'intégrité ZIP et Rollback automatique si échec.
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

    log_startup_event(f"Préparation du script d'installation helper (Dossier Cible : '{install_dir}')...")

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
powershell -Command "$installSize = (Get-ChildItem -Path '{install_dir}' -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum; $freeSpace = (Get-Volume -FilePath '{install_dir}').SizeRemaining; if ($freeSpace -lt ($installSize * 2.5)) {{ exit 1 }} else {{ exit 0 }}"
if %errorlevel% neq 0 (
    echo [ERREUR DISQUE] Espace disque insuffisant pour créer la sauvegarde et extraire la mise à jour !
    msg %username% "Erreur de mise à jour: Espace disque insuffisant sur votre PC. Libérez de l'espace et réessayez."
    cd /d "{install_dir}"
    if exist "CabinetNotarialZarai.exe" ( start "" "CabinetNotarialZarai.exe" ) else ( start /b py -3 -m streamlit run app.py --server.port=8501 )
    del "{script_path}"
    exit
)

:: ÉTAPE 3 : VÉRIFICATION D'INTÉGRITÉ NATIVE POWERSHELL AVANT EXTRACTION
powershell -Command "try {{ $null = [System.IO.Compression.ZipFile]::OpenRead('{zip_path}'); exit 0 }} catch {{ exit 1 }}"
if %errorlevel% neq 0 (
    echo [ERREUR CRITIQUE] Le fichier ZIP téléchargé est corrompu ! Annulation.
    msg %username% "Erreur de mise à jour: Archive corrompue. L'application va redémarrer sur la version actuelle."
    cd /d "{install_dir}"
    if exist "CabinetNotarialZarai.exe" ( start "" "CabinetNotarialZarai.exe" ) else ( start /b py -3 -m streamlit run app.py --server.port=8501 )
    del "{script_path}"
    exit
)

:: ÉTAPE 4.2 : SAUVEGARDE DU DOSSIER ACTUEL AVANT ÉCRASEMENT (ROLLBACK RÉEL)
if exist "{backup_dir}" rmdir /S /Q "{backup_dir}"
mkdir "{backup_dir}" >nul 2>&1
xcopy /E /I /Y /Q "{install_dir}" "{backup_dir}" >nul 2>&1

:: EXTRACTION DE LA NOUVELLE VERSION OVERWRITE
powershell -Command "Expand-Archive -Path '{zip_path}' -DestinationPath '{install_dir}' -Force"
if %errorlevel% neq 0 (
    echo [ERREUR EXTRACTION] Échec de l'extraction. Restauration de la sauvegarde précédente...
    xcopy /E /I /Y /Q "{backup_dir}" "{install_dir}" >nul 2>&1
    msg %username% "Échec d'extraction: Votre ancienne version a été restaurée automatiquement."
)

:: RELANCEMENT SÉCURISÉ DE L'APPLICATION
cd /d "{install_dir}"
if exist "CabinetNotarialZarai.exe" (
    start "" "CabinetNotarialZarai.exe"
) else if exist "Lancer_Application.bat" (
    start "" "Lancer_Application.bat"
) else (
    start /b py -3 -m streamlit run app.py --server.port=8501
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

