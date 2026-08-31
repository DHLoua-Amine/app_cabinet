import subprocess
import os
import re
import sys
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("=== FULL GIT HISTORY SENSITIVE DATA AUDIT ===")

# 1. Get all commit hashes
res = subprocess.run(["git", "log", "--all", "--pretty=format:%H %s (%an, %cd)"], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
commits = res.stdout.strip().splitlines()
print(f"Total Commits in History: {len(commits)}")
for c in commits:
    print(f"  Commit: {c}")

# 2. Check for committed binary database files across all commits
res_db = subprocess.run(["git", "log", "--all", "--full-history", "--name-only", "--oneline"], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
db_files_found = set()
for line in res_db.stdout.splitlines():
    line = line.strip()
    if line.endswith(".db") or line.endswith(".sqlite") or line.endswith(".sqlite3"):
        db_files_found.add(line)

print(f"\nDatabase / SQLite Files in Git History: {list(db_files_found)}")

# 3. Scan full git diff history for API keys, secrets, passwords
key_patterns = [
    (r"AIzaSy[A-Za-z0-9_-]{33}", "Google Gemini API Key"),
    (r"sk-[A-Za-z0-9_-]{32,}", "OpenAI API Key"),
    (r"gsk_[A-Za-z0-9_-]{32,}", "Groq API Key"),
    (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded Password String"),
    (r"zarai2024", "Legacy Password Cleartext"),
    (r"PUBLIC_KEY_B64\s*=\s*['\"][^'\"]+['\"]", "Ed25519 Licensing Public Key"),
]

# Run git log -p --all to search every patch in history
patch_res = subprocess.run(["git", "log", "-p", "--all"], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
patch_text = patch_res.stdout

findings = []
for pattern, label in key_patterns:
    matches = list(re.finditer(pattern, patch_text))
    if matches:
        findings.append((label, len(matches), [m.group(0)[:25] + "..." for m in matches[:5]]))

print("\n--- Sensitive Pattern Findings in Git History ---")
if not findings:
    print("  SUCCESS: ZERO API Keys, Zero Hardcoded Passwords, Zero Credentials found in git history!")
else:
    for label, count, samples in findings:
        print(f"  ATTENTION: FOUND {count} occurrences of {label}: {samples}")

# 4. Check for committed CIN numbers, phone numbers, client names in commit logs/diffs
cin_matches = re.findall(r"\b[0-1][0-9]{7}\b", patch_text)
print(f"\nPotential CIN Numbers (8-digit Tunisian pattern) in git diffs: {len(cin_matches)} found")
if cin_matches:
    print("  Sample CINs found in commits:", set(cin_matches[:10]))

# 5. Check if git remote is configured
res_remote = subprocess.run(["git", "remote", "-v"], cwd=BASE_DIR, capture_output=True, text=True)
print(f"\nGit Remote Configuration:\n{res_remote.stdout if res_remote.stdout else 'No remotes currently set in git config.'}")
