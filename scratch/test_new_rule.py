import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

input_text = "وبعد الاطلاع على رسم الملكية للعقار المسمى سباستيانو كامبيو"
cleaned = contract_templates.clean_and_verify_tunisian_entities(input_text)

print("INPUT:  ", input_text)
print("CLEANED:", cleaned)

assert "رسم الملكية للعقارية" in cleaned
print("\n[SUCCESS] Rule verified with 0 errors!")
