# Preflight

```
Example Hackathon 2026
PASS: Repo exists and is public
PASS: README exists
PASS: LICENSE exists
PASS: No file named .env anywhere in the repo
WARN: commits found before event start
PASS: Demo responded in 0.60s
MANUAL: Demo video is under 3 minutes
MANUAL: Team has 4 or fewer members
0 FAIL, 1 WARN - commits found before event start

```

Checks a hackathon submission before you submit.

## Run
python preflight.py --rules rules/example.yaml --repo GITHUB_URL --demo DEMO_URL

## Install
pip install -r requirements.txt

Optional: set GITHUB_TOKEN to avoid GitHub rate limits.

Rules files are community-maintained and may be out of date.