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
