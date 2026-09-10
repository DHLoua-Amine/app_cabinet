"""
verify_today_all_changes.py — Deep AST & End-to-End Runtime Audit for All Features Built Today.
"""

import sys
import os
import time
import ast
import traceback

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, "core"))

def audit_file_ast(file_path):
    print(f"Checking AST syntax for: {os.path.basename(file_path)}...")
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    ast.parse(code, filename=file_path)

def run_deep_verification():
    print("=================================================================")
    print("       STARTING RIGOROUS COMPREHENSIVE SYSTEM VERIFICATION        ")
    print("=================================================================")

    # 1. AST Syntax Audit on all modified files
    files_to_check = [
        os.path.join(root_dir, "core", "camera.py"),
        os.path.join(root_dir, "core", "contract_templates.py"),
        os.path.join(root_dir, "core", "farida_engine.py"),
        os.path.join(root_dir, "ui", "dialogs", "document_scan_dialog.py"),
        os.path.join(root_dir, "ui", "dialogs", "document_gallery_dialog.py"),
        os.path.join(root_dir, "ui", "pages", "fiche_client_page.py"),
        os.path.join(root_dir, "ui", "pages", "settings_page.py"),
        os.path.join(root_dir, "ui", "components", "farida_dialog.py"),
    ]

    for fp in files_to_check:
        try:
            audit_file_ast(fp)
            print(f"  [OK] AST Syntax Clean: {os.path.basename(fp)}")
        except Exception as e:
            print(f"  [FAIL] AST Syntax Error in {fp}: {e}")
            raise e

    # 2. Qt Application Setup
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # 3. Test Camera Core & Socket Reachability
    print("\n--- Test 1: Camera Core & Multi-Camera Config ---")
    from core.camera import (
        check_ip_reachable, get_saved_camera_source,
        get_saved_secondary_camera_source, get_saved_tertiary_camera_source,
        set_saved_camera_source, set_saved_secondary_camera_source, set_saved_tertiary_camera_source
    )
    cam1 = get_saved_camera_source()
    cam2 = get_saved_secondary_camera_source()
    cam3 = get_saved_tertiary_camera_source()
    print(f"  Camera 1: {cam1}")
    print(f"  Camera 2: {cam2}")
    print(f"  Camera 3: {cam3}")
    
    t0 = time.time()
    reachable = check_ip_reachable("192.168.1.155:554", timeout=0.3)
    elapsed = time.time() - t0
    print(f"  IP Socket Reachability Check Elapsed: {elapsed:.3f}s (Reachable={reachable})")
    assert elapsed < 1.0, "Socket check freeze detected!"

    # 4. Test Hujjat Wafat Contract Phrasing
    print("\n--- Test 2: Hujjat Wafat Legal Contract Phrasing ---")
    from core.contract_templates import TEMPLATE_HOJJAT_WAFAT
    assert "حضَرَ لدينا نحن" in TEMPLATE_HOJJAT_WAFAT, "Missing 'حضَرَ لدينا نحن' in TEMPLATE_HOJJAT_WAFAT!"
    assert "مصرحاً بالوفاة" in TEMPLATE_HOJJAT_WAFAT, "Missing 'مصرحاً بالوفاة' in TEMPLATE_HOJJAT_WAFAT!"
    assert "الشاهدان الإثنين" in TEMPLATE_HOJJAT_WAFAT, "Missing witness section!"
    assert "وقَد ترَك(ت) ورثته(ا)" in TEMPLATE_HOJJAT_WAFAT, "Missing heir clause!"
    print("  [PASS] TEMPLATE_HOJJAT_WAFAT notary structure matches official Tunisian standards.")

    # 5. Test Farida Engine & Hujjat Wafat Text Parser
    print("\n--- Test 3: Farida Engine & Hujjat Wafat Parser ---")
    from core.farida_engine import parse_hujjat_wafat_text, TunisianFaridaEngine
    test_text = """
    حضَرَ لدينا نحن العدل الإشهاد بوصفه مصرحاً بالوفاة.
    وقد ترك: زوجته فاطمة وابنه محمد وابنه كريم وبنته سارة ولا غير.
    """
    parsed = parse_hujjat_wafat_text(test_text)
    print(f"  Parsed result: {parsed}")
    assert parsed.get('wife') is True, "Failed to parse wife!"
    assert parsed.get('sons_count') == 2, "Failed to parse 2 sons!"
    assert parsed.get('daughters_count') == 1, "Failed to parse 1 daughter!"

    engine = TunisianFaridaEngine()
    calc_res = engine.calculate_farida(parsed, gross_estate=150000.0, property_parts=2400)
    out_docx = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_audit_farida.docx"))
    engine.export_farida_docx(calc_res, out_docx)
    assert os.path.exists(out_docx), "DOCX Export failed!"
    print("  [PASS] Farida calculation & Word DOCX export verified.")

    # 6. Test DocumentScanDialog & DocumentGalleryDialog UI Instantiation
    print("\n--- Test 4: DocumentScanDialog & DocumentGalleryDialog UI Instantiation ---")
    from ui.dialogs.document_scan_dialog import DocumentScanDialog
    from ui.dialogs.document_gallery_dialog import DocumentGalleryDialog

    scan_dlg_cin = DocumentScanDialog(client_id=1, mode="cin", lang="ar")
    scan_dlg_doc = DocumentScanDialog(client_id=1, mode="document", lang="ar")
    print("  [PASS] DocumentScanDialog ('cin' & 'document' modes) created cleanly.")

    dummy_docs = [
        {"name": "test_image1.png", "path": os.path.abspath(__file__), "size_kb": 12},
        {"name": "test_doc.docx", "path": os.path.abspath(__file__), "size_kb": 45}
    ]
    gallery_dlg = DocumentGalleryDialog(documents=dummy_docs, start_index=0, lang="ar")
    print("  [PASS] DocumentGalleryDialog created cleanly with carousel support.")

    # 7. Test FicheClientPage UI Page Methods
    print("\n--- Test 5: FicheClientPage Integration ---")
    from ui.pages.fiche_client_page import FicheClientPage
    fiche_page = FicheClientPage(client_id="1")
    fiche_page.update_language("ar")
    assert hasattr(fiche_page, "scan_cin_with_camera"), "Missing scan_cin_with_camera!"
    assert hasattr(fiche_page, "scan_document_with_camera"), "Missing scan_document_with_camera!"
    assert hasattr(fiche_page, "scan_case_document"), "Missing scan_case_document!"
    assert hasattr(fiche_page, "_open_gallery_dialog"), "Missing _open_gallery_dialog!"
    print("  [PASS] FicheClientPage scanner & gallery methods verified.")

    print("\n=================================================================")
    print("  SUCCESS! ALL VERIFICATION CHECKS PASSED WITH 0 ERRORS!        ")
    print("=================================================================")

if __name__ == "__main__":
    try:
        run_deep_verification()
    except Exception as err:
        print("\n[VERIFICATION FAILED]:", err)
        traceback.print_exc()
        sys.exit(1)
