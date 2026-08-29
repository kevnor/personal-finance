"""The budget endpoint and its configuration."""
from __future__ import annotations

from server.lib.ingest import dnb_xlsx
from server.test.fixtures import statements
from server.test.test_api_imports import upload


def load_statements(client):
    client.post("/api/imports", files=upload(statements.BANK, dnb_xlsx.BANK),
                data={"account": "Bankkonto"})
    client.post("/api/imports", files=upload(statements.CARD_A),
                data={"account": "Kredittkort"})


def test_budget_returns_the_figures_and_the_pools_behind_them(client):
    load_statements(client)
    body = client.get("/api/budget?date=2026-07-15").json()

    assert body["day"] == "2026-07-15"
    assert body["week_start"] == "2026-07-13"
    assert body["week_end"] == "2026-07-19"
    assert set(body["pools"]) == {"2026-07"}

    pool = body["pools"]["2026-07"]
    assert pool["amount"] == round(
        pool["income"] - pool["fixed"] - pool["committed"] - pool["savings"], 2)


def test_a_week_straddling_a_month_gets_both_pools(client):
    """The client needs them to explain the number: a day on either side of
    the boundary is genuinely worth a different amount."""
    load_statements(client)
    body = client.get("/api/budget?date=2026-06-30").json()
    assert set(body["pools"]) == {"2026-06", "2026-07"}


def test_budget_defaults_to_today_in_the_configured_timezone(client):
    """Not `date.today()`: a container running UTC would roll the day over at
    01:00 or 02:00 local, putting a late-evening purchase in tomorrow."""
    import datetime
    from zoneinfo import ZoneInfo

    expected = datetime.datetime.now(ZoneInfo("Europe/Oslo")).date()
    assert client.get("/api/budget").json()["day"] == expected.isoformat()


def test_budget_writes_nothing(client, settings):
    load_statements(client)
    before = settings.db_path.stat().st_mtime_ns
    assert client.get("/api/budget?date=2026-07-15").status_code == 200
    assert settings.db_path.stat().st_mtime_ns == before


def test_spending_moves_the_remaining_figure(client):
    """The end-to-end proof that the endpoint reads real rows: adding an
    expense inside the week must reduce what is left of it."""
    before = client.get("/api/budget?date=2026-07-15").json()["figures"]
    client.post("/api/transactions", json={
        "date": "2026-07-15", "description": "Rema Lorenveien, Oslo",
        "amount": -250.0, "account": "Bankkonto"})
    after = client.get("/api/budget?date=2026-07-15").json()["figures"]

    assert after["week_spent"] == round(before["week_spent"] + 250.0, 2)
    assert after["week_remaining"] == round(before["week_remaining"] - 250.0, 2)


def test_a_transfer_does_not_count_as_spending(client):
    """Card settlements must not reduce the envelope: the card's own purchase
    lines already carry that spending."""
    before = client.get("/api/budget?date=2026-07-15").json()["figures"]
    client.post("/api/transactions", json={
        "date": "2026-07-15", "description": "Overføring Mellom Egne Konti",
        "amount": -5000.0, "account": "Bankkonto"})
    after = client.get("/api/budget?date=2026-07-15").json()["figures"]
    assert after["week_spent"] == before["week_spent"]


def test_a_reimbursable_override_takes_a_row_out_of_the_envelope(client):
    """A plain exclusion cannot tell you the money never came back, so the
    row is marked rather than removed -- and must stop being counted.

    Uses a `variable` category deliberately: an `exceptional` one is already
    outside the envelope by its category default, which would make this pass
    without the override doing anything.
    """
    new_id = client.post("/api/transactions", json={
        "date": "2026-07-15", "description": "Rema Lorenveien, Oslo",
        "amount": -600.0, "account": "Bankkonto"}).json()["id"]

    with_it = client.get("/api/budget?date=2026-07-15").json()["figures"]
    assert with_it["week_spent"] == 600.0

    client.patch(f"/api/transactions/{new_id}",
                 json={"budget_override": "reimbursable"})
    without = client.get("/api/budget?date=2026-07-15").json()["figures"]
    assert without["week_spent"] == 0.0


def test_an_exceptional_category_never_touches_the_envelope(client):
    """The spec's third bucket: "a 13 990 purchase against a 4 165 envelope
    makes a strict budget meaningless". Home & furniture is `exceptional`, so
    the phone is out of the weekly figure by category, before any override."""
    client.post("/api/transactions", json={
        "date": "2026-07-15", "description": "Mol*Hoome AS",
        "amount": -13990.0, "account": "Bankkonto",
        "category": "Home & furniture"})
    figures = client.get("/api/budget?date=2026-07-15").json()["figures"]
    assert figures["week_spent"] == 0.0


# -- configuration ----------------------------------------------------------

def test_the_cold_start_config_is_seeded_on_first_run(client):
    """The spec is explicit that without these figures "the app is broken on
    first run" -- load_config raises on an unseeded database."""
    body = client.get("/api/budget/config").json()
    assert body["income_mode"] == "manual"
    assert body["savings_target"] == 5000.0
    assert body["week_starts_on"] == 1


def test_changing_the_savings_target_changes_the_pool(client):
    before = client.get("/api/budget?date=2026-07-15").json()
    assert client.put("/api/budget/config",
                      json={"savings_target": 7000.0,
                            "effective_from": "2026-01-01"}).status_code == 200
    after = client.get("/api/budget?date=2026-07-15").json()

    assert after["pools"]["2026-07"]["savings"] == 7000.0
    assert (before["pools"]["2026-07"]["amount"]
            - after["pools"]["2026-07"]["amount"]) == 2000.0


def test_a_change_leaves_earlier_versions_in_force_for_earlier_dates(client):
    """Versioning by effective_from exists so that changing the savings
    target does not retroactively rewrite what last month was allowed."""
    client.put("/api/budget/config",
               json={"savings_target": 9000.0, "effective_from": "2026-08-01"})

    assert client.get(
        "/api/budget/config?date=2026-07-15").json()["savings_target"] == 5000.0
    assert client.get(
        "/api/budget/config?date=2026-08-15").json()["savings_target"] == 9000.0


def test_fields_left_out_keep_their_current_value(client):
    """Changing only the savings target must not require restating income."""
    before = client.get("/api/budget/config").json()
    client.put("/api/budget/config", json={"savings_target": 1234.0})
    after = client.get("/api/budget/config").json()

    assert after["savings_target"] == 1234.0
    assert after["manual_income"] == before["manual_income"]
    assert after["income_mode"] == before["income_mode"]


def test_switching_income_to_derived_is_accepted(client):
    body = client.put("/api/budget/config",
                      json={"income_mode": "derived"}).json()
    assert body["income_mode"] == "derived"
    # fixed_mode has its own switch: the two hit the complete-month threshold
    # at different times, and one shared flag would force both to wait.
    assert body["fixed_mode"] == "manual"


def test_an_invalid_mode_is_rejected(client):
    assert client.put("/api/budget/config",
                      json={"income_mode": "guesswork"}).status_code == 422


def test_a_negative_savings_target_is_rejected(client):
    assert client.put("/api/budget/config",
                      json={"savings_target": -100}).status_code == 422


def test_an_out_of_range_week_start_is_rejected(client):
    assert client.put("/api/budget/config",
                      json={"week_starts_on": 9}).status_code == 422


def test_an_empty_config_change_is_rejected(client):
    assert client.put("/api/budget/config", json={}).status_code == 422


def test_the_week_start_moves_the_week_bounds(client):
    client.put("/api/budget/config",
               json={"week_starts_on": 7, "effective_from": "2026-01-01"})
    body = client.get("/api/budget?date=2026-07-15").json()
    assert body["week_start"] == "2026-07-12"        # the preceding Sunday
