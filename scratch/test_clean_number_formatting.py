import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

user_text_2 = """بعد الاطلاع على رسم الملكية للعقارية المسمى سباستيانو كامبيو موضوع الرسم العقاري عدد 57722 بن عروس حمام الأنف الكائن بـحي 200، حمام الأنف، بن عروس مساحته 317379 مترا مربعا وإشعار الطرفين بحالته القانونية اتفقا على: الفصل الأول: وهبت وسلّمت وحازت الواهبة، الطرف الأول، للطرف الثاني الموهوب له، تحت سائر الضمانات القانونية والفعلية. وقد قبل الموهوب له الحصة الموهوبة، وهي ما يمثل تسعة وتسعين فاصلة خمسمائة وثمانية وعشرين 99.528 جزءًا من مجموع ثلاثمائة وسبعة عشر ألفًا وثلاثمائة وتسعة وسبعين 317379 جزءًا من العقار. وهي مساحة قسم مشاع في محل سكنى كائن بحي 200، حمام الأنف، بن عروس. الفصل الثاني: قيمة العقار الموهوب ثلاثة آلاف دينار 3000. الفصل الثالث: انجرار الملكية بالبيع، بحجة حررناها في السادس عشر من أوت سنة ألفين واثنين 16/08/2002، مسجلة بقباضة فوشانة في الثاني والعشرين من أوت سنة ألفين وعشرين 22/08/2020، وصل عدد صفر ثلاثة وثلاثين ألفا ومائتين 0330200، مودعة بمجلد بن عروس سنة ألفين وثلاثة 2003 جزء 15، عدد ستة آلاف وثمانمائة وتسعة وعشرين 6829. الفصل الرابع: يعفى الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتشخيص، ويطلبان ترسيم الهبة في حدود ما ذكر."""

cleaned = contract_templates.clean_and_verify_tunisian_entities(user_text_2)

print("="*70)
print(" 🧪 TEST RESULT FOR USER'S LATEST DICTATION TEXT")
print("="*70)
print(cleaned)
print("="*70)

assert "تسعة وتسعين" not in cleaned, "FAIL: 'تسعة وتسعين' still present before 99.528!"
assert "ثلاثمائة وسبعة عشر" not in cleaned, "FAIL: 'ثلاثمائة وسبعة عشر' still present before 317379!"
assert "السادس عشر من أوت سنة ألفين واثنين" not in cleaned, "FAIL: Spelled-out date still present before 16/08/2002!"
assert "الثاني والعشرين من أوت سنة ألفين وعشرين" not in cleaned, "FAIL: Spelled-out date still present before 22/08/2020!"
assert "صفر ثلاثة وثلاثين" not in cleaned, "FAIL: 'صفر ثلاثة وثلاثين' still present before 0330200!"
assert "سنة ألفين وثلاثة" not in cleaned, "FAIL: 'سنة ألفين وثلاثة' still present before 2003!"
assert "ستة آلاف وثمانمائة" not in cleaned, "FAIL: 'ستة آلاف وثمانمائة' still present before 6829!"

print("\n🎉 ALL VERBOSE SPELLED-OUT ARABIC NUMBERS & DATES STRIPPED WITH 0 ERRORS!")
