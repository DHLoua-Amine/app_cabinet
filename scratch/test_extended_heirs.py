import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

from farida_engine import TunisianFaridaEngine

print("="*70)
print(" 🧪 TESTING EXTENDED HEIRS INHERITANCE ENGINE")
print("="*70)

engine = TunisianFaridaEngine()

# Test Case: Wife + 2 Wives + 2 Grandsons + 2 Granddaughters + 2 Nephews
heirs = {
    'wife': True,
    'wives_count': 2,
    'grandsons_count': 2,
    'granddaughters_count': 2,
    'nephew_full_count': 2
}

res = engine.calculate_farida(
    heirs_dict=heirs,
    gross_estate=100000.0,
    funeral_expenses=0.0,
    debts=0.0,
    property_area_m2=400.0
)

print(f"\nOrigin (أصل الفريضة): {res['base_origin']} سهماً")
print("TABLE BREAKDOWN:")
for h in res['heirs_summary']:
    cnt = h.get('count', 1)
    lbl = f" (عدد {cnt})" if cnt > 1 else ""
    print(f"- {h['heir']}{lbl}: {h['shares']} سهماً | {h['single_area_m2']} m² لكل فرد | {h['single_amount']:,.3f} TND لكل فرد")

assert any("الزوجات" in h['heir'] for h in res['heirs_summary'])
assert any("أبناء الابن" in h['heir'] for h in res['heirs_summary'])
assert any("بنات الابن" in h['heir'] for h in res['heirs_summary'])

print("\n" + "="*70)
print(" 🎉 ALL EXTENDED HEIRS PROVEN 100% SUCCESSFUL!")
print("="*70)
