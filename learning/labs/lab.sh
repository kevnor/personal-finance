#!/usr/bin/env bash
# Drive a lab: start a throwaway branch with the flaw applied, check that every
# patch still applies to the current tree, or discard a finished lab branch.
# Lab branches are never merged.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
labs="$root/learning/labs"

usage() {
  echo "usage: lab.sh start <NN-name> | check | finish <NN-name>" >&2
  exit 2
}

case "${1:-}" in
  start)
    name=${2:-}; [ -n "$name" ] || usage
    git switch -c "lab/$name" main
    git apply --index "$labs/$name/vuln.patch"
    git commit -m "lab($name): plant the flaw (never merge)"
    echo "Next: git push -u origin lab/$name, open a PR against main, watch the checks."
    ;;
  check)
    status=0
    for patch in "$labs"/*/vuln.patch; do
      [ -e "$patch" ] || continue
      if git apply --check "$patch"; then echo "ok   $patch"; else echo "FAIL $patch"; status=1; fi
    done
    exit "$status"
    ;;
  finish)
    name=${2:-}; [ -n "$name" ] || usage
    git switch main
    git branch -D "lab/$name"
    echo "Close the PR unmerged, then: git push origin --delete lab/$name"
    ;;
  *)
    usage
    ;;
esac
