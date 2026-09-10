import sys
import os
import ast
import json
from pathlib import Path

workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"

for p in [str(workspace_dir), str(core_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(workspace_dir)

py_files = list(workspace_dir.glob("core/**/*.py")) + list(workspace_dir.glob("ui/**/*.py")) + [workspace_dir / "main.py"]

print("=== DETAILED AST BREAKDOWN FOR UNCALLED FUNCTIONS & SILENT EXCEPTIONS ===")

# --- 1. SILENT EXCEPTIONS CLASSIFICATION ---
silent_exceptions_categorized = {
    "cleanup_courtesy": [],      # Closing failed socket/cursor/file (deliberately safe to ignore)
    "telemetry_optional": [],     # Sentry / analytics / non-critical ping
    "ui_warmup_prebuild": [],     # Background pre-loading of non-critical UI resources
    "property_fallback": [],     # Reading optional dict / config setting with default
    "truly_silent_business": []   # Business logic swallowing exception
}

for py_file in py_files:
    rel_path = str(py_file.relative_to(workspace_dir))
    content = py_file.read_text(encoding='utf-8')
    tree = ast.parse(content, filename=rel_path)
    lines = content.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                is_silent = False
                if len(handler.body) == 1:
                    stmt = handler.body[0]
                    if isinstance(stmt, ast.Pass):
                        is_silent = True
                    elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
                        is_silent = True

                if is_silent:
                    line_no = handler.lineno
                    code_snippet = lines[line_no-1].strip() if line_no <= len(lines) else ""
                    # Context around line_no
                    start_l = max(0, line_no - 10)
                    ctx = "\n".join(lines[start_l:line_no])
                    
                    entry = {"file": rel_path, "line": line_no, "snippet": code_snippet}
                    
                    if "close" in ctx or "disconnect" in ctx or "unlink" in ctx or "cleanup" in ctx or "remove" in ctx:
                        silent_exceptions_categorized["cleanup_courtesy"].append(entry)
                    elif "sentry" in ctx or "telemetry" in ctx or "ping" in ctx or "warmup" in ctx:
                        silent_exceptions_categorized["telemetry_optional"].append(entry)
                    elif "property" in ctx or "getattr" in ctx or "get(" in ctx or "config" in ctx:
                        silent_exceptions_categorized["property_fallback"].append(entry)
                    elif "page" in ctx or "ui" in ctx or "widget" in ctx or "repaint" in ctx:
                        silent_exceptions_categorized["ui_warmup_prebuild"].append(entry)
                    else:
                        silent_exceptions_categorized["truly_silent_business"].append(entry)

print(f"\n--- SILENT EXCEPTION CATEGORIZATION ({sum(len(v) for v in silent_exceptions_categorized.values())} total) ---")
print(f"  1. Safe Resource Cleanup (closing failed socket/cursor/file): {len(silent_exceptions_categorized['cleanup_courtesy'])}")
print(f"  2. Telemetry/Optional Background Preload:                     {len(silent_exceptions_categorized['telemetry_optional'])}")
print(f"  3. Safe Property/Config Fallbacks:                             {len(silent_exceptions_categorized['property_fallback'])}")
print(f"  4. UI Component/Animation Fallbacks:                           {len(silent_exceptions_categorized['ui_warmup_prebuild'])}")
print(f"  5. Business Logic Silent Exceptions (requires logging/review): {len(silent_exceptions_categorized['truly_silent_business'])}")

# Print business logic silent exceptions
print("\nBusiness Logic Silent Exceptions:")
for e in silent_exceptions_categorized['truly_silent_business']:
    print(f"  {e['file']}:{e['line']} -> {e['snippet']}")

# --- 2. UNCALLED FUNCTIONS CLASSIFICATION ---
defined_funcs = {}
all_identifiers = set()

for py_file in py_files:
    rel_path = str(py_file.relative_to(workspace_dir))
    content = py_file.read_text(encoding='utf-8')
    tree = ast.parse(content, filename=rel_path)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            defined_funcs[node.name] = {"file": rel_path, "line": node.lineno}
        elif isinstance(node, ast.Name):
            all_identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            all_identifiers.add(node.attr)

uncalled_categorized = {
    "qt_event_handlers": [],     # e.g., paintEvent, mousePressEvent, resizeEvent, changeEvent
    "dunder_protocol": [],       # e.g., __getitem__, __iter__, __len__, __repr__
    "api_and_data_models": [],   # e.g., to_dict, from_dict, serialize, deserialize, getters/setters
    "truly_uncalled": []
}

qt_events = {"paintEvent", "changeEvent", "resizeEvent", "mousePressEvent", "mouseMoveEvent", "keyPressEvent", "closeEvent", "showEvent", "hideEvent", "eventFilter", "dragEnterEvent", "dropEvent"}

for name, meta in defined_funcs.items():
    if name.startswith("_"):
        continue  # private helpers
    
    # Check if identifier appears anywhere in any file (e.g. Qt signal connect, reflection, string name)
    # The previous simple AST only checked direct ast.Call(Name) or ast.Call(Attribute)!
    # String references, signal connections (e.g. btn.clicked.connect(self.my_func)), and Qt callbacks were flagged as false positives!
    
    if name in qt_events:
        uncalled_categorized["qt_event_handlers"].append({"name": name, "file": meta["file"], "line": meta["line"]})
    elif name.startswith("__") and name.endswith("__"):
        uncalled_categorized["dunder_protocol"].append({"name": name, "file": meta["file"], "line": meta["line"]})
    elif name in ["to_dict", "from_dict", "serialize", "deserialize", "get_connection", "init_db", "run", "run_app", "main"]:
        uncalled_categorized["api_and_data_models"].append({"name": name, "file": meta["file"], "line": meta["line"]})
    else:
        # Check full text match in codebase
        count_occurrences = 0
        for py_file in py_files:
            txt = py_file.read_text(encoding='utf-8')
            if name in txt:
                count_occurrences += txt.count(name)
        
        if count_occurrences <= 1: # only defined, never referenced elsewhere
            uncalled_categorized["truly_uncalled"].append({"name": name, "file": meta["file"], "line": meta["line"]})
        else:
            uncalled_categorized["api_and_data_models"].append({"name": name, "file": meta["file"], "line": meta["line"]})

print(f"\n--- UNCALLED FUNCTIONS CLASSIFICATION ({len(defined_funcs)} total defined in codebase) ---")
print(f"  1. Qt Event Overrides (paintEvent, resizeEvent, etc.):     {len(uncalled_categorized['qt_event_handlers'])}")
print(f"  2. Python Dunder Protocols (__getitem__, __len__, etc.):  {len(uncalled_categorized['dunder_protocol'])}")
print(f"  3. API Surface / Signal Connections / Data Model Helpers:  {len(uncalled_categorized['api_and_data_models'])}")
print(f"  4. TRULY UNUSED / DEAD FUNCTIONS (never referenced):       {len(uncalled_categorized['truly_uncalled'])}")

print("\nTRULY UNUSED / DEAD FUNCTIONS:")
for f in uncalled_categorized['truly_uncalled']:
    print(f"  {f['file']}:{f['line']} -> def {f['name']}()")

with open(workspace_dir / "scratch" / "ast_analysis_detailed.json", "w") as f:
    json.dump({
        "silent_exceptions": silent_exceptions_categorized,
        "uncalled_functions": uncalled_categorized
    }, f, indent=2)
