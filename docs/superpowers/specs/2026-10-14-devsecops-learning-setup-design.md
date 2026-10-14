# DevSecOps learning setup — design

Date: 2026-10-14

## Purpose

Turn this repo into a hands-on DevSecOps learning environment. The owner's goal
is career breadth: a tour of the standard pipeline (secrets, SAST, SCA,
container, DAST, supply chain, gating), not deep hardening of this one app.

Platform: GitHub (the repo is public, with PR history there, so CodeQL, secret
scanning, Dependabot and attestations are free). GitLab is covered only as a
reference mapping, not a second pipeline.

## Success criteria

1. All six stages run on a PR and on a schedule.
2. Each of the seven labs fails its expected check and passes after the fix.
3. `main` is clean or carries documented suppressions, and the required checks
   are enforced by branch protection.
4. The owner can explain each stage in their own words from the `learning/` docs.

## Approach

Hybrid: open-source tools run explicitly in Actions as the portable backbone
(Gitleaks, Semgrep, pip-audit, npm audit, Hadolint, Trivy, Syft, Cosign, ZAP),
with GitHub-native features layered on top (CodeQL, Dependabot, dependency
review, secret scanning with push protection) so both skill sets are learned and
their findings can be compared.

## Pipeline structure

One workflow per stage, so each appears as its own PR check.

| Workflow | Tools | Runs on |
|---|---|---|
| `secrets.yml` | Gitleaks (full history) | PR, push to main |
| `sast.yml` | Semgrep, CodeQL (Python, JS) | PR, push to main, weekly |
| `sca.yml` | pip-audit, npm audit, dependency-review | PR, push to main, weekly |
| `container.yml` | Hadolint, build, Trivy image scan, Syft SBOM | PR, push to main |
| `supply-chain.yml` | Cosign keyless signing, build attestation | main and tags only |
| `dast.yml` | `docker compose up`, OWASP ZAP baseline | weekly, plus PRs touching `server/` or `docker/` |

Also:

- `.github/dependabot.yml` covers pip, npm, Docker and Actions.
- Secret scanning and push protection are enabled in repo settings; these steps
  are documented, since they cannot be toggled from the CLI session.
- Actions are pinned to commit SHAs; every workflow sets least-privilege
  `permissions:`.
- Results go to the run summary, and SARIF uploads go to the Security tab.

## Learning material (`learning/`)

- `README.md`: syllabus and suggested order, with an "explain it back"
  self-check question per stage.
- `stages/NN-<stage>.md`: per stage, (1) the threat, (2) the tool and its key
  config, (3) an annotated sample finding from this repo, (4) link to the lab,
  (5) equivalents in GitLab CI and elsewhere.
- `labs/NN-<name>/`: `vuln.patch`, a README (the flaw, the check that should
  fail, and why, with expected failure output) and `solution.md`.
- `gitlab-equivalents.md`: reference table mapping each stage to its GitLab CI
  template or job.
- `triage-log.md`: one entry per baseline finding: what it was, the decision
  (fix, suppress or accept), and the reason.

## Labs

Labs live only as patches. They are applied on throwaway `lab/NN-...` branches,
opened as PRs to watch the pipeline fail, fixed, and never merged, so `main`
never contains deliberately vulnerable code.

| # | Lab | Planted flaw | Expected failing check |
|---|---|---|---|
| 01 | Leaked secret | Fake API key and JWT signing secret hardcoded in `server/settings.py` | Gitleaks |
| 02 | Vulnerable dependency | Old pinned package with a known CVE in `pyproject.toml` or `client/package.json` | pip-audit, npm audit, dependency-review |
| 03 | SQL injection | A route building a query by string formatting | Semgrep, CodeQL |
| 04 | Weak crypto and auth | MD5 passcode hashing, or a session cookie without `Secure` or `HttpOnly` | Semgrep, CodeQL |
| 05 | Insecure container | Dockerfile runs as root, unpinned `latest` base image, outdated OS package | Hadolint, Trivy |
| 06 | Permissive web config | Wildcard CORS, missing security header | ZAP baseline |
| 07 | Poisoned workflow | Unpinned third-party action, broad `permissions:` | Dependabot, plus a workflow-review exercise |

Planted secrets use obviously fake but scanner-detectable formats. Nothing is
ever taken from `docker/.env`, `data/` or `input/`.

## Triage and gating

- Phase 1 runs every scanner in report-only mode against the real app.
- Baseline findings are triaged into `learning/triage-log.md`.
- Every suppression carries a written reason: `# nosemgrep: rule-id -- reason`,
  a commented `.trivyignore` entry with an expiry date, and a Gitleaks allowlist
  entry with a justification.
- Once a stage is clean, it becomes blocking and is added to the required
  checks in branch protection.

## Build order

Each phase is its own PR with its own verification.

1. Foundation: `learning/` skeleton, Dependabot, Gitleaks in report-only mode,
   lab 01.
2. SCA and SAST: pip-audit, npm audit, Semgrep, CodeQL; labs 02–04.
3. Container: Hadolint, Trivy, SBOM; lab 05.
4. DAST: compose up plus ZAP; lab 06.
5. Supply chain: Cosign, attestations, action pinning; lab 07.
6. Gating: triage, flip stages to blocking, document branch protection.

## Verification

For each lab: the patch applies cleanly to current `main`; the intended check
fails on the lab branch and passes on `main`; the expected failure output is
recorded in the lab README.

## Constraints and risks

- The Claude Code sandbox in the authoring session blocked shell commands
  (`apply-seccomp ... Permission denied`), so `git`, `docker` and the scanners
  could not be run locally. Verification therefore happens in GitHub Actions on
  pushed branches, or by the owner running commands themselves.
- No branches are pushed and no PRs opened without the owner's confirmation.
- ZAP plus compose costs a few minutes of Actions time per run; it is limited
  to the weekly schedule and PRs touching `server/` or `docker/`.
- The app handles real finances: `data/`, `input/` and `docker/.env` must stay
  gitignored, and the secrets scan verifies this automatically.

## Out of scope

- Self-hosting GitLab or any runner.
- Kubernetes, Terraform or other IaC scanning beyond the Dockerfile and compose
  file.
- Hardening the app beyond baseline findings the owner chooses to fix.
- Paid tools or accounts other than GitHub.
