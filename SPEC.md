Preflight: a Python CLI that checks a hackathon submission.
Run: python preflight.py [--repo URL] [--demo URL] [--rules FILE]
Each flag is optional; run only the checks whose flag is given.
One file: preflight.py. Libraries: requests, pyyaml, argparse only.
No classes, no config system, no logging framework, no emojis.
Output: one line per check starting with PASS, WARN, FAIL or MANUAL,
then a summary line with counts.

Repo checks (GitHub REST API, unauthenticated):
1. Repo exists and is public (404 = FAIL).
2. README exists (WARN if missing).
3. LICENSE exists (WARN if missing).
4. No file named .env anywhere in the repo (FAIL if found).
   .env.example is fine.
5. Commits before event_start (WARN). Needs rules file.

Demo check:
- Request the URL twice with a 10s timeout.
- FAIL if unreachable or not 2xx.
- WARN if the first request takes over 3 seconds.

Rules file (YAML): name, event_start, event_end, manual_checks list.
Print each manual check as MANUAL.