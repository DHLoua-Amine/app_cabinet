import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
sys.stdout.reconfigure(encoding='utf-8')

from core.farida_engine import parse_hujjat_wafat_text

# Test 1: Exact text from the document image
raw_doc_text = """
الجمهورية التونسية
وزارة العدل
محكمة الناحية بزغوان

عدد الملف : 4/2020
بلدية جبل الوسط

حجة وفاة
بتاريخ 08-01-2020

حضر لدينا نحن احمد الطرابلسي قاضي ناحية زغوان
المدعو(ة): أحمد الرياحي جنسيته(ها): تونسية مهنته(ها): عامل يومي
صاحب(ة) بطاقة تعريف الوطنية عدد: 00955907 بتاريخ: 14-12-2018 والقاطن(ة) بـ: جبل الوسط بئر مشارقة زغوان
طلب(ت) بصفته(ها) مصرحاً(ة) إقامة حجة وفاة المرحوم(ة):
بوجمعه بن الطيب بن محمد بن العكرمي الرياحي ولقبه الرياحي
اسم الأم ولقبها: مبروكة بنت صالح بن الفهري المثلوثي الجنسية: تونسية
المتوفي(ة) بزغوان بتاريخ 05-01-2020 حسب رسم الوفاة عدد: 4 المسلم له(ها) من بلدية جبل الوسط بتاريخ 08-01-2020
وأدلى بمضامين ولادة خلفاء المرحوم(ة) وأحضر معه الشاهدين:
- وليد الرياحي صاحب(ة) بطاقة تعريف الوطنية عدد: 00945651 القاطن(ة) بـ: جبل الوسط بئر مشارقة زغوان
- هشام الدريدي صاحب(ة) بطاقة تعريف الوطنية عدد: 07345183 القاطن(ة) بـ: قنطرة بنزرت اريانة
الذين تصادقا على صحة معرفتهما بالمرحوم(ة) وأفراد عائلته(ها) بموجب صلة القرابة (أو روابط الجوار).
وبناء على أحكام الفقرتين 3 و 4 من الفصل 44 من القانون عدد 3 لسنة 1957 المؤرخ في غرة أوت 1957 و المتعلق بتنظيم الحالة المدنية كما تم تنقيحه وإتمامه. وعلى ما شهدت به البينة وما اقتضته الوثائق المدلى بها.
نقرر إقامة حجة وفاة المرحوم(ة):
بوجمعه بن الطيب بن محمد بن العكرمي الرياحي ولقبه الرياحي
وذلك باثبات ان المحيطين بارثه هم زوجته : ماميه بنت الصادق بن العربي بن حراث ولقبها بنحراث وابناؤه منها الرشداء وهم : رفيقه/جمال/أحمد/اميرة/منصور/عزة لا غير ./.
زغوان في 08-01-2020
"""

parsed = parse_hujjat_wafat_text(raw_doc_text)

print("Parsed Result:")
print(json.dumps(parsed, ensure_ascii=False, indent=2))

assert parsed['deceased_name'] == 'بوجمعه بن الطيب بن محمد بن العكرمي الرياحي', f"Wrong deceased: {parsed['deceased_name']}"
assert parsed['applicant_name'] == '', f"Wrong applicant: {parsed['applicant_name']}"
assert parsed['hujja_num'] == '4/2020', f"Wrong number: {parsed['hujja_num']}"
assert parsed['hujja_date'] == '08-01-2020', f"Wrong date: {parsed['hujja_date']}"
assert parsed['hujja_court'] == 'محكمة الناحية بزغوان', f"Wrong court: {parsed['hujja_court']}"
assert parsed['sons_count'] == 3, f"Wrong sons count: {parsed['sons_count']}"
assert parsed['daughters_count'] == 3, f"Wrong daughters count: {parsed['daughters_count']}"
assert 'رفيقه الرياحي' in parsed['names'], f"Missing heir: {parsed['names']}"
assert 'جمال الرياحي' in parsed['names'], f"Missing heir: {parsed['names']}"
assert 'اميرة الرياحي' in parsed['names'], f"Missing heir: {parsed['names']}"
assert 'منصور الرياحي' in parsed['names'], f"Missing heir: {parsed['names']}"
assert 'عزة الرياحي' in parsed['names'], f"Missing heir: {parsed['names']}"

print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! ZERO FAULTS FOUND!")
