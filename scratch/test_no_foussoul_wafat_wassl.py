import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 TESTING HOJJAT WAFAT & WASSL KHALASS (WITHOUT FOUSSOUL)")
print("="*70)

# 1. TEST HOJJAT WAFAT (حجة وفاة)
p1_wafat = {
    "full_name": "أمين بن محمد المبارك",
    "birth_date": "14/12/1980",
    "birth_place": "تونس",
    "nationality": "تونسي الجنسية",
    "job": "تاجر",
    "cin_number": "01234567",
    "issue_date": "01/01/2005",
    "address": "أريانة تونس"
}

w1 = {
    "full_name": "صالح بن علي الرياحي",
    "birth_date": "10/05/1960",
    "birth_place": "المنستير",
    "nationality": "تونسي الجنسية",
    "job": "متقاعد",
    "cin_number": "00112233",
    "issue_date": "15/03/1990",
    "address": "المنستير"
}

w2 = {
    "full_name": "عثمان بن سالم الجلاصي",
    "birth_date": "20/08/1965",
    "birth_place": "سوسة",
    "nationality": "تونسي الجنسية",
    "job": "فلاح",
    "cin_number": "00445566",
    "issue_date": "10/06/1995",
    "address": "سوسة"
}

wafat_text = contract_templates.build_multi_party_contract_text(
    contract_type="حجة وفاة وتركة",
    party1_list=[p1_wafat],
    party2_list=[],
    witness1_info=w1,
    witness2_info=w2,
    property_desc="المرحوم محمد المبارك المتوفى بتاريخ 15/02/2026 والمنحصرة ورثته الشرعيون في زوجته فاطمة وأبنائه أمين ومريم"
)

print("\n--- 📄 1. حجة وفاة (بدون فصول) ---")
print(wafat_text)

assert "الفصل الأول" not in wafat_text
assert "الفصل الثاني" not in wafat_text
assert "بطلب من طالب الإشهاد:" in wafat_text
assert "أشهدوا بثبوت وفاة الهالك" in wafat_text


# 2. TEST WASSL KHALASS (وصل خلاص)
p1_wassl = {
    "full_name": "فوزي بن صلاح الدين الوسلاتي",
    "birth_date": "06/05/1968",
    "birth_place": "قعفور",
    "nationality": "تونسي الجنسية",
    "job": "فلاح",
    "cin_number": "04468871",
    "issue_date": "26/06/2000",
    "address": "قعفور سليانة"
}

p2_wassl = {
    "full_name": "الحبيب الوسلاتي",
    "birth_date": "03/08/1969",
    "birth_place": "قعفور",
    "nationality": "تونسي الجنسية",
    "job": "فلاح",
    "cin_number": "04477906",
    "issue_date": "19/01/2000",
    "address": "المحمدية بن عروس"
}

wassl_text = contract_templates.build_multi_party_contract_text(
    contract_type="وصل خلاص",
    party1_list=[p1_wassl],
    party2_list=[p2_wassl],
    ownership_origin="عقد بيع بحجة عادلة بتاريخ 28/11/2008 مسجلة بفوشانة وصل عدد 054753م",
    price_words="ثمانية آلاف وأربعمائة دينار",
    price_num="8400"
)

print("\n--- 📄 2. وصل خلاص (بدون فصول) ---")
print(wassl_text)

assert "الفصل الأول" not in wassl_text
assert "الفصل الثاني" not in wassl_text
assert "حيث أبرم المذكورين عقد بيع بحجة عادلة" in wassl_text
assert "قبض الطرف الأول أعلاه" in wassl_text
assert "وأبرأ البائع ذمة المشترين" in wassl_text

print("\n" + "="*70)
print(" 🎉 BOTH HOJJAT WAFAT & WASSL KHALASS NOW 100% NON-FOUSSOUL DEEDS!")
print("="*70)
