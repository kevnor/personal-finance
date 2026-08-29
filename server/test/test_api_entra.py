"""The Entra sign-in round trip, over HTTP.

`test_entra.py` covers what the app will accept from the directory. This
covers the two endpoints around it: that a passcode-only instance refuses
them cleanly, that the state cookie is actually checked, that every failure
lands the browser on the login screen rather than on a JSON error, and that
the session which comes out is an Entra session with an Entra lifetime.
"""
from __future__ import annotations

import urllib.parse

import pytest
from fastapi.testclient import TestClient

from server import security
from server.app import create_app
from server.settings import Settings
from server.test.conftest import PASSCODE
from server.test.fixtures.entra import ENVIRONMENT, USER_OID, FakeTenant

LOGIN = "/api/auth/entra/login"
CALLBACK = "/api/auth/entra/callback"


@pytest.fixture
def tenant():
    return FakeTenant()


@pytest.fixture
def federated(tmp_path, tenant):
    """An instance with an app registration, and its passcode already set."""
    settings = Settings.from_env({
        "PF_DATA_DIR": str(tmp_path / "data"),
        "PF_STATIC_DIR": str(tmp_path / "no-client-build"),
        **ENVIRONMENT,
    })
    app = create_app(settings)
    app.state.entra = tenant.client()
    with TestClient(app, follow_redirects=False) as client:
        client.post("/api/auth/passcode", json={"passcode": PASSCODE})
        client.post("/api/auth/logout")
        client.cookies.clear()
        yield client


def query_of(response) -> dict:
    return dict(urllib.parse.parse_qsl(
        urllib.parse.urlparse(response.headers["location"]).query))


def sign_in(client, tenant, next: str = "/", **claims):
    """Drive a whole round trip: out to Entra, and back with a code."""
    started = client.get(LOGIN, params={"next": next})
    sent = query_of(started)
    tenant.will_return(nonce=sent["nonce"], **claims)
    return client.get(CALLBACK, params={"code": "the-code",
                                        "state": sent["state"]})


# -- a passcode-only instance -----------------------------------------------

def test_status_says_entra_is_unavailable_when_none_is_configured(anon):
    assert anon.get("/api/auth/status").json()["entra_available"] is False


def test_the_sign_in_routes_refuse_cleanly_with_no_registration(anon):
    """409, not 500: passcode-only is the shipped configuration, so reaching
    these routes on one is a client mistake rather than a server fault."""
    assert anon.get(LOGIN).status_code == 409
    assert anon.get(CALLBACK).status_code == 409


def test_status_says_entra_is_available_when_it_is(federated):
    assert federated.get("/api/auth/status").json()["entra_available"] is True


# -- the redirect out -------------------------------------------------------

def test_login_redirects_to_the_directory_and_remembers_the_attempt(federated):
    response = federated.get(LOGIN)
    assert response.status_code == 303
    assert response.headers["location"].startswith(
        "https://login.microsoftonline.com/")
    assert security.SESSION_COOKIE not in response.cookies
    assert "pf_signin" in response.cookies


def test_the_state_cookie_is_not_readable_by_script(federated):
    """It carries the PKCE verifier. Script-readable, it would stop being a
    proof that this browser started this sign-in."""
    header = federated.get(LOGIN).headers["set-cookie"]
    assert "httponly" in header.lower()


def test_signing_in_before_a_passcode_exists_is_refused(tmp_path, tenant):
    """The credentials file holds the signing secret, and the passcode is the
    break-glass route -- an instance that federated first would have no way
    in when the directory is unreachable."""
    settings = Settings.from_env({
        "PF_DATA_DIR": str(tmp_path / "data"),
        "PF_STATIC_DIR": str(tmp_path / "none"), **ENVIRONMENT})
    app = create_app(settings)
    app.state.entra = tenant.client()
    with TestClient(app, follow_redirects=False) as client:
        assert client.get(LOGIN).status_code == 409


def test_an_unreachable_directory_points_at_the_passcode(tmp_path, tenant):
    """The one moment the break-glass route needs to announce itself."""
    from server import entra
    tenant.discovery_error = entra.EntraError("dns is down")
    settings = Settings.from_env({
        "PF_DATA_DIR": str(tmp_path / "data"),
        "PF_STATIC_DIR": str(tmp_path / "none"), **ENVIRONMENT})
    app = create_app(settings)
    app.state.entra = tenant.client()
    with TestClient(app, follow_redirects=False) as client:
        client.post("/api/auth/passcode", json={"passcode": PASSCODE})
        response = client.get(LOGIN)
    assert response.status_code == 503
    assert "passcode" in response.json()["detail"]


# -- coming back ------------------------------------------------------------

def test_a_completed_sign_in_issues_an_entra_session(federated, tenant):
    response = sign_in(federated, tenant)
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    status = federated.get("/api/auth/status").json()
    assert status["authenticated"] is True
    assert status["source"] == "entra"


def test_the_session_names_the_directory_user(federated, tenant, tmp_path):
    sign_in(federated, tenant)
    store = security.PasscodeStore(tmp_path / "data" / "passcode.json")
    session = security.read_session(
        store.load(), federated.cookies[security.SESSION_COOKIE])
    assert session.subject == USER_OID
    assert session.is_entra


def test_an_entra_session_lasts_an_hour_not_thirty_days(federated, tenant,
                                                        tmp_path):
    """The whole point of federating: removing somebody in the directory has
    to actually lock them out, and a 30-day cookie would leave them a month."""
    import time
    sign_in(federated, tenant)
    store = security.PasscodeStore(tmp_path / "data" / "passcode.json")
    session = security.read_session(
        store.load(), federated.cookies[security.SESSION_COOKIE])
    assert session.expires_at - time.time() <= security.ENTRA_SESSION_TTL_SECONDS
    assert session.expires_at - time.time() > security.ENTRA_SESSION_TTL_SECONDS - 60


def test_the_session_actually_opens_the_api(federated, tenant):
    """The gate is one dependency on the whole /api router, so this is what
    proves an Entra session satisfies the same gate a passcode session does."""
    assert federated.get("/api/categories").status_code == 401
    sign_in(federated, tenant)
    assert federated.get("/api/categories").status_code == 200


def test_where_you_were_going_survives_the_round_trip(federated, tenant):
    response = sign_in(federated, tenant, next="/transactions?month=2026-07")
    assert response.headers["location"] == "/transactions?month=2026-07"


# -- the refusals -----------------------------------------------------------

@pytest.mark.parametrize("hostile", [
    "https://evil.example.com/harvest",
    "//evil.example.com/harvest",
    "http://evil.example.com",
])
def test_an_absolute_next_cannot_redirect_off_this_origin(federated, tenant,
                                                          hostile):
    """An open redirect on a login route is a phishing primitive: the victim
    really does sign in to the real app before being sent on."""
    response = sign_in(federated, tenant, next=hostile)
    assert response.headers["location"] == "/"


def test_a_callback_with_no_sign_in_cookie_goes_to_the_login_screen(federated):
    """A bookmarked callback or a stale tab. Nothing to validate against."""
    response = federated.get(CALLBACK, params={"code": "x", "state": "y"})
    assert response.status_code == 303
    assert response.headers["location"] == "/?signin=expired"


def test_a_mismatched_state_is_refused(federated, tenant):
    """CSRF on a login endpoint looks exactly like this: a genuine response
    from the directory, for a sign-in this browser never started."""
    sent = query_of(federated.get(LOGIN))
    # A token that would otherwise be accepted, so that the state is the only
    # thing left that can refuse this request. Without it the redemption
    # fails for its own reasons and the test passes whether or not the state
    # is ever compared.
    tenant.will_return(nonce=sent["nonce"])
    response = federated.get(CALLBACK, params={"code": "the-code",
                                               "state": "not-the-state"})
    assert response.headers["location"] == "/?signin=denied"
    assert federated.get("/api/auth/status").json()["authenticated"] is False


def test_a_callback_with_no_code_is_refused(federated, tenant):
    sent = query_of(federated.get(LOGIN))
    # Armed for the same reason as above: the absent code must be what
    # refuses this, not an empty token endpoint.
    tenant.will_return(nonce=sent["nonce"])
    response = federated.get(CALLBACK, params={"state": sent["state"]})
    assert response.headers["location"] == "/?signin=denied"
    assert federated.get("/api/auth/status").json()["authenticated"] is False


def test_a_token_from_another_tenant_does_not_sign_anyone_in(federated, tenant):
    """The end-to-end form of the check `test_entra.py` covers in isolation:
    a multitenant registration must not become a way in."""
    from server.test.fixtures.entra import OTHER_TENANT
    response = sign_in(federated, tenant, tid=OTHER_TENANT)
    assert response.headers["location"] == "/?signin=denied"
    assert federated.get("/api/auth/status").json()["authenticated"] is False


def test_a_refused_silent_renewal_asks_for_a_real_sign_in(federated):
    """`login_required` is the expected answer when the directory session has
    lapsed or the user is no longer assigned -- not an error, a prompt."""
    federated.get(LOGIN, params={"silent": "true"})
    response = federated.get(CALLBACK, params={"error": "login_required"})
    assert response.headers["location"] == "/?signin=required"


def test_a_denied_interactive_sign_in_is_reported_as_denied(federated):
    federated.get(LOGIN)
    response = federated.get(CALLBACK, params={"error": "access_denied"})
    assert response.headers["location"] == "/?signin=denied"


def test_a_failed_sign_in_clears_the_state_cookie(federated):
    """Otherwise a stale attempt stays replayable for its full ten minutes."""
    federated.get(LOGIN)
    response = federated.get(CALLBACK, params={"error": "access_denied"})
    assert response.cookies.get("pf_signin") in (None, "")
