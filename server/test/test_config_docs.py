"""Configuration is only as good as its documentation.

Every `PF_*` variable is optional and falls back to a default, which is what
makes an undocumented one dangerous rather than merely untidy: nothing fails
when you do not know it exists. `PF_LOCAL_FILE` was read by `settings.py` for
a whole release while the README's list -- written as a closed one, "all
optional: ..." -- did not name it, so someone repointing `PF_DATA_DIR` at a
new volume had no way to learn that the household's corrections followed it.

Nothing here reads a value or starts an app. These are assertions about names:
that the set the code reads, the set the README documents, and the set the
container sets are the same set, in the directions where a difference means a
real defect.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

# Where a PF_* variable is actually read. The client has one of its own --
# the dev server's proxy target -- so a check that looked only at the server
# would call `PF_API_ORIGIN` an undocumented stray.
READERS = [
    ROOT / "server" / "settings.py",
    ROOT / "client" / "vite.config.js",
]
# Where the shipped container sets them. Setting is not the same as reading:
# a name misspelt here fails silently, because the app simply takes its
# default and nothing anywhere reports that the setting was ignored.
SETTERS = [
    ROOT / "docker" / "Dockerfile",
    ROOT / "docker" / "compose.yaml",
]

NAME = re.compile(r"\bPF_[A-Z0-9_]+\b")


def names_in(*paths) -> set[str]:
    return {n for p in paths for n in NAME.findall(p.read_text(encoding="utf-8"))}


def test_every_variable_the_code_reads_is_documented():
    """The failure this file exists for. An undocumented variable is one
    nobody can use and nobody can discover, since its absence looks exactly
    like its default."""
    undocumented = names_in(*READERS) - names_in(README)
    assert not undocumented, (
        f"read by the code but absent from README.md: {sorted(undocumented)}")


def test_every_variable_the_readme_documents_is_actually_read():
    """The other direction, and the one a rename breaks: the old name stays
    in the README, reads as current, and silently does nothing."""
    stale = names_in(README) - names_in(*READERS)
    assert not stale, (
        f"documented in README.md but read by nothing: {sorted(stale)}")


def test_every_variable_the_container_sets_is_one_the_app_reads():
    """A typo in compose.yaml or the Dockerfile has no symptom -- the app
    takes its default and starts cleanly -- so it has to be caught here."""
    ignored = names_in(*SETTERS) - names_in(*READERS)
    assert not ignored, (
        f"set by the container but read by nothing: {sorted(ignored)}")


def test_the_readme_actually_lists_some_variables():
    """Guards the three assertions above against passing vacuously: each is a
    set difference, and an empty left-hand side satisfies all of them. If a
    refactor moves configuration out of settings.py, or the README section is
    deleted, these must start failing rather than quietly staying green."""
    assert len(names_in(*READERS)) >= 5
    assert len(names_in(README)) >= 5
    assert len(names_in(*SETTERS)) >= 2
