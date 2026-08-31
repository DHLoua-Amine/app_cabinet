import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

user_raw_text = """الفصل الأول: وهبت وسلمت وحولت الطرف الأول، تحت سائر الضمانات الفعلية والقانونية، للطرف الثاني الذي قبل، جميع نصف مناباتها في الرسم. الفصل الثاني: قيمة العقار الموهوب ثلاثة آلاف دينار. الفصل الرابع: يعفي الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتنقيص، ويطلبان ترسيم الهبة في حدود ما ذكر."""

p1_list = [{"full_name": "محمد الطيب بن محمد بن البشير ابن الحاج مبارك"}]
p2_list = [{"full_name": "وفاء بنت حسن بن محمد ابن الحاج"}]

built_contract = contract_templates.build_multi_party_contract_text(
    contract_type="عقد هبة",
    party1_list=p1_list,
    party2_list=p2_list,
    property_desc="جميع نصف مناباتها في الرسم، جميع 99.528 جزء من تجزئة العقار",
    price_num="3000",
    price_words="ثلاثة آلاف دينار",
    ownership_origin="انجرار الملكية بالبيع بحجة حررناها في 16 أوت 2002",
    extra_foussoul=["الفصل الرابع: يعفي الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتنقيص، ويطلبان ترسيم الهبة في حدود ما ذكر."]
)

cleaned_contract = contract_templates.clean_and_verify_tunisian_entities(built_contract)

print("--- REPAIRED CONTRACT OUTPUT ---")
print(cleaned_contract)

print("\nVerifying 4 Fault Corrections:")

# Fault 1: Female grammar (التي قبلت)
assert "التي قبلت" in cleaned_contract, "FAIL: Female pronoun not found!"
print("1. Female Donee Grammar: FIXED ('التي قبلت' present)")

# Fault 2: Typo التنقيص -> والتشخيص
assert "والتشخيص" in cleaned_contract and "التنقيص" not in cleaned_contract, "FAIL: التنقيص not replaced with والتشخيص!"
print("2. Legal Waiver Typo: FIXED ('والتشخيص' present, 'التنقيص' removed)")

# Fault 3: Numeric Price e.g. ثلاثة آلاف دينار (3000 د.)
assert "3000 د." in cleaned_contract, "FAIL: Numeric price (3000 د.) missing!"
print("3. Numeric Price: FIXED ('ثلاثة آلاف دينار (3000 د.)' present)")

# Fault 4: Typo وحولت -> وحوزت
raw_cleaned = contract_templates.clean_and_verify_tunisian_entities("وهبت وسلمت وحولت الطرف الأول")
assert "وهبت وسلمت وحوزت" in raw_cleaned, "FAIL: وحولت not replaced with وحوزت!"
print("4. Possession Verb Typo: FIXED ('وهبت وسلمت وحوزت' present)")

print("\n[SUCCESS] ALL 4 REPORTED FAULTS FIXED WITH 0 ERRORS!")
