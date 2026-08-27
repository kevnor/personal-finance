import json
from pathlib import Path

import pytest

from server.lib import categorise

FIXTURE = Path(__file__).parent / "fixtures" / "categorisation.json"

# Assigned by the account holder, not derivable from text. Covered in Task 9.
CORRECTED = ("Ingvild Kvamme Berg BokTpp", "Torkel Aalborg BokTpp")


def golden():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [r for r in rows if not any(c in r["description"] for c in CORRECTED)]


@pytest.mark.parametrize("row", golden(), ids=lambda r: r["description"][:40])
def test_golden_categorisation(row):
    assert categorise.categorise(row["description"]) == categorise.Verdict(
        row["category"], row["needs_review"])


def test_memo_glued_to_tpp_suffix_still_matches():
    """Regression: \\b fails between 'Kino' and 'Tpp' — both are word chars."""
    assert categorise.categorise(
        "Overføring  9230000000 Vetle Nyhus Dahl KinoTpp: Vipps"
    ).category == "Entertainment"
    assert categorise.categorise(
        "Overføring  92200000000 Ingvild Kvamme Berg LadingTpp: Vipps"
    ).category == "Fuel & EV charging"


def test_unmatched_vipps_is_flagged_for_review():
    v = categorise.categorise("Overføring  90200000000 Ingvild Kvamme Berg Tpp: Vipps")
    assert v.category == "Vipps P2P - unspecified"
    assert v.needs_review is True


def test_unknown_merchant_is_uncategorised_and_flagged():
    v = categorise.categorise("Visa  100121  Ecom Capital AS")
    assert v.category == "Uncategorised"
    assert v.needs_review is True


def test_learned_rule_beats_builtin_rule():
    v = categorise.categorise(
        "Varekjøp Rema Lorenveien Lørenveien 3 Oslo",
        learned={"rema lorenveien": "Restaurants & takeaway"})
    assert v.category == "Restaurants & takeaway"
    assert v.needs_review is False


def test_is_pure_no_arguments_mutated():
    learned = {"foo": "Groceries"}
    categorise.categorise("foo bar", learned=learned)
    assert learned == {"foo": "Groceries"}


def test_counterparty_extracted_from_vipps_star_form():
    assert categorise.extract_counterparty(
        "Vipps*Ingvild Kvamme B, Oslo") == "Ingvild Kvamme B"


def test_counterparty_none_for_plain_merchant():
    assert categorise.extract_counterparty("JOKER LØREN STA, Oslo") is None


def test_treatments_keys_are_known_categories():
    """A typo in a TREATMENTS key would silently leave that category on the
    schema defaults instead of raising, so this pins every key to a real
    category name."""
    category_names = {name for name, _kind in categorise.CATEGORIES}
    assert set(categorise.TREATMENTS) <= category_names


def test_treatments_values_are_valid_enum_members():
    """A typo in a TREATMENTS value (e.g. "comitted") would otherwise survive
    until a migration's CHECK constraint fails at runtime."""
    assert all(
        b in {"fixed", "variable", "exceptional"}
        and c in {"settlement", "committed", "savings"}
        for b, c in categorise.TREATMENTS.values())


def test_bok_memo_glued_to_tpp_suffix_matches_books():
    """The \\bbok(tpp|ref) rule has no real-data coverage: its only matching
    rows in the fixture are the two CORRECTED exclusions. Cover it directly
    with a synthetic description shaped like the real Vipps memos (a 'Bok'
    memo glued to a 'Tpp:' suffix, same as the Kino/Lading regression case)."""
    assert categorise.categorise(
        "Overføring  4699999999 Vetle Nyhus Dahl BokTpp: Vipps"
    ).category == "Books"


def test_unsplit_loan_term_is_categorised_and_treated_as_fixed():
    """The ^l.n\\b|avdrag rule had no coverage anywhere, and its category was
    missing from TREATMENTS -- so it inherited the schema's 'variable'
    default. Nothing lands there today because the one loan line splits, but
    a statement whose itemisation `derive` cannot parse would put the whole
    ~13 288 kr term into a single week's envelope."""
    v = categorise.categorise("Lån  12345678901 Avdrag Og Renter")
    assert v.category == "Mortgage & loan"
    assert v.needs_review is True
    assert categorise.TREATMENTS[v.category] == ("fixed", "settlement")


def test_categories_that_must_not_fall_back_to_variable_are_listed():
    """A category absent from TREATMENTS silently takes budget_treatment =
    'variable', i.e. it lands in the weekly envelope. That default is right
    for groceries and wrong for a loan term, and the difference is invisible
    until the money is counted."""
    treatment = {
        name: categorise.TREATMENTS.get(name, ("variable", "settlement"))[0]
        for name, _kind in categorise.CATEGORIES}
    assert treatment["Mortgage & loan"] == "fixed"
    assert treatment["Student loan"] == "fixed"
    assert treatment["Mortgage - interest"] == "fixed"
    assert treatment["Mortgage - fees"] == "fixed"
    assert treatment["Groceries"] == "variable"
