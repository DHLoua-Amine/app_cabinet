import os, sys, socket

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('core'))

import core.config as config
import core.reception as reception
from ui.dialogs.server_connect_dialog import ServerConnectDialog

def test_recovery():
    print("--- TESTING RECOVERY & NO DEAD-END CRASHES ---")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Test 1: Test connection function in dialog
    dlg = ServerConnectDialog(current_ip="127.0.0.1", current_port=8765, current_token="test", lang="ar")
    print(f"Dialog created OK with IP={dlg.selected_ip}, Port={dlg.selected_port}, Token={dlg.selected_token}")
    assert dlg.selected_ip == "127.0.0.1"
    assert dlg.selected_port == 8765

    # Test 2: Mode switching to standalone
    config.save_network_config({"mode": config.MODE_STANDALONE})
    assert config.network_mode() == config.MODE_STANDALONE, "save_network_config must set standalone mode"
    print("Mode switching to standalone verified!")

    # Test 3: Initialize DB safely in standalone mode
    reception.startup_initialise()
    print("Startup initialise completed with ZERO fatal crashes!")

    print("--- ALL NO-CRASH TESTS PASSED SUCCESSFULLY ---")

if __name__ == "__main__":
    test_recovery()
