"""Listing, hand entry, bulk entry, and corrections over HTTP."""
from __future__ import annotations

import pytest


def add(client, **overrides):
    body = {"date": "2026-07-15", "description": "Rema Lorenveien, Oslo",
            "amount": -189.90, "account": "Bankkonto"}
    body.update(overrides)
    return client.post("/api/transactions", json=body)


# -- hand entry -------------------------------------------------------------

def test_a_hand_entered_row_is_categorised_by_the_same_rules_as_an_import(
        client):
    """Typing a merchant the importer knows must get that merchant's
    category, not a blank one -- manual entry runs the same `categorise`."""
    response = add(client)
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "Groceries"
    assert body["origin"] == "manual"
    assert body["needs_review"] is False


def test_an_unrecognised_merchant_is_flagged_for_review(client):
    body = add(client, description="Bjornstad Handel A/S").json()
    assert body["category"] == "Uncategorised"
    assert body["needs_review"] is True


def test_an_explicit_category_overrides_the_guess(client):
    body = add(client, category="Gifts").json()
    assert body["category"] == "Gifts"
    assert body["needs_review"] is False


def test_an_unknown_category_is_rejected(client):
    assert add(client, category="No Such Category").status_code == 422


def test_an_unknown_account_is_rejected(client):
    assert add(client, account="Nowhere").status_code == 422


def test_a_zero_amount_is_rejected(client):
    """Always a mistake, and it would sit in the ledger contributing nothing
    but confusion."""
    assert add(client, amount=0).status_code == 422


def test_a_manual_row_carries_no_fingerprint(client, con):
    """It has no source document to be identified against. 003's unique index
    covers `fingerprint <> ''`, so a manual row that happened to match an
    imported one would otherwise collide with it."""
    new_id = add(client).json()["id"]
    row = con.execute(
        "SELECT fingerprint, origin FROM transactions WHERE id = ?",
        (new_id,)).fetchone()
    assert row["fingerprint"] == ""
    assert row["origin"] == "manual"


def test_manual_rows_do_not_trip_the_legacy_guard(client, con):
    """Manual entry is the whole reason ingest became additive; those rows
    carry no fingerprint by design and must not block a later import."""
    from server.lib import store
    for n in range(3):
        add(client, description=f"Manual {n}")
    store.require_fingerprinted_imports(con)          # must not raise


def test_manual_rows_share_one_import_batch(client, con):
    """batch_id is NOT NULL, so a manual row still needs a batch -- but a
    batch per entry would bury real imports under one-row batches."""
    for n in range(3):
        add(client, description=f"Manual {n}")
    assert con.execute(
        "SELECT COUNT(*) FROM import_batches").fetchone()[0] == 1


# -- listing ----------------------------------------------------------------

def test_transactions_come_back_newest_first(client):
    for day in ("2026-07-01", "2026-07-20", "2026-07-10"):
        add(client, date=day, description=f"Rema {day}")
    dates = [row["date"] for row in client.get("/api/transactions").json()]
    assert dates == ["2026-07-20", "2026-07-10", "2026-07-01"]


def test_the_date_range_filters_both_ends(client):
    for day in ("2026-07-01", "2026-07-10", "2026-07-20"):
        add(client, date=day, description=f"Rema {day}")
    rows = client.get(
        "/api/transactions?from=2026-07-05&to=2026-07-15").json()
    assert [r["date"] for r in rows] == ["2026-07-10"]


def test_the_review_queue_is_the_same_list_with_a_filter(client):
    add(client, description="Rema Lorenveien, Oslo")       # known merchant
    add(client, description="Bjornstad Handel A/S")        # unknown
    flagged = client.get("/api/transactions?needs_review=true").json()
    assert [r["description"] for r in flagged] == ["Bjornstad Handel A/S"]
    assert len(client.get("/api/transactions?needs_review=false").json()) == 1


def test_paging_does_not_repeat_or_drop_rows_sharing_a_date(client):
    """Date alone is not a total order -- every row from one statement day
    shares it -- so paging over it would repeat and drop rows between calls.
    """
    for n in range(10):
        add(client, date="2026-07-15", description=f"Rema {n}")

    first = client.get("/api/transactions?limit=4&offset=0").json()
    second = client.get("/api/transactions?limit=4&offset=4").json()
    third = client.get("/api/transactions?limit=4&offset=8").json()

    ids = [r["id"] for r in first + second + third]
    assert len(ids) == 10
    assert len(set(ids)) == 10


def test_the_page_size_is_capped(client):
    assert client.get("/api/transactions?limit=100000").status_code == 422


def test_a_single_transaction_can_be_fetched(client):
    new_id = add(client).json()["id"]
    assert client.get(f"/api/transactions/{new_id}").json()["id"] == new_id


# -- bulk -------------------------------------------------------------------

def test_bulk_insert_adds_every_row(client):
    rows = [{"date": "2026-07-15", "description": f"Rema {n}",
             "amount": -10.0 - n, "account": "Bankkonto"} for n in range(5)]
    response = client.post("/api/transactions/bulk", json={"rows": rows})
    assert response.status_code == 201
    body = response.json()
    assert body["inserted"] == 5
    assert len(body["ids"]) == 5
    assert len(client.get("/api/transactions").json()) == 5


def test_bulk_insert_is_all_or_nothing(client):
    """A partial bulk insert is the worst outcome: the caller cannot tell
    which rows landed without diffing, and re-sending would double them."""
    rows = [
        {"date": "2026-07-15", "description": "Good", "amount": -10.0,
         "account": "Bankkonto"},
        {"date": "2026-07-15", "description": "Bad", "amount": -10.0,
         "account": "Nowhere"},
    ]
    assert client.post("/api/transactions/bulk",
                       json={"rows": rows}).status_code == 422
    assert client.get("/api/transactions").json() == []


def test_bulk_rejects_an_empty_batch(client):
    assert client.post("/api/transactions/bulk",
                       json={"rows": []}).status_code == 422


def test_bulk_is_capped(client):
    rows = [{"date": "2026-07-15", "description": "x", "amount": -1.0,
             "account": "Bankkonto"}] * 1001
    assert client.post("/api/transactions/bulk",
                       json={"rows": rows}).status_code == 422


@pytest.mark.parametrize("bad", [
    {"date": "not-a-date"},
    {"amount": "lots"},
    {"description": ""},
])
def test_malformed_rows_are_422_not_500(client, bad):
    assert add(client, **bad).status_code == 422


# -- corrections ------------------------------------------------------------

def test_recategorising_clears_the_review_flag(client):
    """needs_review means "this category is a guess"; a person choosing one
    has answered that."""
    new_id = add(client, description="Bjornstad Handel A/S").json()["id"]
    body = client.patch(f"/api/transactions/{new_id}",
                        json={"category": "Groceries"}).json()
    assert body["category"] == "Groceries"
    assert body["needs_review"] is False


def test_recategorising_to_a_transfer_updates_is_transfer(client):
    """is_transfer is derived from the category kind and would otherwise keep
    the old category's answer -- and that flag is what keeps transfers out of
    the spending figures."""
    new_id = add(client, description="Bjornstad Handel A/S").json()["id"]
    body = client.patch(f"/api/transactions/{new_id}",
                        json={"category": "Internal transfer"}).json()
    assert body["is_transfer"] is True
    assert body["category_kind"] == "transfer"


def test_teaching_makes_the_correction_apply_to_future_rows(client):
    """The whole point of merchant_rules: a correction made once keeps
    applying, so next month's charge lands correctly without a code change."""
    new_id = add(client, description="Bjornstad Handel A/S").json()["id"]
    client.patch(f"/api/transactions/{new_id}",
                 json={"category": "Groceries", "teach": True,
                       "teach_pattern": "bjornstad"})

    later = add(client, date="2026-08-15",
                description="Bjornstad Handel A/S").json()
    assert later["category"] == "Groceries"
    assert later["needs_review"] is False


def test_teaching_without_a_category_is_rejected(client):
    new_id = add(client).json()["id"]
    assert client.patch(f"/api/transactions/{new_id}",
                        json={"note": "hi", "teach": True}).status_code == 422


def test_a_correction_without_teaching_does_not_affect_later_rows(client):
    """A memo says what was bought, not why; some corrections are about one
    payment only. So teaching is opt-in rather than automatic."""
    new_id = add(client, description="Bjornstad Handel A/S").json()["id"]
    client.patch(f"/api/transactions/{new_id}", json={"category": "Gifts"})

    later = add(client, date="2026-08-15",
                description="Bjornstad Handel A/S").json()
    assert later["category"] == "Uncategorised"


def test_a_budget_override_keeps_a_row_out_of_the_envelope(client):
    new_id = add(client).json()["id"]
    body = client.patch(f"/api/transactions/{new_id}",
                        json={"budget_override": "reimbursable"}).json()
    assert body["treatment"] == "reimbursable"


def test_an_override_can_be_cleared_back_to_the_category_default(client):
    new_id = add(client).json()["id"]
    client.patch(f"/api/transactions/{new_id}",
                 json={"budget_override": "exceptional"})
    body = client.patch(f"/api/transactions/{new_id}",
                        json={"clear_override": True}).json()
    assert body["treatment"] == "variable"       # Groceries' default


def test_an_invalid_override_is_rejected_before_it_reaches_the_database(
        client):
    """The schema's CHECK constraint would catch it, but as an opaque
    IntegrityError rather than a message naming the field."""
    new_id = add(client).json()["id"]
    assert client.patch(f"/api/transactions/{new_id}",
                        json={"budget_override": "nonsense"}).status_code == 422


def test_an_empty_patch_is_rejected(client):
    new_id = add(client).json()["id"]
    assert client.patch(f"/api/transactions/{new_id}", json={}).status_code == 422


def test_override_and_clear_together_are_rejected(client):
    new_id = add(client).json()["id"]
    assert client.patch(
        f"/api/transactions/{new_id}",
        json={"budget_override": "fixed", "clear_override": True}
    ).status_code == 422


def test_patching_an_unknown_transaction_is_404(client):
    assert client.patch("/api/transactions/999999",
                        json={"category": "Gifts"}).status_code == 404
