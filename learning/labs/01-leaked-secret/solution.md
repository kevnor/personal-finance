# Lab 01 solution

1. Treat the key as compromised and rotate it at its source. Deleting the line
   does not un-leak it: it is in the commit history of the pushed branch.
2. Read the value from the environment instead:
   `INTERNAL_API_KEY = os.environ.get("PF_INTERNAL_API_KEY", "")` and document
   the variable in `docker/.env.example`.
3. Push the fix commit. Gitleaks still reports the earlier commit in the PR's
   history, because it scans commits, not just the final tree. That is
   expected; it is why a real leak means rotation plus, if warranted, a history
   rewrite coordinated with everyone who has cloned.
4. For a false positive, allowlist narrowly in `.gitleaks.toml` with a reason.
