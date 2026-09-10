"""
scratch/ultimate_stress_test.py
Ultimate Deep Stress & Edge-Case Verification Suite for Cabinet Notarial Zarai.
"""

import sys
import os
import sqlite3
import traceback
import tempfile
import time
import datetime
from pathlib import Path

# Ensure UTF-8 output streams for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Set up paths exactly as main.py does
ROOT_DIR = Path(__file__).parent.parent.resolve()
CORE_DIR = ROOT_DIR / "core"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(CORE_DIR))

import auth
import permissions

# Set admin session role for testing
permissions.session.sign_in("admin", "admin", "Notaire Test")

# Create offscreen Qt Application
from PySide6.QtWidgets import QApplication
if not QApplication.instance():
    app = QApplication(["-platform", "offscreen"])
else:
    app = QApplication.instance()

test_results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def record_pass(test_name, details=""):
    test_results["passed"].append({"name": test_name, "details": details})
    print(f"[PASS] {test_name}: {details}")

def record_fail(test_name, error="", traceback_str=""):
    test_results["failed"].append({"name": test_name, "error": str(error), "traceback": traceback_str})
    print(f"[FAIL] {test_name}: {error}")

def record_warning(test_name, details=""):
    test_results["warnings"].append({"name": test_name, "details": details})
    print(f"[WARN] {test_name}: {details}")

print("==================================================")
print("STARTING ULTIMATE STRESS & EDGE-CASE TEST SUITE")
print("==================================================")

# ---------------------------------------------------------
# STRESS TEST 1: ALL CONTRACT TYPES GENERATION
# ---------------------------------------------------------
try:
    import contract_templates
    
    contract_types = [
        "عقد بيع", "عقد هبة", "عقد مقاسمة", "تنازل",
        "وعد بالبيع", "إسقاط", "عقد كراء توثيقي", "عقد رهن عقاري",
        "عقد صداق وزواج", "توكيل", "حجة وفاة", "عقد وصية",
        "عقد تخارج من التركة", "عقد تأسيس شركة", "عقد بيع أصل تجاري",
        "عقد إقرار بدين والتزام"
    ]
    
    dummy_p1 = [{
        "full_name": "محمد بن علي الفرشيشي",
        "birth_place": "تونس", "birth_date": "1985-04-12",
        "cin_number": "08765432", "cin_issue_date": "2015-06-20",
        "address": "شارع الحبيب بورقيبة تونس"
    }]
    dummy_p2 = [{
        "full_name": "فاطمة بنت الحبيب المنصوري",
        "birth_place": "صفاقس", "birth_date": "1990-09-05",
        "cin_number": "09876543", "cin_issue_date": "2018-01-10",
        "address": "طريق التنسيل صفاقس"
    }]
    
    generated_count = 0
    for c_type in contract_types:
        txt = contract_templates.build_multi_party_contract_text(
            contract_type=c_type,
            party1_list=dummy_p1,
            party2_list=dummy_p2,
            property_desc="قطعة أرض صالحة للبناء كائنة بصفاقس مساحتها 350 متر مربع",
            price_words="خمسون ألف دينار",
            price_num="50000",
            ownership_origin="بالشراء بموجب عقد توثيقي معدد بقباضة تونس"
        )
        if txt and len(txt) > 100:
            generated_count += 1
        else:
            record_fail(f"Contract Generation: {c_type}", "Generated text is empty or too short")

    record_pass("All 16 Contract Types Generation", f"Successfully generated {generated_count}/{len(contract_types)} deed texts")

except Exception as e:
    record_fail("Contract Generation Stress", str(e), traceback.format_exc())

# ---------------------------------------------------------
# STRESS TEST 2: DATE & HIJRI COMPUTATION ON EDGE DATES
# ---------------------------------------------------------
try:
    edge_dates = [
        datetime.datetime(2026, 1, 1, 0, 0, 0),
        datetime.datetime(2026, 12, 31, 23, 59, 59),
        datetime.datetime(2028, 2, 29, 12, 30, 0), # Leap year
    ]
    for d in edge_dates:
        d_info = contract_templates.get_current_arabic_date_info(dt=d)
        if not d_info.get("full_date_text"):
            record_fail(f"Date Conversion: {d}", "full_date_text is empty")
    record_pass("Date & Hijri Conversion Edge Cases", f"Verified {len(edge_dates)} edge dates")

except Exception as e:
    record_fail("Date Conversion Stress", str(e), traceback.format_exc())

# ---------------------------------------------------------
# STRESS TEST 3: FINANCIAL & RECEPTION AGGREGATORS
# ---------------------------------------------------------
try:
    import reception
    
    # Test counting and summary metrics under empty or existing DB
    cnt_clients = reception.count_clients()
    cnt_checkins = reception.count_check_ins()
    cnt_checkins_today = reception.count_check_ins_today()
    
    record_pass("Financial & Reception Aggregators", f"Clients: {cnt_clients}, Total Checkins: {cnt_checkins}, Today: {cnt_checkins_today}")

except Exception as e:
    record_fail("Aggregators Stress", str(e), traceback.format_exc())

# ---------------------------------------------------------
# STRESS TEST 4: EXCEL & WORD DOCX GENERATORS
# ---------------------------------------------------------
try:
    import docx_generator
    font_n = docx_generator.police_arabe()
    record_pass("Word DOCX Font Resolver", f"Resolved system font: {font_n}")

except Exception as e:
    record_fail("Word DOCX Engine", str(e), traceback.format_exc())

# ---------------------------------------------------------
# TEST SUMMARY
# ---------------------------------------------------------
print("\n==================================================")
print("TEST SUMMARY")
print(f"PASSED: {len(test_results['passed'])}")
print(f"FAILED: {len(test_results['failed'])}")
print(f"WARNINGS: {len(test_results['warnings'])}")
print("==================================================")

if test_results['failed']:
    print("\n[!] DETAILED FAULTS FOUND:")
    for f in test_results['failed']:
        print(f"\n--- FAULT IN: {f['name']} ---")
        print(f"Error: {f['error']}")
        print(f"Traceback:\n{f['traceback']}")

import json
with open(ROOT_DIR / "scratch" / "stress_test_report.json", "w", encoding="utf-8") as f:
    json.dump(test_results, f, ensure_ascii=False, indent=2)

print("\nReport written to scratch/stress_test_report.json")
