import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

from farida_engine import TunisianFaridaEngine

print("="*70)
print(" 🧪 TESTING INHERITANCE CALCULATOR (SINGLE BOY & SINGLE GIRL SHARES)")
print("="*70)

engine = TunisianFaridaEngine()

# Test case matching user screenshot:
# Wife + 3 Sons + 4 Daughters + 500 m² Property Area
heirs = {
    'wife': True,
    'sons_count': 3,
    'daughters_count': 4
}

res = engine.calculate_farida(
    heirs_dict=heirs,
    gross_estate=0.0,
    funeral_expenses=0.0,
    debts=0.0,
    property_area_m2=500.0,
    property_parts=500.0
)

print(f"\nOrigin (أصل الفريضة): {res['base_origin']} سهماً")
print("\nTABLE BREAKDOWN (Heirs Summary):")
for h in res['heirs_summary']:
    cnt = h.get('count', 1)
    lbl = f" (عدد {cnt})" if cnt > 1 else ""
    print(f"- {h['heir']}{lbl}:")
    print(f"  • Total Area: {h['area_m2']} m²  |  SINGLE HEIR AREA: {h['single_area_m2']} m²")
    print(f"  • Total Shares: {h['shares']}     |  SINGLE HEIR SHARES: {h['single_shares']}")

# Assertions
summary = {h['heir']: h for h in res['heirs_summary']}

# Wife: 1/8 of 500 = 62.5 m²
assert summary['الزوجة']['area_m2'] == 62.5

# Sons (3 sons): Total = 262.5 m², Single Son = 87.5 m²
assert summary['الأبناء (ذكور)']['count'] == 3
assert summary['الأبناء (ذكور)']['area_m2'] == 262.5
assert summary['الأبناء (ذكور)']['single_area_m2'] == 87.5

# Daughters (4 daughters): Total = 175.0 m², Single Daughter = 43.75 m²
assert summary['البنات (مع الإبن تعصيبا)']['count'] == 4
assert summary['البنات (مع الإبن تعصيبا)']['area_m2'] == 175.0
assert summary['البنات (مع الإبن تعصيبا)']['single_area_m2'] == 43.75

print("\nNOTARIAL LEGAL TEXT GENERATED:")
print(res['legal_notarial_text'])

print("\n" + "="*70)
print(" 🎉 SINGLE HEIR BREAKDOWN (87.5 m² PER BOY / 43.75 m² PER GIRL) PROVEN 100% SUCCESSFUL!")
print("="*70)
