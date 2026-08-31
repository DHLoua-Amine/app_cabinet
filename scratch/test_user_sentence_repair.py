import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

input_str = "يعفى الطرفان السيد حافظ الملكية العقارية السيد حافظ الملكية العقارية، وتعتبر الفصول والتحديد والتشخيص، وتعهدا بتسليم الهبة في حدود ما ذُكر، وأُبرم العقد بين الطرفين وتُلي عليهما فوافقا وأمضايا"

cleaned = contract_templates.clean_and_verify_tunisian_entities(input_str)

print("--- ORIGINAL USER SENTENCE ---")
print(input_str)

print("\n--- REPAIRED LEGAL SENTENCE ---")
print(cleaned)

assert "السيد حافظ الملكية العقارية السيد حافظ" not in cleaned
assert "وأمضيا" in cleaned
print("\n[SUCCESS] Duplication removed & audio typos repaired cleanly with 0 errors!")
