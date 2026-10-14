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
