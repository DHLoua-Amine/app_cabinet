import sys
import shutil
import os
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

app_data = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\amin\AppData\Local")) / "CabinetNotarialZarai"
backup_data = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\amin\AppData\Local")) / "CabinetNotarialZarai_dev_backup"

if app_data.exists():
    if backup_data.exists():
        shutil.rmtree(backup_data, ignore_errors=True)
    app_data.rename(backup_data)
    print(f"✅ Ancienne base de données sauvegardée dans : '{backup_data}'")
    print("✅ Le dossier 'CabinetNotarialZarai' est maintenant totalement vierge (Mode Nouveau PC / Client) !")
else:
    print("✅ Le dossier 'CabinetNotarialZarai' est déjà totalement propre (Mode Nouveau PC).")
