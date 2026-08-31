import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("Testing format_single_party_text with addr:")
p1 = {
    "full_name": "محمد الطيب بن محمد بن البشير ابن الحاج مبارك",
    "birth_place": "القلاعة الكبرى سوسة",
    "birth_date": "1972/12/14",
    "job": "عامل يومي",
    "cin_number": "02998019",
    "address": "5 نهج 10300 الوردية 4"
}

formatted = contract_templates.format_single_party_text(p1)
print("Formatted P1:\n", formatted)

print("\nTesting build_multi_party_contract_text:")
contract_text = contract_templates.build_multi_party_contract_text(
    contract_type="عقد هبة",
    party1_list=[p1],
    party2_list=[{"full_name": "وفاء بنت حسن بن محمد ابن الحاج", "address": "المروج 1"}]
)
print("Generated Contract Text Head:\n", contract_text[:300])
print("\n[SUCCESS] Contract assembly executed with ZERO errors!")
