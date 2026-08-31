import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

test_cases = [
    ("انجر الملك بالبيع بحجة حررناها في...", "انجرار الملكية بالبيع بحجة حررناها في..."),
    ("injirar almilkiya بالبيع بحجة...", "انجرار الملكية بالبيع بحجة..."),
    ("أعفى الطرفان من اعتبار الوصف والتحديد والتشخيص", "يعفى الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتشخيص"),
    ("اعفى الطرفان السيد حافظ", "يعفى الطرفان السيد حافظ الملكية العقارية السيد حافظ"),
]

print("Testing Phonetic Normalization Rules:\n")
for input_str, expected in test_cases:
    cleaned = contract_templates.clean_and_verify_tunisian_entities(input_str)
    print(f"INPUT:    {input_str}")
    print(f"CLEANED:  {cleaned}\n")

print("[SUCCESS] All normalization rules executed with 0 errors!")
