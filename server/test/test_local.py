"""The household's own file: rules and corrections that must not be committed.

Some of what this app needs to categorise correctly identifies the people
using it -- a card account number, an employer, a payment to a named person.
Those live in one gitignored JSON file beside the database. What matters is
that the mechanism works, that a missing file is an ordinary state rather
than a failure, and that a malformed one is loud rather than silently
ignoring a household's corrections.
"""
import json
from pathlib import Path

import pytest

from server.lib import categorise, local

ROOT = Path(__file__).resolve().parents[2]


def write(tmp_path, payload) -> Path:
    path = local.path_for(tmp_path)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# -- absence is normal ------------------------------------------------------

def test_no_file_at_all_loads_as_empty(tmp_path):
    """A fresh clone has no household attached to it. That is the state the
    repository ships in, so it must be the state that works."""
    assert local.load(local.path_for(tmp_path)) is local.EMPTY
    assert local.load(None) is local.EMPTY
    assert local.EMPTY.is_empty


def test_an_empty_object_loads_as_empty(tmp_path):
    assert local.load(write(tmp_path, {})).is_empty


# -- malformed is loud ------------------------------------------------------

def test_invalid_json_raises_rather_than_degrading(tmp_path):
    """Silently continuing would mean a household's corrections quietly stop
    being applied, which is exactly the failure this file exists to prevent."""
    path = local.path_for(tmp_path)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        local.load(path)


def test_a_top_level_list_is_refused(tmp_path):
    with pytest.raises(ValueError, match="JSON object"):
        local.load(write(tmp_path, [1, 2, 3]))


@pytest.mark.parametrize("payload, missing", [
    ({"rules": [{"category": "Groceries"}]}, "pattern"),
    ({"rules": [{"pattern": "x"}]}, "category"),
    ({"recategorisations": [{"date": "2026-07-02", "amount": -1}]}, "description"),
    ({"recategorisations": [
        {"date": "d", "description": "x", "amount": -1}]}, "category"),
    ({"reimbursements": [
        {"date": "d", "description": "x", "amount": -1}]}, "expected_from"),
])
def test_a_missing_field_names_itself(tmp_path, payload, missing):
    with pytest.raises(ValueError, match=missing):
        local.load(write(tmp_path, payload))


# -- rules ------------------------------------------------------------------

def test_rules_load_with_their_review_flag(tmp_path):
    data = local.load(write(tmp_path, {"rules": [
        {"pattern": "acme", "category": "Groceries"},
        {"pattern": "giro.*acme", "category": "Salary", "needs_review": True},
    ]}))
    assert data.rules == (("acme", "Groceries", False),
                          ("giro.*acme", "Salary", True))
    assert not data.is_empty


def test_a_household_rule_beats_the_built_in_rules(tmp_path):
    """They are more specific than anything generic could be: an account
    number matches one account and nothing else."""
    rules = local.load(write(tmp_path, {"rules": [
        {"pattern": r"til\s*:\s*99900011122", "category": "Credit card payment"},
    ]})).rules

    description = "Overføring Innland  396 Til : 99900011122 Mobil Betaling"
    # Without it the line is an unrecognised Vipps transfer, flagged.
    assert categorise.categorise(description).category == "Vipps P2P - unspecified"
    # With it, the card settlement it actually is -- which is what keeps the
    # card's own purchase lines from being counted twice.
    verdict = categorise.categorise(description, extra_rules=rules)
    assert verdict.category == "Credit card payment"
    assert verdict.needs_review is False


def test_a_taught_rule_still_beats_a_household_rule(tmp_path):
    """`learned` is what the user just chose in the UI, so it wins over
    everything, including the file they edited last month."""
    rules = local.load(write(tmp_path, {"rules": [
        {"pattern": "acme", "category": "Groceries"}]})).rules
    verdict = categorise.categorise(
        "ACME Store", learned={"acme": "Gifts"}, extra_rules=rules)
    assert verdict.category == "Gifts"


def test_categorise_is_unchanged_when_no_household_rules_are_given():
    """The golden fixture runs without a file, so the built-in behaviour must
    not depend on one existing."""
    assert categorise.categorise("Rema Lorenveien, Oslo", extra_rules=()) \
        == categorise.categorise("Rema Lorenveien, Oslo")


# -- corrections ------------------------------------------------------------

def test_corrections_load_with_their_content_key(tmp_path):
    data = local.load(write(tmp_path, {
        "recategorisations": [{"date": "2026-07-02", "description": "Acme",
                               "amount": -189.9, "category": "Gifts"}],
        "reimbursements": [{"date": "2026-07-30", "description": "Phone",
                            "amount": -13990, "expected_from": "Acme AS",
                            "note": "paid by employer"}],
    }))
    row, category = data.recategorisations[0]
    assert (row.date, row.description, row.amount) == ("2026-07-02", "Acme", -189.9)
    assert category == "Gifts"

    row, expected_from, note = data.reimbursements[0]
    assert row.amount == -13990.0
    assert (expected_from, note) == ("Acme AS", "paid by employer")


def test_a_reimbursement_note_is_optional(tmp_path):
    data = local.load(write(tmp_path, {"reimbursements": [
        {"date": "d", "description": "x", "amount": -1,
         "expected_from": "Acme AS"}]}))
    assert data.reimbursements[0][2] is None


# -- the file must never be committed ---------------------------------------

def test_the_local_file_is_gitignored():
    """The whole point. It lives beside the database on the data volume, and
    `data/` is ignored -- so the household's own facts cannot be pushed by
    accident."""
    import subprocess

    candidate = ROOT / "data" / local.FILENAME
    result = subprocess.run(
        ["git", "check-ignore", str(candidate)],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"{candidate} is NOT gitignored"
