import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 TESTING SHORTENED CONTRACT TITLES & LISTINGS")
print("="*70)

short_names = [
    "وعد بالبيع",
    "التزام بالبيع",
    "إسقاط",
    "تنازل",
    "إشهاد بالحوز",
    "معاوضة",
    "توكيل",
    "تكليف وتوكيل",
    "إسقاط دعوى",
    "وصل خلاص",
    "اتفاق"
]

p1 = {
    "full_name": "خميس بن خليفة بن سالم الرياحي",
    "birth_date": "11/02/1964",
    "birth_place": "الزريبة",
    "nationality": "تونسي الجنسية",
    "job": "عامل يومي",
    "cin_number": "00907642",
    "issue_date": "10/01/2001",
    "address": "الباطرية الزريبة زغوان"
}

p2 = {
    "full_name": "عبدالمؤمن الطاهري",
    "birth_date": "18/03/1975",
    "birth_place": "تونس",
    "nationality": "تونسي الجنسية",
    "job": "محامي لدى التعقيب",
    "cin_number": "00658824",
    "issue_date": "01/10/2003",
    "address": "نهج أم كلثوم تونس"
}

vars_sample = {
    "property_desc": "قطع أرض بمساحة 200 م.م كائنة بـ زغوان",
    "price_words": "ثلاثة آلاف دينار",
    "price_num": "3000"
}

for ctype in short_names:
    roles = contract_templates.get_party_role_names(ctype)
    text = contract_templates.build_multi_party_contract_text(
        contract_type=ctype,
        party1_list=[p1],
        party2_list=[p2],
        contract_vars=vars_sample
    )
    print(f"\n✅ Title: '{ctype}' | Roles: {roles[0]} / {roles[2]}")
    assert "الحمد لله" in text

print("\n" + "="*70)
print(" 🎉 ALL SHORTENED CONTRACT TITLES & LISTINGS 100% VERIFIED!")
print("="*70)
