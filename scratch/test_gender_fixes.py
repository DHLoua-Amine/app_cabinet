import sys
import re
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

user_text = """الحمد لله ... انعقد بين الطرف الأول البائع: السيد: محمد الطيب بن محمد بن البشير ابن الحاج مبارك ... الطرف الثاني المشترية: السيدة: وفاء بنت حسن بن محمد ابن الحاج ... الفصل الأول: وهبت وسلمت وحوزت الطرف الأول الواهبة، تحت كافة الضمانات الفعلية والقانونية، للطرف الثاني الموهوب له الذي قبل، جميع مناباتها البالغة 99.528 جزءا من جملة 317379 جزءا على الشياع، من محل سكنى كائن بحي الحسامية المحمدية بن عروس. الفصل الثاني: حددت قيمة العقار الموهوب بـ 3000 دينار. الفصل الثالث: انجرار الملكية بالبيع بحجة حررناها في 16/08/2002 ، مسجل بقباضة المالية بفوشانة في 22/08/2002 وصل عدد 03302010 ، ومودع بمجلد بن عروس 2003/5 عدد 698. الفصل الرابع: يعفى الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتشخيص، ويطلبان ترسيم الهبة في حدود ما ذكر."""

cleaned = contract_templates.clean_and_verify_tunisian_entities(user_text)

print("="*70)
print(" 🧪 TEST GENDER & PUNCTUATION FIXES")
print("="*70)
print(cleaned)
print("="*70)
