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
