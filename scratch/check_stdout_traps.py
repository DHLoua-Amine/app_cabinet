import sys
import os
import json
import ast
import hashlib
from pathlib import Path

workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"

for p in [str(workspace_dir), str(core_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(workspace_dir)

py_files = list(workspace_dir.glob("core/**/*.py")) + list(workspace_dir.glob("ui/**/*.py")) + [workspace_dir / "main.py"]

stdout_traps = []
for py_file in py_files:
    content = py_file.read_text(encoding='utf-8')
    rel_path = str(py_file.relative_to(workspace_dir))
    lines = content.splitlines()
    for idx, line in enumerate(lines, 1):
        if "sys.stdout" in line or "sys.stderr" in line:
            if "write" in line or "flush" in line or "file=sys." in line:
                stdout_traps.append({"file": rel_path, "line": idx, "code": line.strip()})

print(f"Total sys.stdout/sys.stderr write/file traps found: {len(stdout_traps)}")
with open(workspace_dir / "scratch" / "stdout_traps.json", "w", encoding="utf-8") as f:
    json.dump(stdout_traps, f, indent=2, ensure_ascii=False)

for t in stdout_traps:
    print(f"  {t['file']}:{t['line']} -> {t['code'][:80]}")
