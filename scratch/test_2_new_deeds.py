import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 TESTING ILTIZAM BL BAY3 & WASSL KHALASS REAL NOTARY STRUCTURE")
print("="*70)

# 1. TEST ILTIZAM BL BAY3 (التزام بالبيع)
p1_iltizam = {
    "full_name": "محمد بن عبد الله بن بلقاسم وسلاتي",
    "birth_date": "11/09/1936",
    "birth_place": "الوسلاتية العروسة",
    "nationality": "تونسي الجنسية",
    "job": "سائق تاكسي",
    "cin_number": "00079973",
    "issue_date": "06/02/1996",
    "address": "3 نهج بيروت حي الزيتون 1 فوشانة بن عروس"
}

p2_iltizam = {
    "full_name": "علي بن ابراهيم بن محمد وسلاتي",
    "birth_date": "12/01/1963",
    "birth_place": "جليدة",
    "nationality": "تونسي الجنسية",
    "job": "قيم",
    "cin_number": "04452278",
    "issue_date": "25/06/2007",
    "address": "ادمان ابو جليدة العروسة سليانة"
}

i_text = contract_templates.build_multi_party_contract_text(
    contract_type="التزام بالبيع",
    party1_list=[p1_iltizam],
    party2_list=[p2_iltizam],
    ownership_origin="أرض فلاحية مساحتها حوالي ثلث هكتار تتمثل في القطعة عدد 67 من هنشير المكلف بوعرادة العروسة سليانة",
    property_desc="قطعة الأرض المذكورة أعلاه والتي يحدها شمالاً سانية بلحسن رحيم ومحمد جنوباً بوجمعة الوسلاتي شرقاً سانية السناينية غرباً خميس الوسلاتي",
    price_words="ألف دينار",
    price_num="1000"
)

print("\n--- 📄 1. التزام بالبيع ---")
print(i_text)

assert "فصل تمهيدي:" in i_text
assert "استقر على ملك الطرف الأول" in i_text
assert "الفصل الأول:" in i_text
assert "التزم الطرف الأول أعلاه تحت سائر الضمانات الفعلية والقانونية" in i_text
assert "الفصل الثاني:" in i_text
assert "1000" in i_text
assert "الفصل الثالث:" in i_text
assert "يتم إبرام عقد بيع وجوبا" in i_text


# 2. TEST WASSL KHALASS (وصل خلاص)
p1_wassl = {
    "full_name": "فوزي بن صلاح الدين بن عثمان الوسلاتي",
    "birth_date": "06/05/1968",
    "birth_place": "قعفور",
    "nationality": "تونسي الجنسية",
    "job": "فلاح",
    "cin_number": "04468871",
    "issue_date": "26/06/2000",
    "address": "شارع الجمهورية قعفور سليانة"
}

p2_wassl = {
    "full_name": "الحبيب الوسلاتي",
    "birth_date": "03/08/1969",
    "birth_place": "قعفور",
    "nationality": "تونسي الجنسية",
    "job": "فلاح",
    "cin_number": "04477906",
    "issue_date": "19/01/2000",
    "address": "إقامة التوفيق المحمدية بن عروس في حقه وحق إخوته عدنان وعاطف وعبد الناصر"
}

w_text = contract_templates.build_multi_party_contract_text(
    contract_type="وصل خلاص",
    party1_list=[p1_wassl],
    party2_list=[p2_wassl],
    ownership_origin="محرر بتاريخ 28/11/2008 مسجلة بفوشانة بتاريخ 16/12/2008 وصل عدد 054753م",
    price_words="ثمانية آلاف وأربعمائة دينار",
    price_num="8400"
)

print("\n--- 📄 2. وصل خلاص ---")
print(w_text)

assert "حيث أبرم المذكورين عقد بيع بحجة عادلة" in w_text
assert "الفصل الأول:" in w_text
assert "قبض الطرف الأول أعلاه مبلغ" in w_text
assert "الفصل الثاني:" in w_text
assert "أبرأ البائع ذمة المشترين في المبلغ المذكور" in w_text
assert "هذا ما تم تلقيه ومعاينته" in w_text

print("\n" + "="*70)
print(" 🎉 BOTH ILTIZAM BL BAY3 & WASSL KHALASS 100% VERIFIED!")
print("="*70)
