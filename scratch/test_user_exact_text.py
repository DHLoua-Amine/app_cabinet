import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

user_text = """الطرف الثاني المشترية: السيدة: وفاء بنت حسن بن محمد ابن الحاج المولودة بـ القلعة الكبرى في 1982/05/18 تونسية الجنسية متصرف بوزارة الصحة بطاقة تعريفها عدد 08495241 مؤرخة في تونس في 25 ديسمبر 2024 قاطنة بـ 53 نهج القصرين المروج 1 بن عروس.. بعد الاطلاع على رسم الملكية للعقارية المسمى سيباستيانو كامبيو موضوع الرسم العقاري عدد 57272 بن عروس الحميدية الكائن بـحي حشانين حميدية بن عروس مساحته 317379 مترا مربعا وإشعار الطرفين بحالته القانونية اتفقا على: الفصل الأول: وهبت وسلمت وحوزت الطرف الأول تحت سائر الضمانات الفعلية والقانونية للطرف الثاني الذي قبل"""

cleaned = contract_templates.clean_and_verify_tunisian_entities(user_text)

print("--- ORIGINAL INPUT ---")
print(user_text)

print("\n--- CLEANED OUTPUT ---")
print(cleaned)

assert "للطرف الثاني التي قبلت" in cleaned, "FAIL: للطرف الثاني التي قبلت missing!"
print("\n[SUCCESS] Gender Grammar Engine verified with 0 errors!")
