"""Categories, reimbursements, and serving the built client."""
from __future__ import annotations

import pytest


# -- categories -------------------------------------------------------------

def test_categories_are_listed_with_their_treatments(client):
    rows = client.get("/api/categories").json()
    by_name = {row["name"]: row for row in rows}

    assert by_name["Groceries"]["budget_treatment"] == "variable"
    assert by_name["Subscriptions"]["budget_treatment"] == "fixed"
    assert by_name["Home & furniture"]["budget_treatment"] == "exceptional"
    # cash_treatment is read only for transfer categories.
    assert by_name["Mortgage - principal"]["cash_treatment"] == "committed"
    assert by_name["Credit card payment"]["cash_treatment"] == "settlement"
    assert by_name["Internal transfer"]["cash_treatment"] == "savings"


def test_a_categorys_treatment_can_be_changed(client):
    """The spec calls this out for Clothing & shoes: `variable` in v1 but
    plausibly `exceptional`, and moving it is a settings change."""
    response = client.patch("/api/categories/Clothing & shoes",
                            json={"budget_treatment": "exceptional"})
    assert response.status_code == 200
    assert response.json()["budget_treatment"] == "exceptional"


def test_changing_a_treatment_changes_what_the_envelope_counts(client):
    """The point of the setting: an `exceptional` category stops competing
    with groceries for the weekly figure."""
    client.post("/api/transactions", json={
        "date": "2026-07-15", "description": "Euro Sko Storo",
        "amount": -1200.0, "account": "Bankkonto"})
    before = client.get("/api/budget?date=2026-07-15").json()["figures"]
    assert before["week_spent"] == 1200.0

    client.patch("/api/categories/Clothing & shoes",
                 json={"budget_treatment": "exceptional"})
    after = client.get("/api/budget?date=2026-07-15").json()["figures"]
    assert after["week_spent"] == 0.0


def test_an_invalid_treatment_is_rejected(client):
    """The schema's CHECK constraint would catch it, but as an opaque
    IntegrityError rather than a message naming the field."""
    assert client.patch("/api/categories/Groceries",
                        json={"budget_treatment": "sometimes"}).status_code == 422


def test_an_unknown_category_is_404(client):
    assert client.patch("/api/categories/Nope",
                        json={"budget_treatment": "fixed"}).status_code == 404


# -- reimbursements ---------------------------------------------------------

@pytest.fixture
def phone(client):
    """The spec's worked example: an employer-paid phone."""
    return client.post("/api/transactions", json={
        "date": "2026-07-30", "description": "Mol*Hoome AS",
        "amount": -13990.0, "account": "Bankkonto",
        "category": "Home & furniture"}).json()["id"]


def test_recording_a_debt_makes_it_queryable(client, phone):
    """This is what makes "13 990 owed by the employer" a real figure rather
    than a silent exclusion."""
    response = client.post("/api/reimbursements", json={
        "transaction_id": phone, "expected_from": "Nordvest Teknikk AS",
        "note": "employer-paid phone"})
    assert response.status_code == 201

    outstanding = client.get("/api/reimbursements").json()
    assert len(outstanding) == 1
    assert outstanding[0]["expected_from"] == "Nordvest Teknikk AS"
    assert outstanding[0]["expected_amount"] == 13990.0
    assert outstanding[0]["settled_at"] is None


def test_recording_a_debt_marks_the_row_reimbursable(client, phone):
    client.post("/api/reimbursements", json={
        "transaction_id": phone, "expected_from": "Nordvest Teknikk AS"})
    assert client.get(
        f"/api/transactions/{phone}").json()["treatment"] == "reimbursable"


def test_recording_a_debt_keeps_the_category_for_reporting(client, phone):
    """Marking a debt says nothing about whether the category is right -- that
    is what makes it a reimbursement rather than a recategorisation."""
    client.post("/api/reimbursements", json={
        "transaction_id": phone, "expected_from": "Nordvest Teknikk AS"})
    assert client.get(
        f"/api/transactions/{phone}").json()["category"] == "Home & furniture"


def test_recording_the_same_debt_twice_does_not_double_it(client, phone):
    """Backed by a UNIQUE index, so a retry or double-submit can never double
    the amount owed."""
    for _ in range(2):
        client.post("/api/reimbursements", json={
            "transaction_id": phone, "expected_from": "Nordvest Teknikk AS"})
    outstanding = client.get("/api/reimbursements").json()
    assert len(outstanding) == 1
    assert outstanding[0]["expected_amount"] == 13990.0


def test_settling_a_debt_removes_it_from_outstanding(client, phone):
    debt_id = client.post("/api/reimbursements", json={
        "transaction_id": phone, "expected_from": "Nordvest Teknikk AS"}).json()["id"]

    response = client.post(f"/api/reimbursements/{debt_id}/settle", json={})
    assert response.status_code == 200
    assert response.json()["settled_at"] is not None
    assert client.get("/api/reimbursements").json() == []


def test_a_settlement_can_name_the_payment_that_covered_it(client, phone):
    debt_id = client.post("/api/reimbursements", json={
        "transaction_id": phone, "expected_from": "Nordvest Teknikk AS"}).json()["id"]
    repayment = client.post("/api/transactions", json={
        "date": "2026-08-15", "description": "Giro Nordvest Teknikk AS",
        "amount": 13990.0, "account": "Bankkonto"}).json()["id"]

    body = client.post(f"/api/reimbursements/{debt_id}/settle", json={
        "settled_by_transaction_id": repayment,
        "settled_at": "2026-08-15"}).json()
    assert body["settled_at"] == "2026-08-15"


def test_a_debt_against_an_unknown_transaction_is_404(client):
    assert client.post("/api/reimbursements", json={
        "transaction_id": 999999, "expected_from": "Someone"
    }).status_code == 404


def test_settling_an_unknown_debt_is_404(client):
    assert client.post("/api/reimbursements/999/settle",
                       json={}).status_code == 404


# -- serving the client -----------------------------------------------------

def build_client_dir(tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html>app", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    return static


@pytest.fixture
def served(tmp_path):
    from fastapi.testclient import TestClient
    from server.app import create_app
    from server.settings import Settings

    static = build_client_dir(tmp_path)
    app = create_app(Settings.from_env({
        "PF_DATA_DIR": str(tmp_path / "data"),
        "PF_STATIC_DIR": str(static)}))
    with TestClient(app) as client:
        yield client


def test_the_built_client_is_served_at_the_root(served):
    response = served.get("/")
    assert response.status_code == 200
    assert "app" in response.text


def test_hashed_assets_are_served(served):
    assert served.get("/assets/app.js").status_code == 200


def test_an_unknown_path_falls_back_to_the_app_shell(served):
    """The client routes in the browser, so reloading on any screen but Home
    would 404 without this."""
    response = served.get("/history")
    assert response.status_code == 200
    assert "app" in response.text


def test_the_api_is_not_shadowed_by_the_spa_fallback(served):
    """The catch-all is registered last, but a routing mistake would turn
    every API 401 into an index.html with status 200 -- which the client
    would read as success."""
    assert served.get("/api/budget").status_code == 401


@pytest.mark.parametrize("attack", [
    # Percent-encoded, which is the variant that matters: a literal `..` is
    # collapsed by the client and by the ASGI server before the handler ever
    # sees it, so a test using one passes whether or not the guard exists.
    # This one arrives intact, and does serve the file if the containment
    # check is removed -- verified by deleting it.
    "/%2e%2e/data/passcode.json",
    "/%2e%2e%2fdata%2fpasscode.json",
    "/assets/%2e%2e/%2e%2e/data/passcode.json",
    "/../data/passcode.json",
])
def test_the_static_mount_cannot_escape_its_directory(served, tmp_path, attack):
    """`path` is caller-controlled; without the containment check this serves
    the credentials file sitting next to the database."""
    secret = tmp_path / "data" / "passcode.json"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('{"passcode_hash": "leaked"}', encoding="utf-8")

    response = served.get(attack)
    assert "leaked" not in response.text


def test_a_missing_client_build_is_not_an_error(client):
    """Absent in development, where the client runs on Vite's own dev server,
    and absent in tests. The API must still work."""
    assert client.get("/api/budget").status_code == 200
    assert client.get("/").status_code == 404
