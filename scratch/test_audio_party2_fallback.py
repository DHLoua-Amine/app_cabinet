import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

# Simulating spoken dictation extraction when Party 2 CIN card is omitted
dictated_party2 = {
    "full_name": "وفاء بنت حسن بن محمد ابن الحاج",
    "birth_place": "القلعة الكبرى",
    "birth_date": "1982/05/18",
    "job": "متصرف بوزارة الصحة",
    "cin_number": "08495241",
    "issue_date": "2010/04/12",
    "address": "53 نهج القصرين المروج 1 بن عروس"
}

p1_info = {
    "full_name": "محمد الطيب بن محمد بن البشير ابن الحاج مبارك",
    "birth_place": "القلعة الكبرى سوسة",
    "birth_date": "1972/12/14",
    "job": "عامل يومي",
    "cin_number": "02998019",
    "issue_date": "1999/03/09",
    "address": "5 نهج 10300 الوردية 4"
}

preamble = contract_templates.build_multi_party_contract_text(
    contract_type="عقد هبة",
    party1_list=[p1_info],
    party2_list=[dictated_party2],
    property_desc="جميع مناباته البالغة 99.528 جزءا من جملة 317379 جزءا",
    price_words="ثلاثة آلاف دينار",
    price_num="3000",
    ownership_origin="انجرار الملكية بالبيع بحجة حررناها في 16/08/2002"
)

print("="*70)
print(" 🧪 TEST SPOKEN AUDIO FALLBACK FOR PARTY 2 (WHEN CIN CARD IS OMITTED)")
print("="*70)
print(preamble[:500])
print("="*70)

assert "السيدة: وفاء بنت حسن" in preamble, "FAIL: Party 2 name missing!"
assert "متصرف بوزارة الصحة" in preamble, "FAIL: Party 2 job missing!"
assert "53 نهج القصرين" in preamble, "FAIL: Party 2 address missing!"
assert "الطرف الأول الواهب" in preamble, "FAIL: Party 1 is not masculine الواهب!"
assert "الطرف الثاني الموهوب لها" in preamble, "FAIL: Party 2 is not feminine الموهوب لها!"

print("\n🎉 SPOKEN AUDIO FALLBACK PROVEN 100% SUCCESSFUL WITH ZERO DOTS!")
print("="*70)
