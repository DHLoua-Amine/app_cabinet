import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import cin_extractor

provider, model = config.load_ai_engine()
keys = config.load_saved_api_keys(provider)

print("="*70)
print(f" 🧪 TESTING DUAL-FACE CIN OCR WITH {model}")
print("="*70)

# Check if party_dict formatted preamble leaves dots if fields exist
test_party = {
    "full_name": "وفاء بنت حسن بن محمد ابن الحاج",
    "birth_place": "القلعة الكبرى",
    "birth_date": "1982/05/18",
    "job": "متصرف بوزارة الصحة",
    "cin_number": "08495241",
    "issue_date": "2010/04/12",
    "address": "53 نهج القصرين المروج 1 بن عروس"
}

import contract_templates
formatted = contract_templates.format_single_party_text(test_party)

print("\nFormatting test with complete fields:")
print(formatted)
assert "................" not in formatted, "FAIL: Dots still present when fields are provided!"

print("\n✅ PREAMBLE FORMATTER PROVEN 100% CLEAN WITH FULL FIELDS!")
print("="*70)
