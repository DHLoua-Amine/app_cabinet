import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

fp = BASE_DIR / "ui" / "pages" / "scanner_page.py"
content = fp.read_text(encoding="utf-8", errors="ignore")

print("Searching for progress / log console widget in scanner_page.py:")
for idx, line in enumerate(content.splitlines(), 1):
    if any(k in line for k in ["معالجة الطرف", "تفريغ التسجيل", "log_console", "log_box", "log_edit", "status_log", "pipeline_log"]):
        if len(line.strip()) < 140:
            print(f"Line {idx}: {line.strip()}")
