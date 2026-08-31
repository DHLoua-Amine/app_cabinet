import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

garbled_f3 = "الفصل الثالث: من جراء المدنية بالبيع بحضر حرارتها في 16 أوت 2002 مسلسل ببفوجه فيه 22 أوت 2020 وسعة كذا كذا 0330202. مودع مجلد بن عروس 2003 / 12 / 5 عدد 689."
garbled_f4 = "الفصل الرابع: وافق الطرفين سيد حق الملكية العقارية واعتباره الفصل والتحديد والتشخيص ويطلبان تسليم الهبة في حدود ما ذكرت."

cleaned_f3 = contract_templates.clean_and_verify_tunisian_entities(garbled_f3)
cleaned_f4 = contract_templates.clean_and_verify_tunisian_entities(garbled_f4)

print("--- ORIGINAL GARBLED AUDIO F3 ---")
print(garbled_f3)
print("\n--- REPAIRED LEGAL TEXT F3 ---")
print(cleaned_f3)

print("\n--- ORIGINAL GARBLED AUDIO F4 ---")
print(garbled_f4)
print("\n--- REPAIRED LEGAL TEXT F4 ---")
print(cleaned_f4)

print("\n[SUCCESS] Contextual Legal Repair Engine executed with 0 errors!")
