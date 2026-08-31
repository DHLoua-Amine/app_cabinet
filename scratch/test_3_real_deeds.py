import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 TESTING THE 3 AUTHENTIC DEEDS (تكليف وتوكيل / اتفاق / إشهاد بالحوز)")
print("="*70)

# 1. TEST TAKLEEF (تكليف وتوكيل)
p1_takleef_list = [
    {
        "full_name": "خميس بن خليفة بن سالم الرياحي",
        "birth_date": "11/02/1964",
        "birth_place": "الباطرية الزريبة",
        "nationality": "تونسي الجنسية",
        "job": "عامل يومي",
        "cin_number": "00907642",
        "issue_date": "10/01/2001",
        "address": "الباطرية الزريبة زغوان"
    },
    {
        "full_name": "الشاذلي بن خليفة بن سالم الرياحي",
        "birth_date": "18/03/1939",
        "birth_place": "عين الباطرية",
        "nationality": "تونسي الجنسية",
        "job": "عامل يومي",
        "cin_number": "00658824",
        "issue_date": "01/10/2003",
        "address": "الباطرية الزريبة زغوان"
    },
    {
        "full_name": "غزالة بنت خليفة بن سالم الرياحي",
        "birth_date": "16/08/1965",
        "birth_place": "البطرية الزريبة",
        "nationality": "تونسية الجنسية",
        "job": "شؤون المنزل",
        "cin_number": "00963725",
        "issue_date": "15/05/2000",
        "address": "الباطرية الزريبة زغوان"
    }
]

p2_lawyer = {
    "full_name": "عبدالمؤمن الطاهري",
    "birth_date": "18/03/1975",
    "birth_place": "تونس",
    "nationality": "تونسي الجنسية",
    "job": "محامي لدى التعقيب",
    "cin_number": "00658824",
    "issue_date": "01/10/2003",
    "address": "نهج أم كلثوم تونس"
}

t_text = contract_templates.build_multi_party_contract_text(
    contract_type="تكليف وتوكيل",
    party1_list=p1_takleef_list,
    party2_list=[p2_lawyer],
    property_desc="شهادة رفع اليد للعقار موضوع الرسم العقاري 41957 بن عروس"
)

print("\n--- 📄 1. تكليف وتوكيل ---")
print(t_text)
assert "الذين أشهدوا بتكليف وتوكيل الأستاذ:" in t_text
assert "رفع الدعاوى القضائية لاستصدار" in t_text


# 2. TEST ICHHAD HAWZ (إشهاد بالحوز)
p1_hawz = {
    "full_name": "الزهرة بنت عبد الله بن علي الجلاصي",
    "birth_date": "05/11/1968",
    "birth_place": "تونس",
    "nationality": "تونسية الجنسية",
    "job": "لا عمل لها",
    "cin_number": "05163824",
    "issue_date": "26/08/2002",
    "address": "شارع الاستقلال حي 20 مارس فوشانة بن عروس"
}

w1_hawz = {
    "full_name": "حسن بن عبد الله بن عبيد العوني",
    "birth_date": "29/05/1960",
    "birth_place": "فوشانة",
    "nationality": "تونسي الجنسية",
    "job": "سائق سيارة اجرة تاكسي",
    "cin_number": "00870824",
    "issue_date": "24/01/1998",
    "address": "20 مارس شارع الاستقلال فوشانة بن عروس"
}

w2_hawz = {
    "full_name": "منذر بن عبد الله بن علي الجلاصي",
    "birth_date": "26/06/1976",
    "birth_place": "تونس",
    "nationality": "تونسي الجنسية",
    "job": "عامل يومي",
    "cin_number": "07018108",
    "issue_date": "28/04/1999",
    "address": "شارع 7 نوفمبر حي الزيتون 1 فوشانة بن عروس"
}

h_text = contract_templates.build_multi_party_contract_text(
    contract_type="إشهاد بالحوز",
    party1_list=[p1_hawz],
    party2_list=[w1_hawz],
    witness2_info=w2_hawz,
    property_desc="محل سكنى مساحته مائة وسبعون 170 مترا مربعا كائن شارع الاستقلال حي 20 مارس فوشانة بن عروس والذي يحده جوفا نهج اسد ابن الفرات يمينا علي الجلاصي يسارا ورثة عبد الله العوني"
)

print("\n--- 📄 2. إشهاد بالحوز ---")
print(h_text)
assert "بطلب من السيدة: الزهرة بنت عبد الله بن علي الجلاصي" in h_text
assert "وصرحت الطالبة أنها مالكة للعقار المتمثل في" in h_text
assert "بحكم المعرفة والقرابة والجوار" in h_text


# 3. TEST ITTIFAQ (اتفاق)
p1_ittifaq = {
    "full_name": "روضة بنت يوسف بن العيد رابحي",
    "birth_date": "30/12/1970",
    "birth_place": "تونس",
    "nationality": "تونسية الجنسية",
    "job": "راقنة ببلدية",
    "cin_number": "07004962",
    "issue_date": "02/01/1999",
    "address": "نهج أحد حي السعادة المحمدية بن عروس"
}

p2_ittifaq = {
    "full_name": "نادر بن سليمان بن الفالح الدريدي",
    "birth_date": "15/04/1974",
    "birth_place": "تونس",
    "nationality": "تونسي الجنسية",
    "job": "عون استقبال بنزل",
    "cin_number": "05180139",
    "issue_date": "01/02/2001",
    "address": "10 نهج 61115 الجبل الأحمر تونس"
}

extra_foussoul_ittifaq = [
    {"number": 1, "title": "الفصل الأول", "content": "سلمت الطرف الأول روضة رابحي مبلغ مالي قدره خمسة آلاف دينار نقداً للطرف الثاني نادر الدريدي."},
    {"number": 2, "title": "الفصل الثاني", "content": "تم الاتفاق على تقديم مبلغ إضافي قدره خمسة آلاف دينار إن أمكن ذلك ليصبح كامل المبلغ عشرة آلاف دينار مقابل وصل في ذلك."},
    {"number": 3, "title": "الفصل الثالث", "content": "المبلغ المدفوع بعد إتمامه أي عشرة آلاف دينار يعتبر مساهمة شريك لمدة محددة."},
    {"number": 4, "title": "الفصل الرابع", "content": "التزم الطرف الثاني بدفع مبلغ يومي قدره عشرون دينار للطرف الأول بداية من افتتاح العمل موضوع محل الشركة وهو المخبزة المتعلقة بالمحل عدد 28 شارع 7 نوفمبر حي النزاهة المحمدية بن عروس."},
    {"number": 5, "title": "الفصل الخامس", "content": "التزم الطرف الثاني بالخلاص في جملة المساهمة التي تعد بيننا بداية من موفى جويلية 2010 أي لجميع مبلغ عشرة آلاف دينار دون احتساب المرابيح اليومية."},
    {"number": 6, "title": "الفصل السادس", "content": "في صورة عدم خلاص المبلغ المذكور تصبح المساهمة المذكورة مساهمة شركة في المخبزة بكامل عناصرها المادية والمعنوية."},
    {"number": 7, "title": "الفصل السابع", "content": "لتنفيذ العقد وتفسيره عين محرره محكما لذلك."}
]

i_text = contract_templates.build_multi_party_contract_text(
    contract_type="اتفاق",
    party1_list=[p1_ittifaq],
    party2_list=[p2_ittifaq],
    extra_foussoul=extra_foussoul_ittifaq
)

print("\n--- 📄 3. عقد اتفاق ---")
print(i_text)
assert "اللذان اتفقا على:" in i_text
assert "الفصل الأول:" in i_text
assert "الفصل السابع: لتنفيذ العقد وتفسيره عين محرره محكما لذلك." in i_text

print("\n" + "="*70)
print(" 🎉 ALL 3 AUTHENTIC TUNISIAN DEEDS 100% VERIFIED!")
print("="*70)
