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
