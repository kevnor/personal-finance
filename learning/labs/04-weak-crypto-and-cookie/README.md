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
