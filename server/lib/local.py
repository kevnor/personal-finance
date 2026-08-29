"""Household-specific data that must not live in the repository.

Some of what this app needs to categorise correctly identifies the people
using it: a card account number, an employer's name, a payment to a named
person that a rule cannot infer the purpose of. Those are facts about one
household, not about budgeting, and a repository is the wrong place for
them — they end up in every clone, every diff and every fork, and they
cannot be taken back out of a history once pushed.

So they live in one JSON file beside the database, on the same volume, and
gitignored: the same reasoning that puts the passcode there rather than in
the database. The code here carries the mechanism; the file carries the
facts.

Everything is optional. With no file at all the app still runs — it simply
categorises by the built-in rules alone and applies no corrections, which is
the correct behaviour for a fresh clone that has no household attached to it
yet. See README "Local configuration" for the format.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

FILENAME = "local.json"


@dataclass(frozen=True)
class Correction:
    """One hand-made fact about one specific transaction.

    Keyed on the row's own content rather than an id, because ids are
    assigned by insertion order and mean nothing across databases.
    """
    date: str
    description: str
    amount: float


@dataclass(frozen=True)
class LocalData:
    # (pattern, category, needs_review), tested before the built-in rules
    # because they are more specific than anything generic could be.
    rules: tuple[tuple[str, str, bool], ...] = ()
    recategorisations: tuple[tuple[Correction, str], ...] = ()
    reimbursements: tuple[tuple[Correction, str, str | None], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.rules or self.recategorisations or self.reimbursements)


EMPTY = LocalData()


def path_for(data_dir: str | Path) -> Path:
    return Path(data_dir) / FILENAME


def load(path: str | Path | None) -> LocalData:
    """Read the local file. A missing file is normal and yields EMPTY.

    A malformed one is not: it is silently ignoring a household's own
    corrections that raises the loudest, so a bad file raises rather than
    degrading to "no corrections today".
    """
    if path is None:
        return EMPTY
    path = Path(path)
    if not path.exists():
        return EMPTY

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")

    return LocalData(
        rules=tuple(_rule(r, path) for r in raw.get("rules", [])),
        recategorisations=tuple(
            (_correction(r, path), _require(r, "category", path))
            for r in raw.get("recategorisations", [])),
        reimbursements=tuple(
            (_correction(r, path), _require(r, "expected_from", path),
             r.get("note"))
            for r in raw.get("reimbursements", [])),
    )


def _rule(row: dict, path: Path) -> tuple[str, str, bool]:
    return (_require(row, "pattern", path), _require(row, "category", path),
            bool(row.get("needs_review", False)))


def _correction(row: dict, path: Path) -> Correction:
    return Correction(_require(row, "date", path),
                      _require(row, "description", path),
                      float(_require(row, "amount", path)))


def _require(row: dict, key: str, path: Path):
    if key not in row:
        raise ValueError(f"{path}: entry is missing {key!r}: {row}")
    return row[key]
