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
