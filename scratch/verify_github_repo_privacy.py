import subprocess
import json
import sys

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

repo_name = "dhlou3/app_zerai"

print(f"=== STEP 1: ENSURING {repo_name} IS PRIVATE IMMEDIATELY ===")

# Force visibility to private via gh CLI
cmd_priv = ["gh", "repo", "edit", repo_name, "--visibility", "private"]
res_priv = subprocess.run(cmd_priv, capture_output=True, text=True)
print("gh repo edit output:", res_priv.stdout.strip())
if res_priv.stderr:
    print("gh repo edit stderr:", res_priv.stderr.strip())

# Verify current visibility via API
cmd_view = ["gh", "api", f"repos/{repo_name}"]
res_view = subprocess.run(cmd_view, capture_output=True, text=True)

if res_view.returncode == 0:
    data = json.loads(res_view.stdout)
    print(f"\nVerified GitHub Repo: {data['full_name']}")
    print(f"  - Visibility: {data['visibility']}")
    print(f"  - Is Private: {data['private']}")
    print(f"  - Stargazers Count: {data['stargazers_count']}")
    print(f"  - Watchers Count: {data['watchers_count']}")
    print(f"  - Forks Count: {data['forks_count']}")
    print(f"  - Created At: {data['created_at']}")
    print(f"  - Updated At: {data['updated_at']}")
    print(f"  - Pushed At: {data['pushed_at']}")
else:
    print("Error fetching repo info:", res_view.stderr)

print("\n=== STEP 2: CHECKING FORKS, CLONES & TRAFFIC METRICS ===")
cmd_forks = ["gh", "api", f"repos/{repo_name}/forks"]
res_forks = subprocess.run(cmd_forks, capture_output=True, text=True)
if res_forks.returncode == 0:
    forks_list = json.loads(res_forks.stdout)
    print(f"Total Forks on GitHub: {len(forks_list)}")
    for f in forks_list:
        print(f"  - Forked by: {f.get('full_name')} ({f.get('html_url')})")

cmd_clones = ["gh", "api", f"repos/{repo_name}/traffic/clones"]
res_clones = subprocess.run(cmd_clones, capture_output=True, text=True)
if res_clones.returncode == 0:
    clones_data = json.loads(res_clones.stdout)
    print(f"Total Clones (Last 14 days): {clones_data.get('count', 0)} (Unique cloners: {clones_data.get('uniques', 0)})")
else:
    print("Clones traffic check response:", res_clones.stderr.strip())
