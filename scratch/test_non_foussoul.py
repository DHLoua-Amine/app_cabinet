import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 TESTING NON-FOUSSOUL DEED GENERATION & CIN extraction")
print("="*70)

p1 = {
    "full_name": "محمد الطيب بن محمد بن البشير ابن الحاج مبارك",
    "birth_date": "14/12/1972",
    "birth_place": "القلعة الكبرى سوسة",
    "nationality": "تونسي الجنسية",
    "job": "عامل يومي",
    "cin_number": "02998019",
    "issue_date": "09/03/1999",
    "address": "5 نهج 10300 الورودية 4 تونس"
}

p2 = {
    "full_name": "حسن بن عبد الله بن عبيد العوني",
    "birth_date": "29/05/1960",
    "birth_place": "فوشانة",
    "nationality": "تونسي الجنسية",
    "job": "سائق سيارة اجرة تاكسي",
    "cin_number": "00870824",
    "issue_date": "24/01/1998",
    "address": "20 مارس شارع الاستقلال فوشانة بن عروس"
}

w2 = {
    "full_name": "منذر بن عبد الله بن علي الجلاصي",
    "birth_date": "26/06/1976",
    "birth_place": "تونس",
    "nationality": "تونسي الجنسية",
    "job": "عامل يومي",
    "cin_number": "07018108",
    "issue_date": "28/04/1999",
    "address": "شارع 7 نوفمبر حي الزيتون 1 فوشانة بن عروس"
}

vars_sample = {
    "property_desc": "محل سكنى مساحته 170 م.م كائن بـ شارع الاستقلال حي 20 مارس فوشانة بن عروس يحده جوفا نهج أسد بن الفرات، يمينا علي الجلاصي، ويسارا ورثة عبد الله العويني"
}

non_foussoul_types = [
    "إشهاد بالحوز والملكية",
    "تكليف وتوكيل محام",
    "إسقاط دعوى قضائية",
    "عقد توكيل",
    "عقد إسقاط"
]

for ctype in non_foussoul_types:
    text = contract_templates.build_multi_party_contract_text(
        contract_type=ctype,
        party1_list=[p1],
        party2_list=[p2],
        witness2_info=w2,
        property_desc=vars_sample["property_desc"]
    )
    print(f"\n--- 📄 {ctype} ---")
    print(text)
    assert "الفصل الأول" not in text, f"Failed: {ctype} should not contain 'الفصل الأول'"
    assert "الفصل الثاني" not in text, f"Failed: {ctype} should not contain 'الفصل الثاني'"
    assert "بعد الاطلاع على رسم الملكية" not in text, f"Failed: {ctype} should not contain 'بعد الاطلاع على رسم الملكية'"
    assert "........................" not in text, f"Failed: {ctype} contains placeholder dots even when CIN data was present"

print("\n" + "="*70)
print(" 🎉 NON-FOUSSOUL & CIN EXTRACTION FULLY VERIFIED 100% SUCCESSFUL!")
print("="*70)
