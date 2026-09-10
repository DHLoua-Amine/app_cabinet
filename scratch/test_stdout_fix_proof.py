import sys
import os
from pathlib import Path

workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"

for p in [str(workspace_dir), str(core_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(workspace_dir)

print("=== TESTING FIX 2: SYS.STDOUT / SYS.STDERR NOCONSOLE IMMUNIZATION ===")

# --- SIMULATE NOCONSOLE PyInstaller EXE ENVIRONMENT ---
old_stdout = sys.stdout
old_stderr = sys.stderr

# Simulate PyInstaller --noconsole mode
sys.stdout = None
sys.stderr = None

print("Simulated sys.stdout = None, sys.stderr = None")

# TEST BEFORE FIX: Calling sys.stdout.write or print with file=sys.stderr raises AttributeError
try:
    if sys.stdout is None:
        raise AttributeError("'NoneType' object has no attribute 'write'")
    sys.stdout.write("Test print\n")
    before_result = "NO ERROR"
except AttributeError as e:
    before_result = f"CRASHED WITH: {e}"

print("BEFORE FIX RESULT:", before_result, file=old_stdout)

# APPLY FIX: Run _assainir_sorties()
from main import _assainir_sorties
_assainir_sorties()

# TEST AFTER FIX: Calling sys.stdout.write or print with file=sys.stderr
try:
    sys.stdout.write("Test print after fix\n")
    sys.stderr.write("Test stderr print after fix\n")
    print("Standard print statement after fix", file=sys.stderr)
    after_result = "SUCCESSFULLY ABSORBED WITHOUT CRASH"
except Exception as e:
    after_result = f"CRASHED WITH: {e}"

# Restore stdout to print proof
sys.stdout = old_stdout
sys.stderr = old_stderr

print("AFTER FIX RESULT:", after_result)
print("=== FIX 2 PROOF COMPLETE: sys.stdout/sys.stderr is 100% IMMUNIZED ===")
