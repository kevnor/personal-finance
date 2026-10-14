# DevSecOps Learning Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give this repo a GitHub Actions DevSecOps pipeline (secrets, SCA, SAST, container, DAST, supply chain, gating) plus a `learning/` curriculum and seven vulnerability labs that prove each stage catches what it should.

**Architecture:** One workflow per stage under `.github/workflows/`, open-source scanners as the portable backbone and GitHub-native features (CodeQL, Dependabot, dependency-review) layered on top. Labs live only as `vuln.patch` files, applied on throwaway `lab/NN-*` branches by `learning/labs/lab.sh`, so `main` never holds deliberately vulnerable code. Every scanner starts report-only, the baseline is triaged, then stages flip to blocking.

**Tech Stack:** GitHub Actions, Gitleaks, Semgrep, CodeQL, pip-audit, npm audit, dependency-review, Hadolint, Trivy, Syft, OWASP ZAP (baseline), Cosign, GitHub build attestations, Dependabot, `gh` CLI, actionlint, zizmor.

**Spec:** `docs/superpowers/specs/2026-10-14-devsecops-learning-setup-design.md`

## Global Constraints

- One workflow per stage: `secrets.yml`, `sast.yml`, `sca.yml`, `container.yml`, `supply-chain.yml`, `dast.yml`.
- Triggers: `secrets` on PR and push to main; `sast` and `sca` on PR, push to main and weekly; `container` on PR and push to main; `supply-chain` on main and tags only; `dast` weekly plus PRs touching `server/` or `docker/`.
- Every workflow sets least-privilege `permissions:`. Actions end up pinned to commit SHAs (Task 12).
- Labs live only as patches. They are applied on throwaway `lab/NN-...` branches and **never merged**.
- Planted secrets are obviously fake. Nothing is ever taken from `docker/.env`, `data/` or `input/`.
- Phase 1 runs every scanner report-only. Every suppression carries a written reason: `# nosemgrep: rule-id -- reason`, a commented `.trivyignore` entry with an expiry date, a Gitleaks allowlist entry with a justification.
- No branch is pushed and no PR is opened without the owner's confirmation. Every `git push`, `gh pr create`, `gh api -X PUT/PATCH` step below is an **ask-first** step.
- Local shell commands may be blocked by the authoring sandbox (`apply-seccomp ... Permission denied`). If a command fails that way, give the owner the exact command to run with `!` instead of working around it.
- Out of scope: self-hosting GitLab or runners, Kubernetes/Terraform scanning, hardening beyond baseline findings the owner chooses to fix, paid tools.

## Findings from reading the code (spec deviations)

These are facts about the repo that shape the plan. None changes the spec's intent.

1. **Passcodes are hashed with argon2** (`server/security.py`), so lab 04 cannot be "MD5 passcode hashing". It plants MD5 in the session-token signature (`_sign`) and drops `httponly=True` from the session cookie (`server/routes/auth.py`).
2. **Python dependencies have no lockfile** (`pyproject.toml` uses `>=` floors). Lab 02's Python half needs an explicit old pin, and `pip-audit` results drift without any code change (see Review Focus 3).
3. **Lab 02's npm half is command-driven**, not patch-driven: `client/package-lock.json` cannot be hand-edited credibly, so the lab README tells the learner to run `npm install lodash@4.17.15 --prefix client`.
4. **Lab patches contain fake secrets**, so Gitleaks would fail `main` on the patch file itself. Task 1 adds a `.gitleaks.toml` allowlist for `learning/labs/`.
5. **The working tree has uncommitted changes** (`.gitignore`, `docker/Dockerfile`, `docker/compose.yaml`, untracked `docker/.env.example`). Lab patches are built against committed `main`, so Task 0 clears these first.
6. **Scanner coverage is uncertain in two places and the labs say so**: GitHub dependency-review may not parse Python deps from `pyproject.toml` (it does parse `package-lock.json`), and ZAP baseline only sees a wildcard CORS header if a request carries an `Origin` header. The labs treat "the scanner missed it" as a lesson and give a manual `curl` confirmation.

## Review Focus

1. **Fork and Dependabot PRs get a read-only token and no secrets.** Expected: workflows that need `packages: write`, `id-token: write` or `security-events: write` never run on `pull_request`; `supply-chain.yml` triggers only on push to main and tags, and SARIF upload steps tolerate failure (Tasks 4, 12).
2. **Gitleaks scans full history and may find a real old secret.** Expected: a real hit is rotated first and triaged second, never "fixed" by rewriting history without asking the owner (Task 1, Task 14).
3. **`pip-audit` on unpinned deps can go red on `main` with no code change.** Expected: the scheduled run reports rather than blocks until Task 14, and the triage log records the date and resolved versions (Task 3).
4. **A lab patch can silently stop applying when `main` changes.** Expected: a `labs-check` workflow runs `git apply --check` on every patch on every PR and push (Task 1).
5. **DAST on a fresh container exposes the one-shot unauthenticated `POST /api/auth/passcode`.** Expected: ZAP runs baseline (passive) only, against a throwaway compose stack with a fresh volume, never against the owner's real instance (Task 10).

---

## File map

| Path | Responsibility |
|---|---|
| `.github/workflows/secrets.yml` | Gitleaks over full history |
| `.github/workflows/sca.yml` | pip-audit, npm audit, dependency-review |
| `.github/workflows/sast.yml` | Semgrep and CodeQL |
| `.github/workflows/container.yml` | Hadolint, build, Trivy, Syft SBOM |
| `.github/workflows/dast.yml` | compose up, ZAP baseline |
| `.github/workflows/supply-chain.yml` | Push image, Cosign sign, attest provenance |
| `.github/workflows/labs-check.yml` | Verify every lab patch still applies |
| `.github/dependabot.yml` | pip, npm, docker, github-actions updates |
| `.gitleaks.toml` | Allowlist for deliberately fake lab secrets |
| `learning/README.md` | Syllabus, order, self-check questions |
| `learning/stages/0N-*.md` | One doc per stage |
| `learning/labs/lab.sh` | start / check / finish a lab |
| `learning/labs/0N-*/` | `vuln.patch`, `README.md`, `solution.md` |
| `learning/gitlab-equivalents.md` | Stage-to-GitLab-CI mapping |
| `learning/triage-log.md` | Baseline findings and decisions |
| `learning/repo-settings.md` | Settings toggled in the GitHub UI or API |

---

## Task 0: Prepare a clean base

**Files:** none created. Working-tree housekeeping only.

**Interfaces:**
- Produces: a clean `main` checkout and a branch `devsecops/01-foundation` for Task 1. Every later phase branches from an up-to-date `main` the same way (`git switch main && git pull && git switch -c devsecops/NN-name`).

- [ ] **Step 1: See what is uncommitted**

Run: `git status --short`
Expected: lists `.gitignore`, `docker/Dockerfile`, `docker/compose.yaml` (modified) and `docker/.env.example` (untracked), possibly more.

- [ ] **Step 2: Ask the owner what to do with those changes**

Offer: (a) they commit them on their own branch and PR, or (b) `git stash push --include-untracked -m pre-devsecops` now and `git stash pop` after Task 14. Do not choose for them: the Dockerfile and compose edits are their work, not ours. Lab 05 patches the Dockerfile, so the tree must be clean before Task 9.

- [ ] **Step 3: Confirm a clean tree**

Run: `git status --short`
Expected: empty output.

- [ ] **Step 4: Confirm the spec commit is present and see the remote**

Run: `git log --oneline -3 && git remote -v`
Expected: `e96cce2 docs: design spec for the DevSecOps learning setup` at the top; `origin` pointing at the `kevnor` GitHub repo. Note the exact `OWNER/REPO` for later `gh api` calls: `gh repo view --json nameWithOwner -q .nameWithOwner`.

- [ ] **Step 5: Create the phase branch**

Run: `git switch -c devsecops/01-foundation`
Expected: `Switched to a new branch 'devsecops/01-foundation'`.

---

## Task 1: Foundation (learning skeleton, Dependabot, Gitleaks, lab runner, labs-check)

**Files:**
- Create: `.github/dependabot.yml`
- Create: `.github/workflows/secrets.yml`
- Create: `.github/workflows/labs-check.yml`
- Create: `.gitleaks.toml`
- Create: `learning/README.md`
- Create: `learning/stages/01-secrets.md`
- Create: `learning/labs/lab.sh`
- Create: `learning/triage-log.md`
- Create: `learning/repo-settings.md`

**Interfaces:**
- Produces: `learning/labs/lab.sh start <NN-name>`, `lab.sh check`, `lab.sh finish <NN-name>`. Later lab tasks create `learning/labs/<NN-name>/vuln.patch` and rely on these exact subcommands. Job names `gitleaks` and `labs-check` (used by Task 14 branch protection). Marker convention: a line `        continue-on-error: true  # report-only` (exactly this text, trailing comment included) that Task 14 deletes with `sed`.

- [ ] **Step 1: Write `.github/dependabot.yml`**

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
  - package-ecosystem: npm
    directory: "/client"
    schedule:
      interval: weekly
  - package-ecosystem: docker
    directory: "/docker"
    schedule:
      interval: weekly
  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
```

- [ ] **Step 2: Write `.gitleaks.toml`**

```toml
# Gitleaks config. Extends the default ruleset and adds one narrow allowlist.
[extend]
useDefault = true

[allowlist]
description = "Lab patches and READMEs carry deliberately fake secrets so the labs can demonstrate detection. The same strings in any other path still fail the scan."
paths = [
  '''learning/labs/.*\.patch''',
  '''learning/labs/.*/(README|solution)\.md''',
]
```

- [ ] **Step 3: Write `.github/workflows/secrets.yml`**

```yaml
name: secrets

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  gitleaks:
    name: gitleaks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history: a secret deleted in a later commit is still leaked
      - uses: gitleaks/gitleaks-action@v2
        continue-on-error: true  # report-only
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_ENABLE_COMMENTS: "false"
```

- [ ] **Step 4: Write `learning/labs/lab.sh`**

```bash
#!/usr/bin/env bash
# Drive a lab: start a throwaway branch with the flaw applied, check that every
# patch still applies to the current tree, or discard a finished lab branch.
# Lab branches are never merged.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
labs="$root/learning/labs"

usage() {
  echo "usage: lab.sh start <NN-name> | check | finish <NN-name>" >&2
  exit 2
}

case "${1:-}" in
  start)
    name=${2:-}; [ -n "$name" ] || usage
    git switch -c "lab/$name" main
    git apply --index "$labs/$name/vuln.patch"
    git commit -m "lab($name): plant the flaw (never merge)"
    echo "Next: git push -u origin lab/$name, open a PR against main, watch the checks."
    ;;
  check)
    status=0
    for patch in "$labs"/*/vuln.patch; do
      [ -e "$patch" ] || continue
      if git apply --check "$patch"; then echo "ok   $patch"; else echo "FAIL $patch"; status=1; fi
    done
    exit "$status"
    ;;
  finish)
    name=${2:-}; [ -n "$name" ] || usage
    git switch main
    git branch -D "lab/$name"
    echo "Close the PR unmerged, then: git push origin --delete lab/$name"
    ;;
  *)
    usage
    ;;
esac
```

Run: `chmod +x learning/labs/lab.sh`

- [ ] **Step 5: Write `.github/workflows/labs-check.yml`**

```yaml
name: labs-check

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  labs-check:
    name: labs-check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Every lab patch still applies to this tree
        run: bash learning/labs/lab.sh check
```

- [ ] **Step 6: Write `learning/stages/01-secrets.md`**

````markdown
# Stage 1: Secrets scanning

## The threat

A credential committed to git is public the moment the repo is, and it stays
retrievable from history after the file is deleted. Attackers scrape new public
commits for keys within minutes. For this repo the sensitive things are the
Entra client secret, the session signing secret and anything in `docker/.env`.

## The tool

**Gitleaks** matches every commit's diff against a ruleset of key formats plus a
generic "keyword near a high-entropy string" rule. `fetch-depth: 0` in the
workflow makes it read the whole history, not just the PR. `.gitleaks.toml`
extends the default rules and allowlists only `learning/labs/`, where the fake
secrets live. GitHub also offers **secret scanning with push protection**, which
blocks the push itself; see `learning/repo-settings.md`.

## Reading the output

A finding names the rule (`generic-api-key`), the file and line, the commit and
the matched secret, redacted. Ask three questions: is it real, is it still
valid, and who has had access since the commit? A real secret is **rotated
first**; removing it from history is a separate, secondary step.

## Do the lab

`learning/labs/01-leaked-secret/`

## Elsewhere

GitLab ships secret detection as `Secret-Detection.gitlab-ci.yml`; it uses
Gitleaks under the hood. See `learning/gitlab-equivalents.md`.
````

- [ ] **Step 7: Write `learning/README.md`**

````markdown
# DevSecOps learning path

This repo is the practice target. Each stage adds one kind of check to the
pipeline in `.github/workflows/`, and each has a lab that plants a realistic
flaw so you can watch the check catch it.

## How to work through it

1. Read the stage doc in `stages/`.
2. Open the workflow file it describes and read it top to bottom.
3. Run the lab: `bash learning/labs/lab.sh start <NN-name>`, push the branch,
   open a PR against `main`, watch the checks fail, then fix it using
   `solution.md` only after you have tried.
4. Close the lab PR **unmerged**: `bash learning/labs/lab.sh finish <NN-name>`.
5. Answer the self-check question out loud.

| Order | Stage | Lab | Self-check |
|---|---|---|---|
| 1 | `stages/01-secrets.md` | `labs/01-leaked-secret` | Why is deleting a leaked key from the latest commit not enough? |
| 2 | `stages/02-sca.md` | `labs/02-vulnerable-dependency` | Why can a dependency with a CVE be harmless in this app, and why fix it anyway? |
| 3 | `stages/03-sast.md` | `labs/03-sql-injection`, `labs/04-weak-crypto-and-cookie` | What can static analysis not see that a running app can? |
| 4 | `stages/04-container.md` | `labs/05-insecure-container` | Why does Trivy flag a package the app never imports? |
| 5 | `stages/05-dast.md` | `labs/06-permissive-web-config` | Why does a passive ZAP scan miss things a manual `curl` finds? |
| 6 | `stages/06-supply-chain.md` | `labs/07-poisoned-workflow` | What does a signature prove, and what does it not prove? |

Also read: `gitlab-equivalents.md`, `triage-log.md` (real findings from this
repo, with the decisions made) and `repo-settings.md`.
````

- [ ] **Step 8: Write `learning/triage-log.md` and `learning/repo-settings.md`**

`learning/triage-log.md`:

````markdown
# Triage log

One entry per baseline finding. Decision is one of: **fix**, **suppress** (with
a written reason, in the tool's own config) or **accept** (with a reason and a
review date). Entries are added in Task 14 after the first full scanner runs.

| Date | Stage | Tool and rule | Location | Decision | Reason |
|---|---|---|---|---|---|
````

`learning/repo-settings.md`:

````markdown
# Repository settings

These are changed in GitHub, not in files. Each can also be done with `gh api`.

| Setting | Where | Why |
|---|---|---|
| Dependabot alerts and security updates | Settings, Code security | CVE alerts on the dependency graph |
| Secret scanning | Settings, Code security | Finds known key formats already in the repo |
| Push protection | Settings, Code security | Rejects a push containing a known key format |
| CodeQL **default setup: off** | Settings, Code security, Code scanning | `sast.yml` runs CodeQL as an advanced workflow; leaving default setup on makes the two conflict |
| Branch protection on `main` | Settings, Branches | Added in Task 14 once checks are clean |

Command form for the first three (needs the repo admin token):

    gh api -X PATCH repos/OWNER/REPO \
      -f 'security_and_analysis[secret_scanning][status]=enabled' \
      -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'
    gh api -X PUT repos/OWNER/REPO/vulnerability-alerts
````

- [ ] **Step 9: Lint the workflows**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`
Expected: no output, exit 0. Fix anything it reports.

- [ ] **Step 10: Check the lab runner on an empty lab set**

Run: `bash learning/labs/lab.sh check; echo "exit=$?"`
Expected: no `ok`/`FAIL` lines and `exit=0` (no patches exist yet).

- [ ] **Step 11: Commit** (add explicit paths only)

```bash
git add .github/dependabot.yml .github/workflows/secrets.yml .github/workflows/labs-check.yml \
  .gitleaks.toml learning/README.md learning/stages/01-secrets.md learning/labs/lab.sh \
  learning/triage-log.md learning/repo-settings.md
git commit -m "feat: DevSecOps foundation - Gitleaks, Dependabot, lab runner

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 2: Lab 01 - leaked secret

**Files:**
- Create: `learning/labs/01-leaked-secret/vuln.patch`
- Create: `learning/labs/01-leaked-secret/README.md`
- Create: `learning/labs/01-leaked-secret/solution.md`

**Interfaces:**
- Consumes: `lab.sh` and the `gitleaks` job from Task 1.
- Produces: `learning/labs/01-leaked-secret/vuln.patch` (applies to `server/settings.py`).

- [ ] **Step 1: Add the flaw to `server/settings.py`**

Insert after the `DEFAULT_TIMEZONE = "Europe/Oslo"` line (line 19):

```python

# Fallback key for the statement-import webhook while we wait for the real one.
INTERNAL_API_KEY = "Zk3pQ9vL2mX8cR7tY1wH6sD0jG5nBfUa"
```

The value is a made-up high-entropy string under a keyword name, matching Gitleaks' `generic-api-key` rule. It matches no vendor's real key format.

- [ ] **Step 2: Export the patch and restore the file**

```bash
mkdir -p learning/labs/01-leaked-secret
git diff -- server/settings.py > learning/labs/01-leaked-secret/vuln.patch
git checkout -- server/settings.py
```

Expected: `vuln.patch` is non-empty; `git status --short` shows only the new `learning/` files.

- [ ] **Step 3: Verify the patch applies**

Run: `bash learning/labs/lab.sh check`
Expected: `ok   .../01-leaked-secret/vuln.patch`

- [ ] **Step 4: Write `README.md`**

````markdown
# Lab 01: leaked secret

**Flaw:** `server/settings.py` gains a hardcoded `INTERNAL_API_KEY`.
**Should fail:** the `gitleaks` check, rule `generic-api-key`.
**Stage:** `../../stages/01-secrets.md`

## Run it

    bash learning/labs/lab.sh start 01-leaked-secret
    git push -u origin lab/01-leaked-secret     # ask first; open a PR against main

Note: GitHub push protection may reject this push if it considers the string a
known key format. If it does, read the message (that *is* the lesson), then use
the "it's used in tests" bypass for this fake value only.

## What to look for

The `gitleaks` check fails (once Task 14 makes it blocking; until then it
reports as a failed step marked continue-on-error). Open the job log: find the
rule, file, line and commit.

## Observed output

Paste the relevant log lines here after your first run.

## Finish

    bash learning/labs/lab.sh finish 01-leaked-secret
````

- [ ] **Step 5: Write `solution.md`**

````markdown
# Lab 01 solution

1. Treat the key as compromised and rotate it at its source. Deleting the line
   does not un-leak it: it is in the commit history of the pushed branch.
2. Read the value from the environment instead:
   `INTERNAL_API_KEY = os.environ.get("PF_INTERNAL_API_KEY", "")` and document
   the variable in `docker/.env.example`.
3. Push the fix commit. Gitleaks still reports the earlier commit in the PR's
   history, because it scans commits, not just the final tree. That is
   expected; it is why a real leak means rotation plus, if warranted, a history
   rewrite coordinated with everyone who has cloned.
4. For a false positive, allowlist narrowly in `.gitleaks.toml` with a reason.
````

- [ ] **Step 6: Commit**

```bash
git add learning/labs/01-leaked-secret
git commit -m "feat: lab 01, leaked secret

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Ask the owner, then push the phase branch and open the PR**

Ask first. Then:

```bash
git push -u origin devsecops/01-foundation
gh pr create --title "DevSecOps foundation: secrets scan, Dependabot, lab runner, lab 01" \
  --body "Phase 1 of docs/superpowers/plans/2026-10-14-devsecops-learning-setup.md. All scanners report-only.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 8: Verify the baseline run**

In the PR's Checks tab: `gitleaks` ran over full history and `labs-check` is green. Record any real Gitleaks hit as a Task 14 triage entry. If the hit is a real secret, stop and tell the owner to rotate it.

- [ ] **Step 9: After the owner merges, run the lab**

```bash
git switch main && git pull
bash learning/labs/lab.sh start 01-leaked-secret
git push -u origin lab/01-leaked-secret   # ask first
```

Expected: a PR from `lab/01-leaked-secret` shows `gitleaks` reporting `generic-api-key` on `server/settings.py`; `main`'s `gitleaks` run does not. Paste the log lines into the lab README's "Observed output" section on a docs branch, then run `bash learning/labs/lab.sh finish 01-leaked-secret`.

---

## Task 3: SCA workflow

**Files:**
- Create: `.github/workflows/sca.yml`
- Create: `learning/stages/02-sca.md`

**Interfaces:**
- Produces: jobs named `pip-audit`, `npm-audit`, `dependency-review` (used by Task 14).

- [ ] **Step 1: Branch**

Run: `git switch main && git pull && git switch -c devsecops/02-sca-sast`

- [ ] **Step 2: Write `.github/workflows/sca.yml`**

```yaml
name: sca

on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "17 5 * * 1"   # Mondays 05:17 UTC; new CVEs land without any code change

permissions:
  contents: read

jobs:
  pip-audit:
    name: pip-audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pip-audit
      - name: Audit the project's declared dependencies
        continue-on-error: true  # report-only
        # pyproject.toml has version floors and no lockfile, so this resolves
        # to the newest allowed versions on the day it runs.
        run: pip-audit .

  npm-audit:
    name: npm-audit
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: client
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - name: Audit
        continue-on-error: true  # report-only
        run: npm audit --audit-level=high

  dependency-review:
    name: dependency-review
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/dependency-review-action@v4
        continue-on-error: true  # report-only
        with:
          fail-on-severity: high
          comment-summary-in-pr: never
```

- [ ] **Step 3: Write `learning/stages/02-sca.md`**

````markdown
# Stage 2: Software composition analysis (SCA)

## The threat

Most of the code running in this app is not yours: FastAPI, argon2, PyJWT,
React, Vite and everything they pull in. A known vulnerability in one of them
is a vulnerability in your app, whether or not you wrote a line near it.

## The tool

- **pip-audit** resolves the Python dependencies in `pyproject.toml` and checks
  them against the PyPI advisory database. There is no lockfile, so it checks
  whatever versions resolve *today*.
- **npm audit** checks the exact versions in `client/package-lock.json`.
- **dependency-review** runs on PRs only and diffs the dependency graph, so it
  flags a vulnerable package a PR *adds or bumps*. It reads manifests GitHub's
  dependency graph understands; `package-lock.json` yes, `pyproject.toml`
  possibly not. Whether it catches a Python pin is part of lab 02.
- **Dependabot** (see `.github/dependabot.yml`) opens the fix PRs.

## Reading the output

Each finding gives the package, installed version, advisory ID (GHSA/CVE), the
fixed version and a severity. Ask: is the vulnerable code path reachable from
this app? A dev-only dependency (Vitest) is rarely a runtime risk. Then decide
fix, suppress with a reason, or accept with a review date.

## Do the lab

`learning/labs/02-vulnerable-dependency/`

## Elsewhere

GitLab: `Dependency-Scanning.gitlab-ci.yml` (Gemnasium). Others: Snyk, OSV-Scanner,
Renovate.
````

- [ ] **Step 4: Lint**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/sca.yml learning/stages/02-sca.md
git commit -m "feat: SCA workflow - pip-audit, npm audit, dependency-review

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 4: SAST workflow

**Files:**
- Create: `.github/workflows/sast.yml`
- Create: `learning/stages/03-sast.md`

**Interfaces:**
- Produces: jobs named `semgrep`, `analyze (python)`, `analyze (javascript-typescript)` (used by Task 14).

- [ ] **Step 1: Write `.github/workflows/sast.yml`**

```yaml
name: sast

on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "41 5 * * 1"

permissions:
  contents: read

jobs:
  semgrep:
    name: semgrep
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write   # SARIF upload; read-only on fork PRs, so the upload tolerates failure
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install semgrep
      - name: Scan
        continue-on-error: true  # report-only
        run: >
          semgrep scan
          --config p/python --config p/security-audit --config p/javascript
          --exclude learning --error
          --sarif --output semgrep.sarif server client/src
      - name: Upload SARIF to the Security tab
        if: always()
        continue-on-error: true
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: semgrep.sarif
          category: semgrep

  codeql:
    name: analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read
      security-events: write
    strategy:
      fail-fast: false
      matrix:
        language: [python, javascript-typescript]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
      - uses: github/codeql-action/analyze@v3
        continue-on-error: true  # report-only
        with:
          category: codeql-${{ matrix.language }}
```

- [ ] **Step 2: Write `learning/stages/03-sast.md`**

````markdown
# Stage 3: Static application security testing (SAST)

## The threat

Bugs *you* wrote: SQL built by string formatting, weak hashes, cookies missing
security flags, user input reaching a dangerous function. SAST reads the source
without running it.

## The tool

- **Semgrep** is pattern matching on syntax trees. Fast, readable rules, easy
  to write your own. `p/python`, `p/security-audit` and `p/javascript` are
  registry rulesets.
- **CodeQL** compiles the code into a database and runs *dataflow* queries: it
  follows a value from an HTTP parameter to a database call across functions.
  Slower, deeper, fewer false positives for injection bugs. Results appear in
  the repo's Security tab.

Running both is deliberate: compare what each finds and misses.

## Reading the output

A finding is a rule ID, file, line and a message. For CodeQL, open the *path*:
the source (where untrusted data enters) and the sink (where it does damage).
Triage by asking whether the source is attacker-controlled. Suppress a false
positive in code with `# nosemgrep: rule-id -- reason`.

## Do the labs

`learning/labs/03-sql-injection/` and `learning/labs/04-weak-crypto-and-cookie/`

## Elsewhere

GitLab: `SAST.gitlab-ci.yml` (Semgrep for most languages). Others: SonarQube,
Bandit (Python only).
````

- [ ] **Step 3: Lint**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`
Expected: no output, exit 0.

- [ ] **Step 4: Commit, then (ask first) push and open the PR**

```bash
git add .github/workflows/sast.yml learning/stages/03-sast.md
git commit -m "feat: SAST workflow - Semgrep and CodeQL

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Hold the push until Tasks 5-7 add the labs to this branch, so the phase is one PR. Before pushing, confirm CodeQL default setup is off (`learning/repo-settings.md`), otherwise the CodeQL job fails with a configuration conflict.

---

## Task 5: Lab 02 - vulnerable dependency

**Files:**
- Create: `learning/labs/02-vulnerable-dependency/vuln.patch`
- Create: `learning/labs/02-vulnerable-dependency/README.md`
- Create: `learning/labs/02-vulnerable-dependency/solution.md`

**Interfaces:**
- Consumes: `lab.sh`, the `pip-audit` and `dependency-review` jobs.

- [ ] **Step 1: Pin an old PyJWT in `pyproject.toml`**

Change line 33 from `"pyjwt[crypto]>=2.7",` to:

```toml
    "pyjwt[crypto]==2.3.0",
```

PyJWT 2.3.0 is affected by CVE-2022-29217 (algorithm confusion; fixed in 2.4.0).

- [ ] **Step 2: Export the patch and restore**

```bash
mkdir -p learning/labs/02-vulnerable-dependency
git diff -- pyproject.toml > learning/labs/02-vulnerable-dependency/vuln.patch
git checkout -- pyproject.toml
bash learning/labs/lab.sh check
```

Expected: `ok` for both lab patches.

- [ ] **Step 3: Write `README.md`**

````markdown
# Lab 02: vulnerable dependency

**Flaw (Python half):** `pyproject.toml` pins `pyjwt[crypto]==2.3.0`
(CVE-2022-29217).
**Flaw (npm half, commands not a patch):** the lockfile cannot be hand-edited,
so after `lab.sh start`, also run
`npm install lodash@4.17.15 --prefix client` and commit `client/package.json`
and `client/package-lock.json` on the lab branch.
**Should fail:** `pip-audit` (PyJWT), `npm-audit` (lodash), and `dependency-review`
on the PR.
**Stage:** `../../stages/02-sca.md`

## Run it

    bash learning/labs/lab.sh start 02-vulnerable-dependency
    npm install lodash@4.17.15 --prefix client
    git add client/package.json client/package-lock.json
    git commit -m "lab(02): add a vulnerable npm dependency"
    git push -u origin lab/02-vulnerable-dependency     # ask first

## What to look for

Which of the three checks caught which half? GitHub's dependency graph reads
`package-lock.json` but may not read Python dependencies from `pyproject.toml`,
so `dependency-review` can report lodash and stay silent on PyJWT. If so, that
is a coverage gap worth writing down: it is the reason to run `pip-audit` too.

## Observed output

Paste the relevant log lines here after your first run.

## Finish

    bash learning/labs/lab.sh finish 02-vulnerable-dependency
````

- [ ] **Step 4: Write `solution.md`**

````markdown
# Lab 02 solution

1. Python: restore `"pyjwt[crypto]>=2.7"` (or bump the pin to a fixed release,
   2.4.0 or later). Re-run `pip-audit .` locally to confirm.
2. npm: `npm uninstall lodash --prefix client`, or move to a fixed version with
   `npm install lodash@latest --prefix client`.
3. Dependabot would have opened this PR for you. Check the Dependabot tab and
   compare its PR to your manual fix.
4. Decide whether the old PyJWT was *reachable*: this app verifies Entra ID
   tokens with RS256 using a fixed algorithm list, which limits exposure to the
   algorithm-confusion class. It is still a fix, not a suppression: the cost of
   bumping is tiny and the reachability argument is easy to get wrong.
````

- [ ] **Step 5: Commit**

```bash
git add learning/labs/02-vulnerable-dependency
git commit -m "feat: lab 02, vulnerable dependency

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 6: Lab 03 - SQL injection

**Files:**
- Create: `learning/labs/03-sql-injection/vuln.patch`
- Create: `learning/labs/03-sql-injection/README.md`
- Create: `learning/labs/03-sql-injection/solution.md`

**Interfaces:**
- Consumes: `lab.sh`, the `semgrep` and `analyze` jobs.

- [ ] **Step 1: Confirm the real table name**

Run: `grep -n "FROM transactions\|FROM tx\|CREATE TABLE" server/lib/store.py db/migrations/*.sql | head`
Expected: shows the actual table name. Use it in Step 2 in place of `transactions` if different. The scanners do not execute the query; the name only has to be plausible, but use the real one so the lab code is honest.

- [ ] **Step 2: Add the flaw to `server/routes/transactions.py`**

Insert after `list_transactions` (after line 46, before the `get_transaction` route; the order matters because `/{transaction_id}` would otherwise capture `/search`):

```python


@router.get("/search", response_model=list[TransactionOut])
def search_transactions(q: str, con: sqlite3.Connection = Depends(db_ro)):
    """Free-text search over descriptions."""
    rows = con.execute(
        f"SELECT * FROM transactions WHERE description LIKE '%{q}%' LIMIT 50"
    ).fetchall()
    return [TransactionOut.from_row(row) for row in rows]
```

- [ ] **Step 3: Export the patch and restore**

```bash
mkdir -p learning/labs/03-sql-injection
git diff -- server/routes/transactions.py > learning/labs/03-sql-injection/vuln.patch
git checkout -- server/routes/transactions.py
bash learning/labs/lab.sh check
```

Expected: `ok` for all lab patches.

- [ ] **Step 4: Write `README.md`**

````markdown
# Lab 03: SQL injection

**Flaw:** a new `GET /api/transactions/search?q=` builds its SQL with an
f-string, so `q=%' UNION SELECT ...` rewrites the query.
**Should fail:** `semgrep` (a formatted-SQL rule from `p/security-audit`) and
CodeQL `py/sql-injection`.
**Stage:** `../../stages/03-sast.md`

## Run it

    bash learning/labs/lab.sh start 03-sql-injection
    git push -u origin lab/03-sql-injection     # ask first

## What to look for

Compare the two tools. Semgrep matches the *shape* (an f-string reaching
`execute`). CodeQL traces the *flow* from the `q` parameter to the sink and shows
you the path in the Security tab. Which was faster? Which explained more?

## Observed output

Paste the relevant log lines here after your first run.

## Finish

    bash learning/labs/lab.sh finish 03-sql-injection
````

- [ ] **Step 5: Write `solution.md`**

````markdown
# Lab 03 solution

Use a bound parameter, never string formatting:

```python
rows = con.execute(
    "SELECT * FROM transactions WHERE description LIKE ? LIMIT 50",
    (f"%{q}%",),
).fetchall()
```

The `%` wildcards belong to the *value* you pass, not the SQL text. Re-push and
confirm both tools go quiet. Note that the route is behind `require_session`
(see `server/app.py`), so exploitation needs a session: severity is lower than
on an open route, but SQL injection is still a fix, not a suppression.
````

- [ ] **Step 6: Commit**

```bash
git add learning/labs/03-sql-injection
git commit -m "feat: lab 03, SQL injection

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 7: Lab 04 - weak crypto and cookie

**Files:**
- Create: `learning/labs/04-weak-crypto-and-cookie/vuln.patch`
- Create: `learning/labs/04-weak-crypto-and-cookie/README.md`
- Create: `learning/labs/04-weak-crypto-and-cookie/solution.md`

**Interfaces:**
- Consumes: `lab.sh`, the `semgrep` and `analyze` jobs.

- [ ] **Step 1: Make session signing use MD5 in `server/security.py`**

Replace the body of `_sign` (lines 289-292):

```python
def _sign(secret: str, body: str) -> str:
    digest = hashlib.md5(secret.encode("utf-8") + body.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
```

and add `import hashlib` to the imports (after `import base64`, before `import hmac`). Leave `from hashlib import sha256` untouched; it becomes an unused import, which a linter would also flag.

- [ ] **Step 2: Drop `httponly=True` in `server/routes/auth.py`**

In `_set_session_cookie`, delete the line `httponly=True,` (line 48).

- [ ] **Step 3: Export one patch covering both files, restore, check**

```bash
mkdir -p learning/labs/04-weak-crypto-and-cookie
git diff -- server/security.py server/routes/auth.py > learning/labs/04-weak-crypto-and-cookie/vuln.patch
git checkout -- server/security.py server/routes/auth.py
bash learning/labs/lab.sh check
```

Expected: `ok` for all lab patches.

- [ ] **Step 4: Write `README.md`**

````markdown
# Lab 04: weak crypto and cookie

**Flaw:** (1) session tokens are signed with a bare MD5 of `secret + body`
instead of HMAC-SHA256, which is both a broken hash and a length-extension-prone
construction; (2) the session cookie loses `httponly`, so any script on the page
can read it.
**Should fail:** `semgrep` on the MD5 use (`insecure-hash-algorithms-md5` or similar). The
cookie flag may or may not be flagged by either tool: that is the point of the
lab.
**Stage:** `../../stages/03-sast.md`

## Run it

    bash learning/labs/lab.sh start 04-weak-crypto-and-cookie
    git push -u origin lab/04-weak-crypto-and-cookie     # ask first

## What to look for

Write down which flaw each tool caught and which it missed. A scanner reporting
"clean" is a statement about its rules, not about your code. Confirm the cookie
flaw yourself by running the app and checking the `Set-Cookie` header after
login: `curl -si -X POST localhost:8000/api/auth/login ...`.

## Observed output

Paste the relevant log lines here after your first run.

## Finish

    bash learning/labs/lab.sh finish 04-weak-crypto-and-cookie
````

- [ ] **Step 5: Write `solution.md`**

````markdown
# Lab 04 solution

1. Restore the HMAC in `_sign`:
   `hmac.new(secret.encode("utf-8"), body.encode("ascii"), sha256).digest()`.
   HMAC is the correct construction for authenticating a message with a secret
   key; `hash(secret + message)` is not, whichever hash you pick.
2. Restore `httponly=True` on the session cookie. Keep `secure=settings.https_only`
   as it is: the existing comment explains why it cannot be hardcoded.
3. The existing session tests in `server/test/` should fail against the MD5
   version only if they pin token bytes; if they pass, note that tests verified
   *behaviour*, not *security*, which is why a separate scanner stage exists.
````

- [ ] **Step 6: Commit**

```bash
git add learning/labs/04-weak-crypto-and-cookie
git commit -m "feat: lab 04, weak crypto and cookie flags

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Ask the owner, then push the phase branch and open the PR**

```bash
git push -u origin devsecops/02-sca-sast
gh pr create --title "DevSecOps phase 2: SCA and SAST, labs 02-04" \
  --body "Adds sca.yml and sast.yml (report-only) and labs 02-04.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Expected on the PR: `pip-audit`, `npm-audit`, `dependency-review`, `semgrep`, both `analyze` jobs and `labs-check` all ran; baseline findings go to Task 14's triage log.

- [ ] **Step 8: After merge, run labs 02, 03 and 04**

For each of `02-vulnerable-dependency` (plus its npm commands), `03-sql-injection`, `04-weak-crypto-and-cookie`: `bash learning/labs/lab.sh start <name>`, push (ask first), open a PR, confirm the expected checks report findings and `main` does not, paste the output into the lab README's "Observed output" on a docs branch, then `lab.sh finish`. Record any expected check that did **not** fire as a finding in that lab's README (see Findings 6).

---

## Task 8: Container workflow

**Files:**
- Create: `.github/workflows/container.yml`
- Create: `learning/stages/04-container.md`

**Interfaces:**
- Produces: jobs `hadolint` and `image-scan` (used by Task 14).

- [ ] **Step 1: Branch**

Run: `git switch main && git pull && git switch -c devsecops/03-container`

- [ ] **Step 2: Write `.github/workflows/container.yml`**

```yaml
name: container

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  hadolint:
    name: hadolint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hadolint/hadolint-action@v3.1.0
        continue-on-error: true  # report-only
        with:
          dockerfile: docker/Dockerfile
          failure-threshold: warning

  image-scan:
    name: image-scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build the image
        run: docker build -f docker/Dockerfile -t personal-finance:ci .
      - name: Trivy - misconfiguration in docker/
        uses: aquasecurity/trivy-action@0.28.0
        continue-on-error: true  # report-only
        with:
          scan-type: config
          scan-ref: docker
          exit-code: "1"
      - name: Trivy - vulnerabilities in the image
        uses: aquasecurity/trivy-action@0.28.0
        continue-on-error: true  # report-only
        with:
          image-ref: personal-finance:ci
          severity: HIGH,CRITICAL
          ignore-unfixed: true
          exit-code: "1"
      - name: SBOM (SPDX)
        uses: anchore/sbom-action@v0
        with:
          image: personal-finance:ci
          format: spdx-json
          artifact-name: sbom.spdx.json
```

- [ ] **Step 3: Write `learning/stages/04-container.md`**

````markdown
# Stage 4: Container and Dockerfile scanning

## The threat

The image is code too: an old base image carries OS-package CVEs, a process
running as root turns a small app bug into a container-wide one, and a
`latest` tag means the build you tested is not the build you ship.

## The tool

- **Hadolint** lints the Dockerfile against best practice (`DL3007` unpinned
  `latest`, `DL3002` last user is root, `DL3013` unpinned pip versions).
- **Trivy** does two jobs here: `config` mode flags misconfiguration in
  `docker/` (for example a missing non-root `USER`), and image mode lists known
  CVEs in the OS and language packages inside the built image.
  `ignore-unfixed` hides CVEs with no available fix, which keeps the signal
  actionable.
- **Syft** produces the **SBOM** (software bill of materials): the full
  inventory of what is in the image, uploaded as an artifact. It is the input to
  later questions like "are we affected by the new CVE?"

## Reading the output

Trivy lists package, installed version, fixed version and severity. A CVE in an
OS package the app never calls is usually *real but unreachable*: the right fix
is a newer base image, not a code change. The SBOM is read with a tool, not by
eye: `grype` or `trivy sbom`.

## Do the lab

`learning/labs/05-insecure-container/`

## Elsewhere

GitLab: `Container-Scanning.gitlab-ci.yml` (Trivy). Others: Grype, Docker Scout,
Snyk Container.
````

- [ ] **Step 4: Lint, commit**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`
Expected: no output, exit 0.

```bash
git add .github/workflows/container.yml learning/stages/04-container.md
git commit -m "feat: container workflow - Hadolint, Trivy, SBOM

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 9: Lab 05 - insecure container

**Files:**
- Create: `learning/labs/05-insecure-container/vuln.patch`
- Create: `learning/labs/05-insecure-container/README.md`
- Create: `learning/labs/05-insecure-container/solution.md`

**Interfaces:**
- Consumes: `lab.sh`, the `hadolint` and `image-scan` jobs. Requires the tree to be clean of the owner's own Dockerfile edits (Task 0).

- [ ] **Step 1: Confirm `docker/Dockerfile` has no uncommitted changes**

Run: `git status --short docker/`
Expected: empty. If not, stop and return to Task 0, Step 2.

- [ ] **Step 2: Edit `docker/Dockerfile`**

Change line 14 to an old pinned base:

```dockerfile
FROM python:3.9.0-slim AS runtime
```

and add as the last line before `CMD` (after `EXPOSE 8000`):

```dockerfile
USER root
```

- [ ] **Step 3: Export the patch and restore**

```bash
mkdir -p learning/labs/05-insecure-container
git diff -- docker/Dockerfile > learning/labs/05-insecure-container/vuln.patch
git checkout -- docker/Dockerfile
bash learning/labs/lab.sh check
```

Expected: `ok` for all lab patches.

- [ ] **Step 4: Write `README.md`**

````markdown
# Lab 05: insecure container

**Flaw:** the runtime stage moves from `python:3.12-slim` to `python:3.9.0-slim`
(an old Debian base with many unfixed-at-the-time CVEs) and sets
`USER root` explicitly.
**Should fail:** `hadolint` (DL3002, last user is root), `image-scan` (Trivy
reports HIGH/CRITICAL OS package CVEs from the old base, and a root-user
misconfiguration).
**Stage:** `../../stages/04-container.md`

## Run it

    bash learning/labs/lab.sh start 05-insecure-container
    git push -u origin lab/05-insecure-container     # ask first

## What to look for

First compare against `main`'s baseline: the real Dockerfile has no `USER`
line at all, so Trivy and Hadolint may already warn about running as root and
unpinned pip versions. What *new* findings does the lab branch add? That
difference is the signal.

## Observed output

Paste the relevant log lines here after your first run.

## Finish

    bash learning/labs/lab.sh finish 05-insecure-container
````

- [ ] **Step 5: Write `solution.md`**

````markdown
# Lab 05 solution

1. Revert the base to a current, specific tag (`python:3.12-slim`, ideally
   pinned by digest once you have a Dependabot docker updater maintaining it).
2. Remove `USER root` and run as an unprivileged user: create one with
   `RUN useradd --system --uid 10001 app`, `chown` `/data` and `/app` to it,
   then `USER app`. The SQLite volume at `/data` must be writable by that user:
   test with `docker compose up` and a first-run passcode before trusting it.
3. Re-run both checks. Expect the baseline root-user warning to persist until
   step 2 is done on `main` too: that is a real finding, and Task 14 decides
   whether to fix it.
````

- [ ] **Step 6: Commit, then (ask first) push and open the PR**

```bash
git add learning/labs/05-insecure-container
git commit -m "feat: lab 05, insecure container

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin devsecops/03-container
gh pr create --title "DevSecOps phase 3: container scanning, lab 05" \
  --body "Adds container.yml (report-only), SBOM artifact and lab 05.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Expected on the PR: `hadolint` and `image-scan` ran; the SBOM artifact `sbom.spdx.json` is attached to the run. After merge, run lab 05 as in Task 7, Step 8.

---

## Task 10: DAST workflow

**Files:**
- Create: `.github/workflows/dast.yml`
- Create: `learning/stages/05-dast.md`

**Interfaces:**
- Produces: job `zap-baseline`. **Not** a required check in Task 14 (it is path-filtered, so requiring it would block PRs that never trigger it).

- [ ] **Step 1: Branch**

Run: `git switch main && git pull && git switch -c devsecops/04-dast`

- [ ] **Step 2: Write `.github/workflows/dast.yml`**

```yaml
name: dast

on:
  pull_request:
    paths:
      - "server/**"
      - "docker/**"
  schedule:
    - cron: "5 6 * * 1"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  zap-baseline:
    name: zap-baseline
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # A throwaway stack with a fresh volume and no .env: the first-run
      # passcode endpoint is open on an unconfigured instance, so this must
      # never point at a real deployment.
      - name: Start the app
        run: docker compose -f docker/compose.yaml up -d --build

      - name: Wait until it answers
        run: |
          for i in $(seq 1 30); do
            curl -fsS http://localhost:8000/api/auth/status && exit 0
            sleep 2
          done
          docker compose -f docker/compose.yaml logs
          exit 1

      # Baseline = passive scan of the spidered site. No active attacks, so it
      # cannot mutate data. -I: report warnings without failing the job.
      - name: ZAP baseline scan
        run: |
          mkdir -p zap && chmod 777 zap
          docker run --rm --network host -v "$PWD/zap:/zap/wrk:rw" \
            ghcr.io/zaproxy/zaproxy:stable zap-baseline.py \
            -t http://localhost:8000 -r report.html -J report.json -I

      - name: Upload the report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: zap-report
          path: zap/

      - name: Stop and remove the stack and its volume
        if: always()
        run: docker compose -f docker/compose.yaml down -v
```

- [ ] **Step 3: Write `learning/stages/05-dast.md`**

````markdown
# Stage 5: Dynamic application security testing (DAST)

## The threat

Some problems only exist at runtime: missing security headers, a misconfigured
CORS policy, cookies sent without flags, error pages that leak internals, and
anything the framework or reverse proxy adds or omits. Source code analysis
cannot see these because they depend on how the whole stack behaves.

## The tool

**OWASP ZAP baseline** spiders the running app and passively inspects every
response. It sends no attack payloads, so it is safe to run and cannot change
data. CI starts the app with `docker compose` on a fresh volume, scans it and
tears it down. An *active* scan (which does attack) is deliberately not used
here: it is for a copy of the app you are happy to damage.

Baseline sees only what the spider reaches. On this app that is the login
screen and `/api/auth/status`, because everything else sits behind a session.
Authenticated scanning is a real next step and out of scope here.

## Reading the output

`report.html` groups alerts by rule with risk level and the evidence (the
header or snippet). Typical baseline results for this app: missing
`Content-Security-Policy`, `X-Content-Type-Options`, anti-clickjacking header.
For each: is it exploitable here, and is the fix a one-line middleware?

## Do the lab

`learning/labs/06-permissive-web-config/`

## Elsewhere

GitLab: `DAST.gitlab-ci.yml` (ZAP-based, authenticated scans are a paid feature).
Others: Nuclei, Burp Suite.
````

- [ ] **Step 4: Lint, commit**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`
Expected: no output, exit 0.

```bash
git add .github/workflows/dast.yml learning/stages/05-dast.md
git commit -m "feat: DAST workflow - compose up and ZAP baseline

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 11: Lab 06 - permissive web config

**Files:**
- Create: `learning/labs/06-permissive-web-config/vuln.patch`
- Create: `learning/labs/06-permissive-web-config/README.md`
- Create: `learning/labs/06-permissive-web-config/solution.md`

**Interfaces:**
- Consumes: `lab.sh`, the `zap-baseline` job.

- [ ] **Step 1: Add wildcard CORS to `server/app.py`**

Add to the imports (after `from fastapi import Depends, FastAPI`, line 13):

```python
from fastapi.middleware.cors import CORSMiddleware
```

and after `app.state.settings = settings` (line 84):

```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

The module docstring says there is no CORS configuration because the client is same-origin; this lab breaks that on purpose.

- [ ] **Step 2: Export the patch and restore**

```bash
mkdir -p learning/labs/06-permissive-web-config
git diff -- server/app.py > learning/labs/06-permissive-web-config/vuln.patch
git checkout -- server/app.py
bash learning/labs/lab.sh check
```

Expected: `ok` for all lab patches.

- [ ] **Step 3: Write `README.md`**

````markdown
# Lab 06: permissive web config

**Flaw:** `server/app.py` adds `CORSMiddleware` with `allow_origins=["*"]` and
`allow_credentials=True`. Any website can then make requests to the API.
**Should fail / report:** the `zap-baseline` job *may* raise "Cross-Domain
Misconfiguration" (rule 10098). It only sees the CORS header if a request
carries an `Origin` header, which ZAP's spider does not send by default.
**Stage:** `../../stages/05-dast.md`

## Run it

    bash learning/labs/lab.sh start 06-permissive-web-config
    git push -u origin lab/06-permissive-web-config     # ask first

## What to look for

Check `zap/report.html` from the run's artifacts. Whether or not ZAP flags it,
confirm the flaw yourself against a local stack:

    docker compose -f docker/compose.yaml up -d --build
    curl -si -H 'Origin: https://evil.example' http://localhost:8000/api/auth/status | grep -i access-control

If you see `access-control-allow-origin` echoing the origin or `*`, the flaw is
real. A baseline scan that does not flag it taught you the limits of passive
scanning.

## Observed output

Paste the relevant log lines here after your first run.

## Finish

    bash learning/labs/lab.sh finish 06-permissive-web-config
    docker compose -f docker/compose.yaml down -v
````

- [ ] **Step 4: Write `solution.md`**

````markdown
# Lab 06 solution

Remove the middleware. The app is same-origin by design (see the `server/app.py`
docstring), so it needs no CORS configuration at all: the safest CORS policy is
none. If a second origin ever must call the API, list that single origin
explicitly and never combine `allow_credentials=True` with a wildcard.
````

- [ ] **Step 5: Commit, then (ask first) push and open the PR**

```bash
git add learning/labs/06-permissive-web-config
git commit -m "feat: lab 06, permissive web config

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -u origin devsecops/04-dast
gh pr create --title "DevSecOps phase 4: DAST, lab 06" \
  --body "Adds dast.yml (ZAP baseline, passive only) and lab 06.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Expected on the PR: `zap-baseline` ran (the PR touches `docker/`? it touches only workflow and learning files, so it may **not** trigger; use the Actions tab, workflow `dast`, "Run workflow" to trigger it manually) and `zap/report.html` is in the artifacts. Record the baseline alerts for Task 14. After merge, run lab 06 as in Task 7, Step 8.

---

## Task 12: Supply chain - sign, attest, pin

**Files:**
- Create: `.github/workflows/supply-chain.yml`
- Create: `learning/stages/06-supply-chain.md`
- Modify: every workflow in `.github/workflows/` (pin `uses:` to SHAs)

**Interfaces:**
- Produces: job `publish`. Image `ghcr.io/<owner>/<repo>` signed with Cosign keyless and carrying a provenance attestation.

- [ ] **Step 1: Branch**

Run: `git switch main && git pull && git switch -c devsecops/05-supply-chain`

- [ ] **Step 2: Write `.github/workflows/supply-chain.yml`**

```yaml
name: supply-chain

# Main and tags only. Never on pull_request: this job has packages:write and
# id-token:write, and a PR from a fork must not be able to reach either.
on:
  push:
    branches: [main]
    tags: ["v*"]

permissions:
  contents: read

jobs:
  publish:
    name: publish
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write       # keyless signing: GitHub's OIDC token is the identity
      attestations: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
      - id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
      - uses: sigstore/cosign-installer@v3
      - name: Sign the image by digest
        env:
          DIGEST: ${{ steps.build.outputs.digest }}
        run: cosign sign --yes "ghcr.io/${GITHUB_REPOSITORY,,}@${DIGEST}"
      - uses: actions/attest-build-provenance@v2
        with:
          subject-name: ghcr.io/${{ github.repository }}
          subject-digest: ${{ steps.build.outputs.digest }}
          push-to-registry: true
```

- [ ] **Step 3: Write `learning/stages/06-supply-chain.md`**

````markdown
# Stage 6: Supply chain - signing, attestation and pinning

## The threat

Between your source and the thing that runs, there are build tools, third-party
GitHub Actions and a registry. If any of them is tampered with, you ship
something you never wrote. Mutable tags (`@v4`, `:latest`) can be moved to
malicious code after you reviewed them.

## The tool

- **Cosign (keyless)** signs the image digest using the workflow's own GitHub
  identity, recorded in a public transparency log. No private key to store or
  leak.
- **Build provenance attestation** is a signed statement of *which repo, commit
  and workflow* produced this image.
- **SHA pinning** replaces `uses: owner/action@v4` with the full commit SHA
  (with the tag in a comment), so a retagged action cannot change what runs.
  Dependabot's `github-actions` ecosystem keeps the SHAs current.
- **Least privilege:** every workflow declares `permissions:`; only
  `supply-chain.yml` gets write scopes, and only on main and tags.

## Reading the output

Verify instead of trusting:

    cosign verify ghcr.io/OWNER/REPO@sha256:... \
      --certificate-identity-regexp 'https://github.com/OWNER/REPO/.github/workflows/supply-chain.yml@.*' \
      --certificate-oidc-issuer https://token.actions.githubusercontent.com
    gh attestation verify oci://ghcr.io/OWNER/REPO@sha256:... -R OWNER/REPO

A signature proves *who built it and from what*. It does not prove the code is
free of vulnerabilities or that the build was not run on malicious source.

## Do the lab

`learning/labs/07-poisoned-workflow/`

## Elsewhere

GitLab: container registry plus Cosign in a job, SLSA attestations in recent
versions. Others: Notary, in-toto, SLSA generators.
````

- [ ] **Step 4: Pin every `uses:` to a commit SHA**

Run (needs a GitHub token to resolve tags):

```bash
docker run --rm -e GITHUB_TOKEN="$(gh auth token)" -v "$PWD:/repo" -w /repo \
  ghcr.io/suzuki-shunsuke/pinact:latest run
```

Expected: every `uses: x/y@vN` in `.github/workflows/*.yml` becomes `uses: x/y@<40-hex-sha> # vN`. If pinact is unavailable, resolve each by hand: `gh api repos/OWNER/ACTION/commits/TAG --jq .sha`. Never type a SHA from memory.

- [ ] **Step 5: Verify pinning is complete**

Run: `grep -rnE 'uses: [^ ]+@' .github/workflows | grep -vE '@[0-9a-f]{40}'`
Expected: no output (every `uses:` is pinned). Local `uses: ./...` paths, if any, are exempt.

- [ ] **Step 6: Lint, commit**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`
Expected: no output, exit 0.

```bash
git add .github/workflows learning/stages/06-supply-chain.md
git commit -m "feat: supply chain - Cosign, provenance, SHA-pinned actions

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Task 13: Lab 07 - poisoned workflow

**Files:**
- Create: `learning/labs/07-poisoned-workflow/vuln.patch`
- Create: `learning/labs/07-poisoned-workflow/README.md`
- Create: `learning/labs/07-poisoned-workflow/solution.md`

**Interfaces:**
- Consumes: `lab.sh`. Uses `zizmor` locally; it is not part of the pipeline.

- [ ] **Step 1: Create the flawed workflow**

Create `.github/workflows/lab-07.yml` (temporary, for patch export only):

```yaml
name: lab-07

on:
  pull_request:

permissions: write-all

jobs:
  greet:
    runs-on: ubuntu-latest
    steps:
      - uses: some-org/unreviewed-action@main
      - name: Say hello
        run: echo "PR title is ${{ github.event.pull_request.title }}"
```

Three flaws: an unpinned third-party action on a moving branch, `write-all` permissions, and a PR title interpolated straight into a shell script (script injection).

- [ ] **Step 2: Export the patch (new file, so stage it) and remove the file**

```bash
mkdir -p learning/labs/07-poisoned-workflow
git add -N .github/workflows/lab-07.yml
git diff -- .github/workflows/lab-07.yml > learning/labs/07-poisoned-workflow/vuln.patch
rm .github/workflows/lab-07.yml
git reset -q .github/workflows/lab-07.yml
bash learning/labs/lab.sh check
```

Expected: `ok` for all lab patches; `git status --short` shows only the new `learning/` files.

- [ ] **Step 3: Write `README.md`**

````markdown
# Lab 07: poisoned workflow

**Flaw:** a new workflow with (1) `some-org/unreviewed-action@main`, a
third-party action on a moving branch, (2) `permissions: write-all`, (3) the PR
title interpolated into a `run:` script.
**Should flag:** Dependabot would track the action once pinned; nothing in the
pipeline reads workflow *logic*. This is a review exercise: use `zizmor`, a
static analyser for GitHub Actions.
**Stage:** `../../stages/06-supply-chain.md`

## Run it

    bash learning/labs/lab.sh start 07-poisoned-workflow
    docker run --rm -v "$PWD:/repo" -w /repo ghcr.io/zizmorcore/zizmor:latest .github/workflows/lab-07.yml

No push is needed for this lab. The action `some-org/unreviewed-action` does
not exist, so do **not** push this branch: the PR's workflow run would fail
resolving it.

## What to look for

Read each zizmor finding and explain the attack in a sentence: how would a
malicious PR title run commands with `write-all` permissions? How would a
compromised `@main` of a third-party action reach your repo's secrets?

## Observed output

Paste the zizmor findings here after your first run.

## Finish

    bash learning/labs/lab.sh finish 07-poisoned-workflow
````

- [ ] **Step 4: Write `solution.md`**

````markdown
# Lab 07 solution

1. Pin the action to a full commit SHA you have reviewed, with the version in a
   comment, and let Dependabot's `github-actions` updater maintain it.
2. Replace `permissions: write-all` with the minimum: usually
   `permissions: { contents: read }`, granting a write scope per job only where
   a step needs it.
3. Pass untrusted values through the environment, never into the script text:

   ```yaml
   env:
     PR_TITLE: ${{ github.event.pull_request.title }}
   run: echo "PR title is $PR_TITLE"
   ```
   The shell then treats it as data, not code.
4. Confirm with `zizmor` that all three findings are gone.
````

- [ ] **Step 5: Commit**

```bash
git add learning/labs/07-poisoned-workflow
git commit -m "feat: lab 07, poisoned workflow

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Ask the owner, then push the phase branch and open the PR**

```bash
git push -u origin devsecops/05-supply-chain
gh pr create --title "DevSecOps phase 5: supply chain, SHA pinning, lab 07" \
  --body "Adds supply-chain.yml (Cosign keyless + provenance), pins all actions to SHAs and adds lab 07.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Expected on the PR: all workflows still run with pinned actions; `supply-chain` does **not** run on the PR (it is push-to-main only).

- [ ] **Step 7: After merge, verify the signed image**

Wait for `supply-chain` to complete on `main`, then run both verification commands from `learning/stages/06-supply-chain.md` against the digest in the run's summary.
Expected: `cosign verify` prints the signature payload and certificate identity naming `supply-chain.yml`; `gh attestation verify` prints `Verification succeeded`.

---

## Task 14: Triage, gating and GitLab mapping

**Files:**
- Create: `learning/gitlab-equivalents.md`
- Modify: `learning/triage-log.md`
- Modify: every workflow containing a `# report-only` marker
- Modify: `learning/repo-settings.md`

**Interfaces:**
- Consumes: the report-only marker convention (Task 1), the job names from Tasks 1, 3, 4, 8 (`gitleaks`, `labs-check`, `pip-audit`, `npm-audit`, `dependency-review`, `semgrep`, `analyze (python)`, `analyze (javascript-typescript)`, `hadolint`, `image-scan`).

- [ ] **Step 1: Branch**

Run: `git switch main && git pull && git switch -c devsecops/06-gating`

- [ ] **Step 2: Collect the baseline**

For each of `secrets`, `sca`, `sast`, `container`, `dast`, open the latest `main` run. List every finding: tool, rule, location. Include the dates and the resolved Python versions for `pip-audit` (Review Focus 3).

- [ ] **Step 3: Triage with the owner**

Go through the list *with the owner*. For each finding decide fix, suppress or accept, and write one row in `learning/triage-log.md`:

```markdown
| 2026-10-14 | container | Trivy DS002 | docker/Dockerfile | fix | image runs as root; add a non-root USER |
```

Apply the decisions: fixes as code changes, suppressions in the tool's own config with the reason inline (`# nosemgrep: <rule> -- <reason>`, a commented `.trivyignore` line with an expiry date, a `.gitleaks.toml` allowlist entry with a description). Each fix is its own commit. A real secret finding is rotated first (tell the owner), never history-rewritten without their say-so.

- [ ] **Step 4: Write `learning/gitlab-equivalents.md`**

````markdown
# GitLab CI equivalents

| Stage | This repo (GitHub) | GitLab CI |
|---|---|---|
| Secrets | `secrets.yml` (Gitleaks), push protection | `Secret-Detection.gitlab-ci.yml` (Gitleaks) |
| SCA | `sca.yml` (pip-audit, npm audit, dependency-review), Dependabot | `Dependency-Scanning.gitlab-ci.yml` (Gemnasium), Renovate |
| SAST | `sast.yml` (Semgrep, CodeQL) | `SAST.gitlab-ci.yml` (Semgrep for most languages) |
| Container | `container.yml` (Hadolint, Trivy, Syft) | `Container-Scanning.gitlab-ci.yml` (Trivy) |
| DAST | `dast.yml` (ZAP baseline) | `DAST.gitlab-ci.yml` (ZAP-based) |
| Supply chain | `supply-chain.yml` (Cosign, attestations), SHA pinning | Cosign in a job, SLSA attestations, container registry |
| Gating | Branch protection, required checks | Merge request approval rules, security policies (paid tiers) |

Most GitLab templates wrap the same open-source tools used here, so the skills
carry over: the difference is where results are shown (the merge request widget
and Security Dashboard, some features paid-tier) and how jobs are declared
(`include:` of a template instead of a workflow file per stage).
````

- [ ] **Step 5: Flip clean stages to blocking**

For each stage whose findings are all fixed, suppressed or accepted, delete its marker lines:

```bash
sed -i '/continue-on-error: true  # report-only$/d' .github/workflows/secrets.yml
```

Do this per file, only for clean stages, and name them in the commit message. A stage with open findings keeps its marker and gets a line in the triage log saying when to revisit.

- [ ] **Step 6: Lint and commit**

Run: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`
Expected: no output, exit 0.

```bash
git add learning/gitlab-equivalents.md learning/triage-log.md .github/workflows
git commit -m "feat: triage baseline findings, enforce clean stages

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Push, open the PR, and confirm every required check is green on it**

Ask first, then push `devsecops/06-gating` and open the PR. Required checks must have run recently on `main` to be selectable in branch protection.

- [ ] **Step 8: Write the branch-protection steps into `learning/repo-settings.md`**

Replace the "Branch protection on `main`" row's "Added in Task 14" with a section:

````markdown
## Branch protection on main

Require these status checks, and "branches must be up to date": `gitleaks`,
`labs-check`, `pip-audit`, `npm-audit`, `dependency-review`, `semgrep`,
`analyze (python)`, `analyze (javascript-typescript)`, `hadolint`, `image-scan`.

Do **not** require `zap-baseline`: it is path-filtered, so a PR that does not
touch `server/` or `docker/` never produces the check and would be blocked
forever. Do not require `publish`: it runs only on main.

    gh api -X PUT repos/OWNER/REPO/branches/main/protection \
      -H "Accept: application/vnd.github+json" --input - <<'JSON'
    {
      "required_status_checks": {
        "strict": true,
        "contexts": ["gitleaks", "labs-check", "pip-audit", "npm-audit",
          "dependency-review", "semgrep", "analyze (python)",
          "analyze (javascript-typescript)", "hadolint", "image-scan"]
      },
      "enforce_admins": false,
      "required_pull_request_reviews": null,
      "restrictions": null
    }
    JSON

Only include the checks for stages that are blocking. A required check whose
step is still `continue-on-error` always passes and enforces nothing.
````

- [ ] **Step 9: Ask the owner, then apply branch protection**

Show the owner the exact command and the list of required checks. Run it only on their say-so. `enforce_admins: false` lets the owner push a hotfix in an emergency; mention it and let them choose.

- [ ] **Step 10: End-to-end verification against the success criteria**

1. All six stage workflows ran on a PR and on schedule: check each workflow's run history for a `schedule` event.
2. Re-run `bash learning/labs/lab.sh start <name>` for a lab whose stage is now blocking (for example `01-leaked-secret`), push, and confirm the PR **cannot be merged** because the required check fails; then `lab.sh finish`.
3. `main` has no unexplained findings: every item is in `learning/triage-log.md`.
4. Ask the owner to explain one stage back using only the `learning/` docs; fix any doc that left them stuck.

- [ ] **Step 11: Restore stashed work if Task 0 stashed any**

Run: `git stash list`
Expected: if `pre-devsecops` is listed, `git stash pop` on a branch where it makes sense, and tell the owner.
