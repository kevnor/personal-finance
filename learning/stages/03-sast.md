# Stage 3: Static application security testing (SAST)

## The threat

Bugs *you* wrote: SQL built by string formatting, weak hashes, cookies missing
security flags, user input reaching a dangerous function. SAST reads the source
without running it.

## The tool

- **Semgrep** is pattern matching on syntax trees. Fast, readable rules, easy
  to write your own. `p/python`, `p/security-audit` and `p/javascript` are
  registry rulesets.
- **CodeQL** compiles the code into a database and runs *dataflow* queries: it
  follows a value from an HTTP parameter to a database call across functions.
  Slower, deeper, fewer false positives for injection bugs. Results appear in
  the repo's Security tab.

Running both is deliberate: compare what each finds and misses.

## Reading the output

A finding is a rule ID, file, line and a message. For CodeQL, open the *path*:
the source (where untrusted data enters) and the sink (where it does damage).
Triage by asking whether the source is attacker-controlled. Suppress a false
positive in code with `# nosemgrep: rule-id -- reason`.

## Do the labs

`learning/labs/03-sql-injection/` and `learning/labs/04-weak-crypto-and-cookie/`

## Elsewhere

GitLab: `SAST.gitlab-ci.yml` (Semgrep for most languages). Others: SonarQube,
Bandit (Python only).
