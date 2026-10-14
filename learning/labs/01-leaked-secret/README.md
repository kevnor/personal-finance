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
