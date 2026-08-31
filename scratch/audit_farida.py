import sys
import os
from pathlib import Path

# Add core path
BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

from farida_engine import TunisianFaridaEngine

def run_farida_comprehensive_audit():
    print("=================================================================")
    print("      COMPREHENSIVE AUDIT OF TUNISIAN FARIDA ENGINE & DIALOG     ")
    print("=================================================================")

    engine = TunisianFaridaEngine()
    passed = 0
    failed = 0

    # -------------------------------------------------------------------------
    # TEST 1: Zero Heirs Selected (Boundary Test)
    # -------------------------------------------------------------------------
    try:
        res = engine.calculate_farida(heirs_dict={}, gross_estate=50000)
        assert res["base_origin"] > 0, "Base origin should be valid integer"
        assert isinstance(res["heirs_summary"], list), "Heirs summary should be list"
        print("[PASS] Test 1: Zero Heirs Selected (Handled cleanly, 0 division error)")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 1: Zero Heirs Exception: {e}")
        failed += 1

    # -------------------------------------------------------------------------
    # TEST 2: Deductions Exceed Gross Estate (Negative Protection)
    # -------------------------------------------------------------------------
    try:
        res = engine.calculate_farida(
            heirs_dict={'wife': True, 'sons_count': 2},
            gross_estate=10000,
            funeral_expenses=8000,
            debts=5000
        )
        assert res["net_estate"] == 0.0, f"Net estate should be clamped to 0.0, got {res['net_estate']}"
        for h in res["heirs_summary"]:
            assert h["amount"] == 0.0, "Heir amounts should be 0.0 when net estate is 0"
        print("[PASS] Test 2: Deductions Exceed Gross Estate (Clamped to 0.0 TND cleanly)")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 2: Deductions Exceed Exception: {e}")
        failed += 1

    # -------------------------------------------------------------------------
    # TEST 3: Awl Case (العول - Estate Deficit)
    # Husband + 2 Full Sisters + Mother (Shares: 3/6 + 4/6 + 1/6 = 8/6 -> Base 8)
    # -------------------------------------------------------------------------
    try:
        res = engine.calculate_farida(
            heirs_dict={'husband': True, 'full_sisters_count': 2, 'mother': True},
            gross_estate=24000
        )
        assert res["is_awl"] == True, "Should be marked as Awl case"
        assert res["base_origin"] == 8, f"Awl base origin should be 8, got {res['base_origin']}"
        print("[PASS] Test 3: Awl Case (Awl correctly increased base origin to 8)")
        passed += 1
    except Exception as e:
        sys.stdout.buffer.write(f"[FAIL] Test 3: Awl Case Exception: {e}\n".encode('utf-8'))
        failed += 1

    # -------------------------------------------------------------------------
    # TEST 4: Radd Case (الرد - Estate Surplus to Daughters under Art 143 CSP)
    # 1 Daughter + Mother (Shares: 1/2 + 1/6 = 4/6 -> Remainder 2/6 restored to Daughter)
    # -------------------------------------------------------------------------
    try:
        res = engine.calculate_farida(
            heirs_dict={'daughters_count': 1, 'mother': True},
            gross_estate=60000
        )
        assert res["is_radd"] == True, "Should be marked as Radd case"
        summary_map = {h["heir"]: h["amount"] for h in res["heirs_summary"]}
        # Mother gets 10,000, Daughter gets 50,000
        assert abs(summary_map.get("الأم", 0) - 10000.0) < 0.01, "Mother share incorrect"
        assert abs(summary_map.get("البنت (فرضا ورداً - الفصل 143)", 0) - 50000.0) < 0.01, "Daughter radd share incorrect"
        print("[PASS] Test 4: Radd Case (Radd to Daughters - Article 143 CSP verified)")
        passed += 1
    except Exception as e:
        sys.stdout.buffer.write(f"[FAIL] Test 4: Radd Case Exception: {e}\n".encode('utf-8'))
        failed += 1

    # -------------------------------------------------------------------------
    # TEST 5: Obligatory Bequest (الوصية الواجبة - Art 191 CSP)
    # Predeceased children present (1/3 max cap for grandchildren)
    # -------------------------------------------------------------------------
    try:
        res = engine.calculate_farida(
            heirs_dict={'wife': True, 'sons_count': 2, 'predeceased_children_count': 1},
            gross_estate=90000
        )
        summary_map = {h["heir"]: h["amount"] for h in res["heirs_summary"]}
        bequest_amt = summary_map.get("أولاد الابن/البنت (وصية واجبة - الفصل 191)", 0)
        assert abs(bequest_amt - 30000.0) < 0.01, f"Obligatory bequest should be 30,000 TND (1/3 of 90,000), got {bequest_amt}"
        print("[PASS] Test 5: Obligatory Bequest (Obligatory Bequest - Article 191 CSP verified)")
        passed += 1
    except Exception as e:
        sys.stdout.buffer.write(f"[FAIL] Test 5: Obligatory Bequest Exception: {e}\n".encode('utf-8'))
        failed += 1

    # -------------------------------------------------------------------------
    # TEST 6: Real Estate Mapping (m² and fractional parts)
    # 180 m² and 264,000 parts
    # -------------------------------------------------------------------------
    try:
        res = engine.calculate_farida(
            heirs_dict={'wife': True, 'sons_count': 1, 'daughters_count': 1},
            gross_estate=100000,
            property_area_m2=180.0,
            property_parts=264000.0
        )
        total_m2 = sum(h["area_m2"] for h in res["heirs_summary"])
        total_parts = sum(h["parts"] for h in res["heirs_summary"])
        assert abs(total_m2 - 180.0) < 0.1, f"Total m2 mapped should sum to 180, got {total_m2}"
        assert abs(total_parts - 264000.0) < 1.0, f"Total parts mapped should sum to 264000, got {total_parts}"
        print("[PASS] Test 6: Real Estate Mapping (180 m² & 264,000 parts mapped accurately)")
        passed += 1
    except Exception as e:
        sys.stdout.buffer.write(f"[FAIL] Test 6: Real Estate Mapping Exception: {e}\n".encode('utf-8'))
        failed += 1

    # -------------------------------------------------------------------------
    # TEST 7: Word Document (.docx) Export
    # -------------------------------------------------------------------------
    try:
        out_docx = BASE_DIR / "scratch" / "audit_farida_sample.docx"
        engine.export_farida_docx(res, str(out_docx))
        assert out_docx.exists() and out_docx.stat().st_size > 0, "Docx file should exist and not be empty"
        print(f"[PASS] Test 7: Word Document Export (Generated valid .docx {out_docx.stat().st_size} bytes)")
        passed += 1
    except Exception as e:
        sys.stdout.buffer.write(f"[FAIL] Test 7: Word Export Exception: {e}\n".encode('utf-8'))
        failed += 1

    print("-----------------------------------------------------------------")
    print(f"AUDIT SUMMARY: {passed} PASSED, {failed} FAILED.")
    print("=================================================================")

if __name__ == "__main__":
    run_farida_comprehensive_audit()
