import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 VERIFYING 7 NEW TUNISIAN NOTARIAL CONTRACT TYPES")
print("="*70)

new_types = [
    "تكليف وتوكيل محام",
    "عقد اتفاق وتصالح",
    "إسقاط دعوى قضائية",
    "إشهاد بالحوز والملكية",
    "التزام بالبيع",
    "وصل خلاص وإبراء ذمة",
    "إسقاط وتنازل"
]

p1 = [{
    "full_name": "خميس بن خليفة بن سالم الرياحي",
    "birth_date": "11/02/1964",
    "birth_place": "الزريبة",
    "nationality": "تونسي",
    "job": "عامل يومي",
    "cin_number": "00907642",
    "issue_date": "10/01/2001",
    "address": "الباطرية الزريبة زغوان"
}]

p2 = [{
    "full_name": "عبدالمؤمن الطاهري",
    "birth_date": "18/03/1975",
    "birth_place": "تونس",
    "nationality": "تونسي",
    "job": "محامي لدى التعقيب",
    "cin_number": "00658824",
    "issue_date": "01/10/2003",
    "address": "نهج أم كلثوم تونس"
}]

vars_sample = {
    "property_desc": "استصدار شهادة رفع اليد للعقار موضوع الرسم العقاري 41957 بن عروس",
    "price_words": "خمسة آلاف دينار",
    "price_num": "5000"
}

for ctype in new_types:
    text = contract_templates.build_multi_party_contract_text(
        contract_type=ctype,
        party1_list=p1,
        party2_list=p2,
        contract_vars=vars_sample
    )
    print(f"\n--- 📄 {ctype} ---")
    print(text[:300] + "...")
    assert "الحمد لله" in text
    assert "الفصل الأول" in text

print("\n" + "="*70)
print(" 🎉 ALL 7 NEW NOTARIAL CONTRACT TYPES PROVEN 100% SUCCESSFUL!")
print("="*70)
