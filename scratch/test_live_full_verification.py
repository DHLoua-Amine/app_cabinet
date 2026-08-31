import sys
import time
import io
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import contract_templates

print("="*70)
print(" 🧪 FINAL EMPIRICAL VERIFICATION OF ALL FIXED COMPONENTS")
print("="*70)

# 1. Test Party Preamble Formatter with Full Dual-Face Fields (Mohammed Taieb & Wafa)
p1_full = {
    "full_name": "محمد الطيب بن محمد بن البشير ابن الحاج مبارك",
    "birth_place": "القلعة الكبرى سوسة",
    "birth_date": "1972/12/14",
    "job": "عامل يومي",
    "cin_number": "02998019",
    "issue_date": "1999/03/09",
    "address": "5 نهج 10300 الوردية 4"
}

p2_full = {
    "full_name": "وفاء بنت حسن بن محمد ابن الحاج",
    "birth_place": "القلعة الكبرى",
    "birth_date": "1982/05/18",
    "job": "متصرف بوزارة الصحة",
    "cin_number": "08495241",
    "issue_date": "2010/04/12",
    "address": "53 نهج القصرين المروج 1 بن عروس"
}

p1_formatted = contract_templates.format_single_party_text(p1_full)
p2_formatted = contract_templates.format_single_party_text(p2_full)

print("\n1. PARTY PREAMBLE FORMATTING:")
print(f"Party 1: {p1_formatted}")
print(f"Party 2: {p2_formatted}")
assert "................" not in p1_formatted, "FAIL: Party 1 has dots!"
assert "................" not in p2_formatted, "FAIL: Party 2 has dots!"
print("✅ PREAMBLE FIELD TEST: 100% SUCCESS (0 DOTS)")

# 2. Test Gender Agreement (الواهب vs الموهوب لها)
dictation_text_with_reversed_gender = """الفصل الأول: وهبت وسلمت وحوزت الطرف الأول الواهبة، تحت كافة الضمانات الفعلية والقانونية، للطرف الثاني الموهوب له الذي قبل، جميع مناباتها البالغة 99.528 جزءا من جملة 317379 جزءا على الشياع."""

full_contract_draft = f"انعقد بين الطرف الأول البائع: {p1_formatted} الطرف الثاني المشترية: {p2_formatted} {dictation_text_with_reversed_gender}"

cleaned_contract = contract_templates.clean_and_verify_tunisian_entities(full_contract_draft)

print("\n2. GENDER AGREEMENT CORRECTION (الواهب vs الموهوب لها):")
print(cleaned_contract)

assert "الطرف الأول الواهب" in cleaned_contract, "FAIL: Party 1 is not masculine الواهب!"
assert "وهب وسلم وحوز" in cleaned_contract, "FAIL: Party 1 verb is not masculine وهب!"
assert "جميع مناباته" in cleaned_contract, "FAIL: Party 1 pronoun is not masculine مناباته!"
assert "الموهوب لها التي قبلت" in cleaned_contract, "FAIL: Party 2 is not feminine الموهوب لها التي قبلت!"

print("✅ GENDER AGREEMENT TEST: 100% SUCCESS!")

print("\n" + "="*70)
print(" 🎉 ALL TESTS PASSED WITH 100% ABSOLUTE CONFIRMATION!")
print("="*70)
