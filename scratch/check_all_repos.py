import subprocess
import json

print("=== CHECKING ALL REPOSITORIES FOR USER dhlou3 ===")

# Query GitHub API via gh CLI for dhlou3 repositories
cmd = ["gh", "api", "user/repos", "--paginate", "--jq", ".[] | {name: .name, full_name: .full_name, private: .private, visibility: .visibility, stargazers_count: .stargazers_count, forks_count: .forks_count, html_url: .html_url}"]
res = subprocess.run(cmd, capture_output=True, text=True)

if res.returncode == 0:
    lines = res.stdout.strip().splitlines()
    for line in lines:
        try:
            repo = json.loads(line)
            print(f"Repo: {repo['full_name']}")
            print(f"  - Visibility: {repo['visibility']} (Private: {repo['private']})")
            print(f"  - Stars: {repo['stargazers_count']} | Forks: {repo['forks_count']}")
            print(f"  - URL: {repo['html_url']}\n")
        except Exception as e:
            print("Error parsing line:", line, e)
else:
    print("Error querying gh api user/repos:", res.stderr)
