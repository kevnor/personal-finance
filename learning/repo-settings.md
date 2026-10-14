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
