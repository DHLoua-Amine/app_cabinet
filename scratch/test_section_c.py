import sys
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication

workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"

for path in [str(workspace_dir), str(core_dir)]:
    if path not in sys.path:
        sys.path.insert(0, path)

os.chdir(workspace_dir)

app = QApplication.instance()
if not app:
    app = QApplication([])

import auth
auth.session_state.logged_in = True
auth.session_state.username = "admin"
auth.session_state.role = "ADMIN"

from ui.main_window import MainWindow

win = MainWindow()
print("Nav buttons keys:", list(win.nav_buttons.keys()))
assert "fiche" not in win.nav_buttons, "Fiche should not be in sidebar buttons"

# Test navigating to client fiche from directory
win.open_fiche_client("CLI-2026-001")
print("Current widget page class:", win.content_area.currentWidget().__class__.__name__)
assert win.content_area.currentWidget().__class__.__name__ == "FicheClientPage"
print("SECTION C VERIFICATION SUCCESSFUL: 'fiche' removed from sidebar, deep-link open_fiche_client works flawlessly.")
