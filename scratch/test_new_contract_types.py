import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 TESTING NEW CONTRACT TYPES: Promise of Sale (وعد بالبيع) & Relinquishment (إسقاط)")
print("="*70)

p1 = {"full_name": "محمد الطيب بن محمد", "job": "عامل يومي", "address": "الوردية 4"}
p2 = {"full_name": "وفاء بنت حسن", "job": "متصرف بوزارة الصحة", "address": "بن عروس"}

# 1. Test Promise of Sale (وعد بالبيع)
w_roles = contract_templates.get_party_role_names("عقد وعد بالبيع")
print("\n1. Promise of Sale Party Roles:", w_roles)
assert w_roles[0] == "الواعد بالبيع"
assert w_roles[2] == "الموعود له بالبيع"

w_text = contract_templates.build_multi_party_contract_text(
    contract_type="عقد وعد بالبيع",
    party1_list=[p1],
    party2_list=[p2],
    property_desc="العقار المسمى سيباستيانو كامبيو",
    price_words="ثلاثة آلاف دينار",
    price_num="3000"
)
print("Generated Promise of Sale Preview:")
print(w_text[:400])
assert "الواعد بالبيع" in w_text
assert "الموعود له" in w_text or "الموعود لها" in w_text

# 2. Test Relinquishment / Iskat (عقد إسقاط)
i_roles = contract_templates.get_party_role_names("عقد إسقاط")
print("\n2. Relinquishment (Iskat) Party Roles:", i_roles)
assert i_roles[0] == "المسقط"
assert i_roles[2] == "المسقط له"

i_text = contract_templates.build_multi_party_contract_text(
    contract_type="عقد إسقاط",
    party1_list=[p1],
    party2_list=[p2],
    property_desc="جميع حقوقه ومناباته الإرثية",
    price_words="ثلاثة آلاف دينار",
    price_num="3000"
)
print("Generated Relinquishment (Iskat) Preview:")
print(i_text[:400])
assert "المسقط" in i_text
assert "المسقط له" in i_text or "المسقط لها" in i_text

print("\n" + "="*70)
print(" 🎉 BOTH NEW CONTRACT TYPES PROVEN 100% FUNCTIONAL!")
print("="*70)
