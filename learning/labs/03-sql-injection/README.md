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
