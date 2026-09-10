import sys
import os
import json
from pathlib import Path

workspace_dir = Path(__file__).resolve().parent.parent

target_files = [
    "ui/components/camera_thread.py",
    "ui/services/camera_service.py",
    "core/camera.py",
    "core/reception.py",
    "core/db_client.py",
    "core/db_server.py",
    "ui/pages/presence_page.py"
]

findings = []
for rel in target_files:
    fpath = workspace_dir / rel
    if fpath.exists():
        lines = fpath.read_text(encoding="utf-8").splitlines()
        for idx, l in enumerate(lines, 1):
            if "print(" in l or "sys.stdout" in l or "sys.stderr" in l:
                findings.append({
                    "file": rel,
                    "line": idx,
                    "code": l.strip()
                })

print(f"Total print/stdout/stderr statements in target files: {len(findings)}")
for f in findings:
    safe_code = f['code'].encode('ascii', 'replace').decode('ascii')
    print(f"  {f['file']}:{f['line']} -> {safe_code}")
