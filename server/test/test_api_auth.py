"""The passcode flow, sessions, and the rate limit."""
from __future__ import annotations

import json
import time

import pytest

from server import security
from server.test.conftest import PASSCODE


def test_status_before_anything_is_configured(anon):
    """The client needs this to choose between the first-run setup screen,
    the login screen, and the app -- so it must answer without a session."""
    assert anon.get("/api/auth/status").json() == {
        "configured": False, "authenticated": False,
        "entra_available": False, "source": None}


def test_setting_the_passcode_signs_you_in(anon):
    response = anon.post("/api/auth/passcode", json={"passcode": PASSCODE})
    assert response.status_code == 201
    assert response.json() == {
            "configured": True, "authenticated": True,
            "entra_available": False, "source": "passcode"}
    assert anon.get("/api/auth/status").json()["authenticated"] is True


def test_the_passcode_endpoint_closes_once_a_passcode_exists(client):
    """First-run setup is unauthenticated by necessity -- there is nothing to
    authenticate against yet -- so it must be available exactly once."""
    response = client.post("/api/auth/passcode", json={"passcode": "another1"})
    assert response.status_code == 409


def test_a_short_passcode_is_refused(anon):
    response = anon.post("/api/auth/passcode", json={"passcode": "abc"})
    assert response.status_code == 422
    assert anon.get("/api/auth/status").json()["configured"] is False


def test_the_passcode_is_hashed_not_stored(client, settings):
    """The file on the volume must never contain the passcode itself."""
    stored = json.loads(settings.passcode_file.read_text(encoding="utf-8"))
    assert PASSCODE not in json.dumps(stored)
    assert stored["passcode_hash"].startswith("$argon2")
    assert stored["session_secret"]


def test_the_credentials_file_is_not_world_readable(client, settings):
    assert (settings.passcode_file.stat().st_mode & 0o077) == 0


def test_login_with_the_right_passcode_sets_a_session_cookie(anon):
    anon.post("/api/auth/passcode", json={"passcode": PASSCODE})
    anon.cookies.clear()
    assert anon.get("/api/auth/status").json()["authenticated"] is False

    response = anon.post("/api/auth/login", json={"passcode": PASSCODE})
    assert response.status_code == 200
    assert security.SESSION_COOKIE in response.cookies
    assert anon.get("/api/auth/status").json()["authenticated"] is True


def test_login_with_the_wrong_passcode_is_rejected(client):
    client.cookies.clear()
    response = client.post("/api/auth/login", json={"passcode": "wrong-one"})
    assert response.status_code == 401
    assert client.get("/api/budget").status_code == 401


def test_the_session_cookie_is_httponly_and_samesite_lax(anon):
    """httpOnly keeps it out of reach of any script on the page; SameSite=Lax
    is what stops another site's form POSTing to this one with it attached."""
    response = anon.post("/api/auth/passcode", json={"passcode": PASSCODE})
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/" in header


def test_the_cookie_is_not_marked_secure_over_plain_http(anon):
    """A `Secure` cookie set over http:// is dropped by the browser, so
    hardcoding it would break local development silently -- login would
    appear to succeed and every later request would be a 401."""
    response = anon.post("/api/auth/passcode", json={"passcode": PASSCODE})
    assert "secure" not in response.headers["set-cookie"].lower()


def test_the_cookie_is_marked_secure_when_serving_https(tmp_path):
    from fastapi.testclient import TestClient
    from server.app import create_app
    from server.settings import Settings

    app = create_app(Settings.from_env({
        "PF_DATA_DIR": str(tmp_path / "data"),
        "PF_STATIC_DIR": str(tmp_path / "none"),
        "PF_HTTPS_ONLY": "true"}))
    with TestClient(app) as client:
        response = client.post("/api/auth/passcode", json={"passcode": PASSCODE})
        assert "secure" in response.headers["set-cookie"].lower()


def test_logout_clears_the_session(client):
    assert client.get("/api/budget").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/status").json()["authenticated"] is False
    assert client.get("/api/budget").status_code == 401


def test_a_tampered_cookie_is_rejected(client):
    """The token is signed, so editing the expiry inside it does not extend
    it -- the signature no longer matches."""
    client.cookies.set(security.SESSION_COOKIE, "OTk5OTk5OTk5OQ.forged")
    assert client.get("/api/budget").status_code == 401


def test_a_session_signed_with_another_secret_is_rejected(client):
    other = security.Credentials(passcode_hash="x", session_secret="different")
    client.cookies.set(security.SESSION_COOKIE, security.issue_session(other))
    assert client.get("/api/budget").status_code == 401


def test_changing_the_passcode_requires_the_current_one(client):
    assert client.put("/api/auth/passcode", json={
        "current_passcode": "not-it", "new_passcode": "new-passcode"
    }).status_code == 403

    assert client.put("/api/auth/passcode", json={
        "current_passcode": PASSCODE, "new_passcode": "new-passcode"
    }).status_code == 200

    client.cookies.clear()
    assert client.post("/api/auth/login",
                       json={"passcode": PASSCODE}).status_code == 401
    assert client.post("/api/auth/login",
                       json={"passcode": "new-passcode"}).status_code == 200


def test_changing_the_passcode_keeps_existing_sessions_alive(client):
    """Changing a passcode because it was weak should not sign the user out
    of every device. Revoking sessions is a different action -- delete the
    credentials file, which rotates the signing secret."""
    client.put("/api/auth/passcode", json={
        "current_passcode": PASSCODE, "new_passcode": "new-passcode"})
    assert client.get("/api/budget").status_code == 200


# -- the rate limit ---------------------------------------------------------

def test_repeated_wrong_guesses_are_rate_limited(client):
    """A passcode is short by nature, so unlimited guessing is the one attack
    this design is genuinely exposed to."""
    client.cookies.clear()
    for _ in range(security.RATE_LIMIT_ATTEMPTS):
        assert client.post("/api/auth/login",
                           json={"passcode": "wrong"}).status_code == 401

    response = client.post("/api/auth/login", json={"passcode": "wrong"})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0

    # The correct passcode is refused too while the window is open: the limit
    # is checked before the hash is verified, so a locked-out caller does not
    # even get the timing signal.
    assert client.post("/api/auth/login",
                       json={"passcode": PASSCODE}).status_code == 429


def test_a_successful_login_clears_the_attempt_count(client):
    client.cookies.clear()
    for _ in range(security.RATE_LIMIT_ATTEMPTS - 1):
        client.post("/api/auth/login", json={"passcode": "wrong"})

    assert client.post("/api/auth/login",
                       json={"passcode": PASSCODE}).status_code == 200
    # The budget is spent again, not still exhausted from before.
    for _ in range(security.RATE_LIMIT_ATTEMPTS):
        assert client.post("/api/auth/login",
                           json={"passcode": "wrong"}).status_code == 401


# -- the rate limit's key, behind a reverse proxy ---------------------------
#
# `_client_key` is what the limit above is actually keyed on. Once the app
# sits behind a reverse proxy on the same machine (cloudflared, tailscale
# serve), every request arrives over loopback -- so this is the function that
# decides whether "rate limited per client address" still means anything, or
# whether it has quietly become "rate limited for everyone at once".

from starlette.requests import Request  # noqa: E402

from server.routes.auth import _client_key  # noqa: E402


def _request(peer: str | None, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "client": (peer, 0) if peer is not None else None,
        "headers": [(k.lower().encode(), v.encode())
                    for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_a_direct_connection_is_keyed_on_its_own_address():
    """No proxy in front at all -- local development, or an instance reached
    directly on the LAN. Nothing to trust a header for."""
    assert _client_key(_request("192.168.1.50")) == "192.168.1.50"


def test_a_forwarded_header_is_trusted_only_from_loopback():
    """The header Cloudflare Tunnel sets, honoured only when it could only
    have arrived via a proxy already running on this machine."""
    trusted = _request("127.0.0.1", {"cf-connecting-ip": "203.0.113.9"})
    assert _client_key(trusted) == "203.0.113.9"

    # The same header, claimed by a direct connection instead of loopback.
    # Trusting it here is exactly the spoof this function exists to refuse:
    # anyone on the LAN could claim to be any address they like and both
    # dodge the limit and frame another client for it.
    spoofed = _request("192.168.1.77", {"cf-connecting-ip": "203.0.113.9"})
    assert _client_key(spoofed) == "192.168.1.77"


def test_a_forwarded_for_chain_is_read_from_the_right():
    """`X-Forwarded-For` accumulates as `client, proxy1, ...`, each hop
    appending what it heard from. With one trusted proxy in front, only its
    entry -- the rightmost -- is vouched for; everything left of it was
    supplied by the caller. Taking the leftmost is the standard way this is
    got wrong, and it hands the caller a free choice of key."""
    forged = _request("127.0.0.1",
                      {"x-forwarded-for": "10.9.9.9, 203.0.113.9"})
    assert _client_key(forged) == "203.0.113.9"


def test_a_single_entry_chain_is_the_client():
    single = _request("127.0.0.1", {"x-forwarded-for": "203.0.113.9"})
    assert _client_key(single) == "203.0.113.9"


def test_a_forwarded_for_chain_is_ignored_from_a_direct_connection():
    """Same reasoning as the Cloudflare header: off loopback it is just a
    caller-supplied string."""
    spoofed = _request("192.168.1.77", {"x-forwarded-for": "203.0.113.9"})
    assert _client_key(spoofed) == "192.168.1.77"


def test_a_malformed_chain_does_not_collapse_everyone_into_one_bucket():
    """A trailing comma would otherwise split to an empty final element, and
    every caller behind the proxy would key on "" together."""
    assert _client_key(
        _request("127.0.0.1", {"x-forwarded-for": "203.0.113.9, "})
    ) == "203.0.113.9"
    assert _client_key(
        _request("127.0.0.1", {"x-forwarded-for": " , "})) == "127.0.0.1"


def test_ipv6_loopback_is_recognised_too():
    trusted = _request("::1", {"cf-connecting-ip": "203.0.113.9"})
    assert _client_key(trusted) == "203.0.113.9"


def test_a_loopback_connection_with_no_header_falls_back_to_loopback():
    """The tailscale serve path: proxied, on loopback, but no client-IP header
    to read. Everyone behind it shares one bucket -- accepted, because only
    devices already inside the tailnet can reach that proxy at all."""
    assert _client_key(_request("127.0.0.1")) == "127.0.0.1"


def test_no_client_at_all_does_not_crash():
    """ASGI permits a request with no client info at all (e.g. a Unix
    socket). The rate limiter still needs a key, not an exception."""
    assert _client_key(_request(None)) == "unknown"


def test_the_window_expires():
    limiter = security.RateLimiter(attempts=2, window_seconds=60)
    now = time.time()
    limiter.record("a", now)
    limiter.record("a", now)
    assert limiter.check("a", now) is False
    assert limiter.check("a", now + 61) is True


def test_one_client_being_locked_out_does_not_lock_out_another():
    limiter = security.RateLimiter(attempts=1, window_seconds=60)
    limiter.record("10.0.0.1")
    assert limiter.check("10.0.0.1") is False
    assert limiter.check("10.0.0.2") is True


# -- session tokens ---------------------------------------------------------

def test_a_session_token_expires():
    credentials = security.Credentials("hash", "secret")
    now = time.time()
    token = security.issue_session(credentials, now=now)
    assert security.session_is_valid(credentials, token, now=now)
    assert not security.session_is_valid(
        credentials, token, now=now + security.SESSION_TTL_SECONDS + 1)


@pytest.mark.parametrize("token", [
    None, "", "no-dot", "notbase64.notasignature", ".", "a.b.c"])
def test_malformed_tokens_are_rejected_rather_than_raising(token):
    credentials = security.Credentials("hash", "secret")
    assert security.session_is_valid(credentials, token) is False


def test_login_before_a_passcode_exists_is_a_conflict(anon):
    response = anon.post("/api/auth/login", json={"passcode": "anything"})
    assert response.status_code == 409


def test_changing_the_passcode_requires_a_session(anon):
    """Without this the endpoint verifies the current passcode while sitting
    on the unauthenticated router -- a brute-force oracle that bypasses the
    rate limit on /login entirely."""
    anon.post("/api/auth/passcode", json={"passcode": PASSCODE})
    anon.cookies.clear()
    response = anon.put("/api/auth/passcode", json={
        "current_passcode": PASSCODE, "new_passcode": "brand-new-one"})
    assert response.status_code == 401
    # ... and the passcode really was not changed.
    assert anon.post("/api/auth/login",
                     json={"passcode": PASSCODE}).status_code == 200


def test_guessing_the_current_passcode_is_rate_limited_too(client):
    """The change endpoint shares login's counter, so the two cannot be
    played off against each other."""
    for _ in range(security.RATE_LIMIT_ATTEMPTS):
        assert client.put("/api/auth/passcode", json={
            "current_passcode": "wrong", "new_passcode": "whatever1"
        }).status_code == 403

    assert client.put("/api/auth/passcode", json={
        "current_passcode": "wrong", "new_passcode": "whatever1"
    }).status_code == 429
    # The shared counter means login is locked out as well.
    client.cookies.clear()
    assert client.post("/api/auth/login",
                       json={"passcode": PASSCODE}).status_code == 429
