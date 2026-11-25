import argparse
import os
import sys
import time
import urllib.parse
import requests
import yaml

TIMEOUT = 10
results = []


def record_result(status, message):
    results.append((status, message))
    print(f"{status}: {message}")


def parse_github_url(url):
    if not url:
        return None, None
    url = url.strip()
    while url.endswith("/"):
        url = url[:-1]
    if url.endswith(".git"):
        url = url[:-4]
    while url.endswith("/"):
        url = url[:-1]

    if "://" in url:
        parsed = urllib.parse.urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
    elif ":" in url and not url.startswith("http"):
        parts = [p for p in url.split(":")[-1].split("/") if p]
    else:
        parts = [p for p in url.split("/") if p]

    if len(parts) >= 2:
        owner = parts[-2]
        repo = parts[-1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo
    return None, None


def is_rate_limit(resp):
    return (
        resp is not None
        and resp.status_code == 403
        and str(resp.headers.get("X-RateLimit-Remaining", "")).strip() == "0"
    )


def check_repo(repo_url, rules=None):
    owner, repo = parse_github_url(repo_url)
    if not owner or not repo:
        record_result("FAIL", "Repo exists and is public (invalid repository URL)")
        return

    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "preflight",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        session.headers["Authorization"] = f"Bearer {token}"

    # Check 1: Repo exists and is public (404 = FAIL)
    repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        resp = session.get(repo_api_url, timeout=TIMEOUT)
    except requests.RequestException as e:
        record_result("FAIL", f"Repo exists and is public (request error: {e})")
        return

    if is_rate_limit(resp):
        record_result("WARN", "GitHub rate limit hit, try again later or set GITHUB_TOKEN")
        return
    elif resp.status_code == 404:
        record_result("FAIL", "Repo exists and is public (404 Not Found)")
        return
    elif resp.status_code != 200:
        record_result("FAIL", f"Repo exists and is public (HTTP {resp.status_code})")
        return

    repo_data = resp.json()
    if repo_data.get("private", False):
        record_result("FAIL", "Repo exists and is public (repo is private)")
        return

    record_result("PASS", "Repo exists and is public")
    default_branch = repo_data.get("default_branch", "HEAD")

    # Fetch git tree for checks 2, 3, 4
    tree = []
    tree_api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    try:
        tree_resp = session.get(tree_api_url, timeout=TIMEOUT)
        if tree_resp.status_code == 200:
            tree = tree_resp.json().get("tree", [])
    except requests.RequestException:
        pass

    # Check 2: README exists (WARN if missing)
    readme_api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    readme_exists = False
    try:
        readme_resp = session.get(readme_api_url, timeout=TIMEOUT)
        if readme_resp.status_code == 200:
            readme_exists = True
    except requests.RequestException:
        pass

    if not readme_exists and tree:
        for item in tree:
            path = item.get("path", "")
            if "/" not in path and path.lower().startswith("readme"):
                readme_exists = True
                break

    if readme_exists:
        record_result("PASS", "README exists")
    else:
        record_result("WARN", "README exists (missing)")

    # Check 3: LICENSE exists (WARN if missing)
    license_api_url = f"https://api.github.com/repos/{owner}/{repo}/license"
    license_exists = False
    try:
        license_resp = session.get(license_api_url, timeout=TIMEOUT)
        if license_resp.status_code == 200:
            license_exists = True
    except requests.RequestException:
        pass

    if not license_exists and tree:
        for item in tree:
            path = item.get("path", "")
            if "/" not in path and path.lower().startswith(("license", "copying")):
                license_exists = True
                break

    if license_exists:
        record_result("PASS", "LICENSE exists")
    else:
        record_result("WARN", "LICENSE exists (missing)")

    # Check 4: No file named .env anywhere in the repo (FAIL if found). .env.example is fine.
    env_file_found = None
    for item in tree:
        path = item.get("path", "")
        if path.split("/")[-1] == ".env":
            env_file_found = path
            break

    if env_file_found:
        record_result("FAIL", f"No file named .env anywhere in the repo (found {env_file_found})")
    else:
        record_result("PASS", "No file named .env anywhere in the repo")

    # Check 5: Commits before event_start (WARN). Needs rules file.
    if rules and "event_start" in rules and rules["event_start"]:
        event_start = str(rules["event_start"]).strip()
        until_val = event_start if "T" in event_start else f"{event_start}T00:00:00Z"
        commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits?until={until_val}&per_page=1"
        try:
            commits_resp = session.get(commits_url, timeout=TIMEOUT)
            if is_rate_limit(commits_resp):
                record_result("WARN", "GitHub rate limit hit, try again later or set GITHUB_TOKEN")
                return
            if commits_resp.status_code == 200:
                commits = commits_resp.json()
                if isinstance(commits, list) and len(commits) > 0:
                    record_result("WARN", "commits found before event start")
                else:
                    record_result("PASS", "No commits found before event start")
            elif commits_resp.status_code == 409:
                record_result("PASS", "No commits found before event start")
            else:
                record_result("WARN", f"Could not check commits before event start (HTTP {commits_resp.status_code})")
        except requests.RequestException:
            record_result("WARN", "Could not check commits before event start (connection error)")


def check_demo(demo_url):
    try:
        t0 = time.perf_counter()
        resp1 = requests.get(demo_url, headers={"User-Agent": "preflight"}, timeout=TIMEOUT)
        elapsed = time.perf_counter() - t0

        if not (200 <= resp1.status_code < 300):
            record_result("FAIL", f"Demo returned HTTP {resp1.status_code}")
            return

        resp2 = requests.get(demo_url, headers={"User-Agent": "preflight"}, timeout=TIMEOUT)
        if not (200 <= resp2.status_code < 300):
            record_result("FAIL", f"Demo returned HTTP {resp2.status_code}")
            return

        if elapsed > 3.0:
            record_result("WARN", f"Demo responded in {elapsed:.2f}s (took over 3s)")
        else:
            record_result("PASS", f"Demo responded in {elapsed:.2f}s")
    except requests.exceptions.RequestException as e:
        err_msg = str(e).lower()
        if isinstance(e, requests.exceptions.Timeout):
            reason = "timed out"
        elif any(k in err_msg for k in ("nameresolution", "getaddrinfo", "failed to resolve")):
            reason = "DNS lookup failed"
        elif isinstance(e, requests.exceptions.SSLError) or "ssl" in err_msg:
            reason = "SSL error"
        elif "connection refused" in err_msg:
            reason = "connection refused"
        elif isinstance(e, (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL)):
            reason = "invalid URL"
        else:
            reason = "connection failed"
        record_result("FAIL", f"Demo unreachable ({reason})")


def print_summary():
    fail_count = sum(1 for status, _ in results if status == "FAIL")
    warn_count = sum(1 for status, _ in results if status == "WARN")

    most_urgent = None
    for status, msg in results:
        if status == "FAIL":
            most_urgent = msg
            break
    if not most_urgent:
        for status, msg in results:
            if status == "WARN":
                most_urgent = msg
                break

    summary = f"{fail_count} FAIL, {warn_count} WARN"
    if most_urgent:
        summary += f" - {most_urgent}"
    print(summary)


def main():
    parser = argparse.ArgumentParser(description="Preflight: a Python CLI that checks a hackathon submission.")
    parser.add_argument("--repo", help="GitHub repository URL")
    parser.add_argument("--demo", help="Demo URL")
    parser.add_argument("--rules", help="Rules YAML file")
    args = parser.parse_args()

    if not args.repo and not args.demo and not args.rules:
        return

    rules = None
    if args.rules:
        try:
            with open(args.rules, "r", encoding="utf-8") as f:
                rules = yaml.safe_load(f) or {}
            if "name" in rules and rules["name"]:
                print(rules["name"])
        except Exception as e:
            record_result("FAIL", f"Rules file could not be read ({e})")

    if args.repo:
        check_repo(args.repo, rules)

    if args.demo:
        check_demo(args.demo)

    if rules and "manual_checks" in rules and isinstance(rules["manual_checks"], list):
        for check in rules["manual_checks"]:
            print(f"MANUAL: {check}")

    print_summary()


if __name__ == "__main__":
    main()
