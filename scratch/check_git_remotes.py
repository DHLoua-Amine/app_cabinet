import subprocess
import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Checking git status in workspace:")
git_dir = BASE_DIR / ".git"
print(f".git directory exists at {git_dir}: {git_dir.exists()}")

# Check gh auth status
try:
    res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    print("gh auth status stdout:", res.stdout)
    print("gh auth status stderr:", res.stderr)
except Exception as e:
    print("gh auth status error:", e)

# Check all git remotes in git config
try:
    res = subprocess.run(["git", "config", "--get-regexp", "remote\..*"], cwd=BASE_DIR, capture_output=True, text=True)
    print("git remotes config:", res.stdout)
except Exception as e:
    print("git config check error:", e)

# Check gh repo list
try:
    res = subprocess.run(["gh", "repo", "list"], capture_output=True, text=True)
    print("gh repo list stdout:", res.stdout)
    print("gh repo list stderr:", res.stderr)
except Exception as e:
    print("gh repo list error:", e)
