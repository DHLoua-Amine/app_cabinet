import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
sys.stdout.reconfigure(encoding='utf-8')

from core.farida_engine import TunisianFaridaEngine

engine = TunisianFaridaEngine()

heirs_dict = {
    'wife': True,
    'wives_count': 1,
    'sons_count': 3,
    'daughters_count': 3,
    'deceased_name': 'بوجمعه بن الطيب بن محمد بن العكرمي الرياحي',
    'applicant_name': 'أحمد الرياحي',
    'hujja_num': '4/2020',
    'hujja_date': '08-01-2020',
    'hujja_court': 'محكمة الناحية بزغوان'
}

heir_details = {
    'wife_1': {'name': 'ماميه بنت الصادق بن العربي بن حراث'},
    'son_1': {'name': 'جمال الرياحي'},
    'son_2': {'name': 'أحمد الرياحي'},
    'son_3': {'name': 'منصور الرياحي'},
    'daughter_1': {'name': 'رفيقة الرياحي'},
    'daughter_2': {'name': 'أميرة الرياحي'},
    'daughter_3': {'name': 'عزة الرياحي'}
}

res = engine._compute_shares(heirs_dict, property_area_m2=500.0, property_parts=500.0)

text = engine._build_notarial_legal_text(
    origin=res['base_origin'],
    results=res['results'],
    contract_type="فريضة شرعية",
    applicant_name="أحمد الرياحي",
    applicant_cin="",
    deceased_name="بوجمعه بن الطيب بن محمد بن العكرمي الرياحي",
    hujja_num="4/2020",
    hujja_date="08-01-2020",
    hujja_court="محكمة الناحية بزغوان",
    heir_details=heir_details
)

print("=== GENERATED OFFICIAL NOTARIAL TEXT ===")
print(text)
