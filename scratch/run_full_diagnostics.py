import sys
import os
import time
import hashlib
import ast
import inspect
import threading
from pathlib import Path

# Fix paths
workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"
ui_dir = workspace_dir / "ui"

for p in [str(workspace_dir), str(core_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(workspace_dir)

DB_PATH = os.path.expanduser('~') + r'\AppData\Local\CabinetNotarialZarai\data\reception.db'
initial_checksum = hashlib.sha256(open(DB_PATH, 'rb').read()).hexdigest() if os.path.exists(DB_PATH) else 'N/A'
print(f"=== INITIAL DB CHECKSUM: {initial_checksum} ===")

results = {}

# ---------------------------------------------------------
# 1. AST AUDIT: Bare excepts, silent passes, unused imports
# ---------------------------------------------------------
print("\n--- RUNNING AST AUDIT ---")
py_files = list(workspace_dir.glob("core/**/*.py")) + list(workspace_dir.glob("ui/**/*.py")) + [workspace_dir / "main.py"]

bare_except_count = 0
except_pass_count = 0
total_try_except = 0
silent_excepts_details = []

for py_file in py_files:
    try:
        content = py_file.read_text(encoding='utf-8')
        tree = ast.parse(content, filename=str(py_file))
        rel_path = py_file.relative_to(workspace_dir)

        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                total_try_except += 1
                for handler in node.handlers:
                    if handler.type is None:
                        bare_except_count += 1
                        silent_excepts_details.append(f"{rel_path}:{handler.lineno} Bare except:")
                    elif isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                        # Check body for pass
                        if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                            except_pass_count += 1
                            silent_excepts_details.append(f"{rel_path}:{handler.lineno} except Exception: pass")
                        elif len(handler.body) == 1 and isinstance(handler.body[0], ast.Expr) and isinstance(handler.body[0].value, ast.Constant) and handler.body[0].value.value is Ellipsis:
                            except_pass_count += 1
                            silent_excepts_details.append(f"{rel_path}:{handler.lineno} except Exception: ...")
    except Exception as e:
        print(f"Error parsing {py_file}: {e}")

print(f"Total try-except blocks: {total_try_except}")
print(f"Bare excepts: {bare_except_count}")
print(f"except Exception: pass/...: {except_pass_count}")

# ---------------------------------------------------------
# 2. CHECK FOR --noconsole PRINT / SYS.STDOUT TRAPS
# ---------------------------------------------------------
print("\n--- CHECKING SYS.STDOUT / NOCONSOLE TRAPS ---")
stdout_traps = []
for py_file in py_files:
    content = py_file.read_text(encoding='utf-8')
    rel_path = str(py_file.relative_to(workspace_dir))
    lines = content.splitlines()
    for idx, line in enumerate(lines, 1):
        if "sys.stdout" in line or "sys.stderr" in line:
            if "write" in line or "flush" in line:
                stdout_traps.append(f"{rel_path}:{idx}: {line.strip()}")

print(f"Found {len(stdout_traps)} potential sys.stdout/sys.stderr write traps:")
for t in stdout_traps[:10]:
    print("  ", t)

# Save AST results
results["ast"] = {
    "total_try_except": total_try_except,
    "bare_except_count": bare_except_count,
    "except_pass_count": except_pass_count,
    "silent_excepts_details": silent_excepts_details,
    "stdout_traps": stdout_traps
}

with open(workspace_dir / "scratch" / "ast_results.json", "w", encoding="utf-8") as f:
    import json
    json.dump(results["ast"], f, indent=2)

print("\n--- AST AUDIT COMPLETE ---")
