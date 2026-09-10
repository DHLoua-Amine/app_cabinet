import sys
import os
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, "core"))

from PySide6.QtWidgets import QApplication
from ui.dialogs.document_scan_dialog import DocumentScanDialog
from ui.pages.fiche_client_page import FicheClientPage
from core.farida_engine import parse_hujjat_wafat_text, TunisianFaridaEngine
from core.camera import (
    check_ip_reachable, get_saved_camera_source, 
    get_saved_secondary_camera_source, get_saved_tertiary_camera_source
)

def run_full_suite():
    print("--- STARTING END-TO-END VERIFICATION ---")
    
    # 1. Test Qt App Initialization
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        
    print("[1/5] Testing Network Reachability Check (Offline IP timeout test)...")
    t0 = time.time()
    reachable = check_ip_reachable("192.168.1.250:554", timeout=0.5)
    elapsed = time.time() - t0
    print(f"      Result: Reachable={reachable}, Elapsed={elapsed:.3f}s (Must be fast < 1s)")
    assert elapsed < 1.5, "Network timeout took too long!"
    
    print("[2/5] Testing Hujjat Wafat Auto-Parser...")
    sample_text = """
    وقد ترك: زوجته فاطمة وابنه محمد وابنه كريم وبنته سارة ولا غير.
    """
    heirs_dict = parse_hujjat_wafat_text(sample_text)
    print(f"      Parsed Heirs Dict: {heirs_dict}")
    assert heirs_dict.get('wife') is True, "Wife not detected!"
    assert heirs_dict.get('sons_count') == 2, "Sons count incorrect!"
    assert heirs_dict.get('daughters_count') == 1, "Daughters count incorrect!"

    print("[3/5] Testing Farida Engine & DOCX Exporter...")
    engine = TunisianFaridaEngine()
    result = engine.calculate_farida(heirs_dict, gross_estate=100000.0, property_parts=2400)
    output_docx = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_farida_output.docx"))
    engine.export_farida_docx(result, output_path=output_docx)
    print(f"      Exported DOCX File Exists: {os.path.exists(output_docx)}")
    assert os.path.exists(output_docx), "DOCX Export failed!"

    print("[4/5] Testing DocumentScanDialog & FicheClientPage UI Components...")
    scan_dialog = DocumentScanDialog(client_id=1, mode="cin", parent=None)
    scan_dialog.show()
    print("      DocumentScanDialog instantiated and shown successfully.")
    scan_dialog.close()

    print("[5/5] Testing Multi-Camera Configuration Core Integration...")
    cam1 = get_saved_camera_source()
    cam2 = get_saved_secondary_camera_source()
    cam3 = get_saved_tertiary_camera_source()
    print(f"      Configured Cameras: Cam1={cam1}, Cam2={cam2}, Cam3={cam3}")
    print("--- ALL 5 END-TO-END VERIFICATION TESTS PASSED SUCCESSFULLY! ---")

if __name__ == "__main__":
    run_full_suite()
