import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import contract_templates

print("="*70)
print(" 🧪 TESTING VERBATIM FULL PROBLEM TEXT FOR ISKAT DEED")
print("="*70)

p1 = {
    "full_name": "أنيس بن عبد المجيد بن محمود الجلاصي",
    "birth_date": "06/01/1978",
    "birth_place": "المحمدية",
    "nationality": "تونسي الجنسية",
    "job": "عامل يومي",
    "cin_number": "00907642",
    "issue_date": "10/01/2001",
    "address": "نهج الرازي الحي العتيق المحمدية بن عروس"
}

p2 = {
    "full_name": "طاهر بن محمد بن أحمد اللفات",
    "birth_date": "12/12/1962",
    "birth_place": "الدويرات",
    "nationality": "تونسي الجنسية",
    "job": "",
    "cin_number": "",
    "issue_date": "",
    "address": "10 نهج شكيب أرسلان الحي العتيق المحمدية بن عروس"
}

full_spoken_text = "الاعتداء بالعنف الذي تعرضت له يوم الاثنين فجرا حوالي الرابعة صباحا 10/08/2009 حيث اني لا علم لي اصلا باعتداء المذكور علي نظرا لظلمة المكان الذي حدث فيه الاعتداء"

text1 = contract_templates.build_multi_party_contract_text(
    contract_type="إسقاط",
    party1_list=[p1],
    party2_list=[p2],
    property_desc=full_spoken_text
)

print("\n--- 📄 CASE 1: Exact Spoken Text ---")
print(text1)

ai_prefixed_text = "تنازل وإسقاط حق في التتبع القضائي في خصوص " + full_spoken_text
text2 = contract_templates.build_multi_party_contract_text(
    contract_type="إسقاط",
    party1_list=[p1],
    party2_list=[p2],
    property_desc=ai_prefixed_text
)

print("\n--- 📄 CASE 2: AI Prefixed Text Cleaned ---")
print(text2)

assert "في خصوص في خصوص" not in text1
assert "في خصوص في خصوص" not in text2
assert "تنازل وإسقاط حق في التتبع القضائي في خصوص" not in text2
assert full_spoken_text in text1
assert full_spoken_text in text2

print("\n" + "="*70)
print(" 🎉 FULL VERBATIM ISKAT TEXT PROVEN 100% SUCCESSFUL!")
print("="*70)
