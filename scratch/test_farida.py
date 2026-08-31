import sys
sys.path.insert(0, r'C:\Users\amin\Desktop\zarai1_pyside\core')

from farida_engine import TunisianFaridaEngine
engine = TunisianFaridaEngine()

res1 = engine.calculate_farida({'wives_count': 1, 'daughters_count': 2, 'mother': True}, estate_value=24000)
out = [f"Base Origin: {res1['base_origin']}, Is Radd: {res1['is_radd']}\nNotarial Text:\n{res1['legal_notarial_text']}\n"]
for h in res1['heirs_summary']:
    out.append(f"{h['heir']}: {h['shares']} shares / {h['base_origin']} ({h['percentage']} pct) -> {h['amount']} TND")

sys.stdout.buffer.write('\n'.join(out).encode('utf-8') + b'\n')
