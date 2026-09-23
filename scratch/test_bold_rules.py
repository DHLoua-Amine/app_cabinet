import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'c:\Users\amin\Desktop\zarai1_pyside\core')
sys.path.insert(0, r'c:\Users\amin\Desktop\zarai1_pyside')

from core.docx_generator import create_notary_deed_docx
import docx

test_docx_path = r'c:\Users\amin\Desktop\zarai1_pyside\scratch\test_bold_out.docx'
contract_title = "عقد بيع توثيقي"
contract_text = (
    "الحمد لله في يوم الإثنين 14 سبتمبر 2026 انعقد بين "
    "الطرف الأول البائع: السيد علي بن أحمد "
    "الطرف الثاني المشتري: السيدة مريم بنت صالح. "
    "الفصل الأول: باع واحال الطرف الأول تحت سائر الضمانات... "
    "الفصل الثاني: تم البيع نظير مبلغ جملي قدره خمسة آلاف دينار (5000 د.ت). "
    "فصل تمهيدي: حيث استقر على ملكية البائع..."
)

ok = create_notary_deed_docx(contract_title, contract_text, test_docx_path)
assert ok, "DOCX Generation failed!"

doc = docx.Document(test_docx_path)
bold_runs = []
non_bold_runs = []

for p in doc.paragraphs:
    for run in p.runs:
        if run.bold:
            bold_runs.append(run.text.strip())
        else:
            non_bold_runs.append(run.text.strip())

print("BOLD RUNS FOUND:", bold_runs)
print("NON-BOLD RUNS SAMPLE:", non_bold_runs[:5])

# Verify ONLY title and chapter headings are bold
for b_text in bold_runs:
    is_valid_bold = (
        b_text == "عقد بيع توثيقي" or
        "الفصل الأول:" in b_text or
        "الفصل الثاني:" in b_text or
        "فصل تمهيدي:" in b_text
    )
    assert is_valid_bold, f"Unexpected bold text found: {b_text}"

assert "الطرف الأول" not in bold_runs, "Party 1 should NOT be bold!"
assert "الطرف الثاني" not in bold_runs, "Party 2 should NOT be bold!"
assert "الحمد لله" not in bold_runs, "Preamble should NOT be bold!"

print("\nSUCCESS: ONLY title and chapter headings are in bold (Gras) as requested!")
