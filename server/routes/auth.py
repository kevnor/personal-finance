"""Passcode setup, login and logout.

The only unauthenticated router in the app. Everything else hangs off a
router carrying `require_session`, so a new route is protected unless
somebody deliberately puts it here.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from server import entra, security
from server.deps import (get_entra, get_passcodes, get_rate_limiter,
                         get_settings, require_session)
from server.schemas import AuthStatus, PasscodeChangeIn, PasscodeIn
from server.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

log = logging.getLogger(__name__)

# Carries one sign-in attempt's state, nonce and PKCE verifier across the
# round trip to Entra. SameSite=Lax rather than Strict: the browser arrives
# back here as a top-level navigation *from* login.microsoftonline.com, and
# Strict would withhold the cookie on exactly that request -- so every
# sign-in would fail its state check.
SIGNIN_COOKIE = "pf_signin"

# 422. Spelled as a literal because starlette renamed the constant
# (HTTP_422_UNPROCESSABLE_ENTITY -> ..._CONTENT) and deprecated the old
# name; the number is the part that is actually stable.
UNPROCESSABLE = 422


# Loopback only: the app is meant to be reached exclusively via a reverse
# proxy running on the same machine (`tailscale serve`, `cloudflared`), never
# by a direct connection from the network. That is what makes trusting a
# client-supplied IP header safe -- the only thing able to open a loopback
# connection to this process is a proxy already running on the box.
_LOOPBACK = {"127.0.0.1", "::1"}


def _client_key(request: Request) -> str:
    """The rate limiter's key: the real client, not the proxy in front of it.

    Every request the app receives arrives over loopback once it sits behind
    a reverse proxy -- `request.client.host` is then always "127.0.0.1",
    whoever is actually asking. Rate-limiting on that would do the opposite
    of its job: every attacker on the internet would share one budget with
    the household, and exhausting it would lock the household out along with
    them, not before them.

    A proxy states the real address in a header -- `X-Forwarded-For` for the
    general case (Caddy, nginx), `Cf-Connecting-Ip` where Cloudflare is in
    front. Either is trusted **only** when the direct peer is loopback: on
    this deployment nothing but a proxy running on this same machine can open
    such a connection, so the header cannot be set by anything reachable from
    the network. Trusting it unconditionally would be the opposite of a
    limit, since any caller could then claim any address it liked, both
    dodging its own budget and spending someone else's.

    `X-Forwarded-For` is read right to left. It accumulates as
    `client, proxy1, proxy2`, each hop appending the address it heard from --
    so with exactly one trusted proxy in front, which is this topology, the
    **rightmost** entry is the one that proxy observed and the only one it
    vouches for. Anything to its left was supplied by the caller and is
    exactly as forgeable as the header itself; taking the leftmost entry is
    the standard way this check is got wrong.

    A proxy that sets neither header falls back to keying on loopback -- one
    shared bucket for everyone behind it. Coarse, but safe here: whether a
    given proxy forwards the address is the proxy's business, and on a
    private deployment the set of callers who can reach it is already
    restricted to the household.
    """
    peer = request.client.host if request.client else None
    if peer in _LOOPBACK:
        stated = request.headers.get("cf-connecting-ip")
        if stated:
            return stated.strip()
        chain = request.headers.get("x-forwarded-for")
        if chain:
            # Rightmost: see above. A trailing comma or empty element would
            # otherwise yield "" and collapse every caller into one bucket.
            hops = [hop.strip() for hop in chain.split(",") if hop.strip()]
            if hops:
                return hops[-1]
    return peer or "unknown"


def _set_session_cookie(response: Response, token: str, settings: Settings,
                        max_age: int = security.SESSION_TTL_SECONDS) -> None:
    response.set_cookie(
        security.SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        # Only over HTTPS: a `Secure` cookie set over plain http:// is
        # dropped by the browser, so hardcoding it would break local
        # development silently -- login would appear to succeed and every
        # subsequent request would be a 401.
        secure=settings.https_only,
        path="/")


@router.get("/status", response_model=AuthStatus)
def status_(request: Request,
            passcodes: security.PasscodeStore = Depends(get_passcodes),
            client: entra.Client | None = Depends(get_entra)):
    """Whether a passcode exists and whether this caller is signed in.

    Unauthenticated on purpose: the client needs it to decide between the
    first-run setup screen, the login screen, and the app itself.
    """
    available = client is not None
    if not passcodes.is_configured():
        return AuthStatus(configured=False, authenticated=False,
                          entra_available=available)
    session = security.read_session(
        passcodes.load(), request.cookies.get(security.SESSION_COOKIE))
    return AuthStatus(configured=True,
                      authenticated=session is not None,
                      entra_available=available,
                      source=session.source if session else None)


@router.post("/passcode", response_model=AuthStatus,
             status_code=status.HTTP_201_CREATED)
def set_passcode(body: PasscodeIn, response: Response,
                 passcodes: security.PasscodeStore = Depends(get_passcodes),
                 settings: Settings = Depends(get_settings)):
    """Set the passcode on first run, and sign the caller in.

    Unauthenticated by necessity -- there is nothing to authenticate against
    yet -- and available exactly once: it returns 409 the moment a passcode
    exists. Changing one afterwards requires the current one.
    """
    try:
        credentials = passcodes.set_passcode(body.passcode)
    except security.AlreadyConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except security.WeakPasscode as exc:
        raise HTTPException(UNPROCESSABLE, str(exc))

    _set_session_cookie(response, security.issue_session(credentials), settings)
    return AuthStatus(configured=True, authenticated=True,
                      source=security.SOURCE_PASSCODE)


@router.put("/passcode", response_model=AuthStatus,
            dependencies=[Depends(require_session)])
def change_passcode(body: PasscodeChangeIn, request: Request,
                    passcodes: security.PasscodeStore = Depends(get_passcodes),
                    limiter: security.RateLimiter = Depends(get_rate_limiter)):
    """Replace the passcode. Existing sessions survive; see security.py.

    Two guards, and both are load-bearing. It requires a session, because
    changing a passcode is something the signed-in user does from Settings --
    and without that this endpoint verifies the current passcode while
    sitting on the unauthenticated router, which makes it a brute-force
    oracle that bypasses the limit on /login entirely. It is then rate-limited
    on the same counter as login, so the two cannot be played off against
    each other by a caller who has somehow obtained a session.
    """
    key = _client_key(request)
    if not limiter.check(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many attempts; try again later",
            headers={"Retry-After": str(limiter.retry_after(key))})
    try:
        passcodes.change_passcode(body.current_passcode, body.new_passcode)
    except security.NotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except security.WeakPasscode as exc:
        raise HTTPException(UNPROCESSABLE, str(exc))
    except PermissionError as exc:
        limiter.record(key)
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    limiter.reset(key)
    return AuthStatus(configured=True, authenticated=True)


@router.post("/login", response_model=AuthStatus)
def login(body: PasscodeIn, request: Request, response: Response,
          passcodes: security.PasscodeStore = Depends(get_passcodes),
          limiter: security.RateLimiter = Depends(get_rate_limiter),
          settings: Settings = Depends(get_settings)):
    """Exchange the passcode for a session cookie.

    Rate-limited per client address: a passcode is short by nature, so
    unlimited guessing is the one attack this design is genuinely exposed to.
    The limit is checked before the hash is verified, so a locked-out caller
    does not even get the timing signal.
    """
    key = _client_key(request)
    if not limiter.check(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many attempts; try again later",
            headers={"Retry-After": str(limiter.retry_after(key))})

    try:
        credentials = passcodes.load()
    except security.NotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    if not security.verify(credentials, body.passcode):
        limiter.record(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect passcode")

    limiter.reset(key)
    _set_session_cookie(response, security.issue_session(credentials), settings)
    return AuthStatus(configured=True, authenticated=True,
                      source=security.SOURCE_PASSCODE)


@router.post("/logout", response_model=AuthStatus)
def logout(response: Response, settings: Settings = Depends(get_settings)):
    """Clear the session cookie.

    Session tokens are stateless and signed (see security.py), so this drops
    the browser's copy rather than revoking the token. To revoke everything --
    a lost device -- delete the credentials file and set a new passcode,
    which rotates the signing secret.
    """
    response.delete_cookie(
        security.SESSION_COOKIE, path="/",
        httponly=True, samesite="lax", secure=settings.https_only)
    return AuthStatus(configured=True, authenticated=False)


# --- Entra ID --------------------------------------------------------------
#
# Two endpoints and a redirect between them. Neither returns JSON: the browser
# is navigating, not fetching, because the sign-in has to happen at the top
# level -- Entra refuses to be framed, and an XHR cannot show a login page.


def _safe_next(candidate: str | None) -> str:
    """Where to send the browser after signing in.

    Only a path on this origin. A `next` that survived as an absolute URL
    would make this endpoint an open redirect -- and an open redirect on a
    login route is a phishing primitive, because the victim really is signing
    in to the real app before being sent on. `//host` is rejected too: it is
    protocol-relative, so browsers read it as another origin.
    """
    if (not candidate or not candidate.startswith("/")
            or candidate.startswith("//")):
        return "/"
    return candidate


def _require_client(client: entra.Client | None) -> entra.Client:
    if client is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "no Entra app registration is configured on this instance")
    return client


@router.get("/entra/login")
def entra_login(request: Request,
                next: str = "/",
                silent: bool = False,
                client: entra.Client | None = Depends(get_entra),
                passcodes: security.PasscodeStore = Depends(get_passcodes),
                settings: Settings = Depends(get_settings)):
    """Begin a sign-in: remember the attempt, then hand the browser to Entra.

    Requires a passcode to already be set, because the credentials file is
    where the signing secret lives and both the sign-in state and the
    resulting session are signed with it. That ordering is not an accident of
    implementation: the passcode is the break-glass route, and an instance
    that federated before it had one would have no way back in when the
    directory is unreachable -- which is the one situation break-glass is for.
    """
    client = _require_client(client)
    try:
        credentials = passcodes.load()
    except security.NotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    flow = entra.start_flow()
    try:
        destination = client.authorization_url(flow, silent=silent)
    except entra.EntraError as exc:
        # Discovery failed, so the directory is unreachable. Say so plainly:
        # this is precisely when the user needs to know the passcode still
        # works.
        log.warning("entra: could not build sign-in url: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "the directory is unreachable; sign in with the passcode instead")

    response = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SIGNIN_COOKIE,
        security.seal(credentials.session_secret,
                      {"state": flow.state, "nonce": flow.nonce,
                       "verifier": flow.verifier, "next": _safe_next(next),
                       "silent": bool(silent)},
                      entra.FLOW_TTL_SECONDS),
        max_age=entra.FLOW_TTL_SECONDS,
        httponly=True, samesite="lax", secure=settings.https_only, path="/")
    return response


@router.get("/entra/callback")
def entra_callback(request: Request,
                   code: str | None = None,
                   state: str | None = None,
                   error: str | None = None,
                   client: entra.Client | None = Depends(get_entra),
                   passcodes: security.PasscodeStore = Depends(get_passcodes),
                   settings: Settings = Depends(get_settings)):
    """Where Entra sends the browser back. Always redirects, never renders.

    Every failure lands on the login screen with a short reason in the query
    string rather than a JSON error: the browser got here by navigation, so a
    401 body would replace the app with a blob of JSON.
    """
    client = _require_client(client)
    try:
        credentials = passcodes.load()
    except security.NotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    flow_state = security.unseal(
        credentials.session_secret, request.cookies.get(SIGNIN_COOKIE))
    if flow_state is None:
        # No cookie, or one older than ten minutes. Usually a stale tab or a
        # bookmarked callback rather than an attack, and either way there is
        # nothing to validate the response against.
        return _signin_failed(settings, "expired")

    silent = bool(flow_state.get("silent"))
    destination = _safe_next(flow_state.get("next"))

    if error:
        # `login_required` and `interaction_required` are the expected answer
        # to a silent renewal that cannot be completed without showing the
        # user something -- their directory session lapsed, or they are no
        # longer assigned to the app. Not an error worth logging as one.
        if silent and error in {"login_required", "interaction_required",
                                "consent_required"}:
            return _signin_failed(settings, "required")
        log.warning("entra: sign-in returned %s", error)
        return _signin_failed(settings, "denied")

    if not code or not state:
        return _signin_failed(settings, "denied")
    # Constant-time, and before the code is spent: a state that does not match
    # means this response belongs to a different sign-in than the one this
    # browser started, which is what CSRF on a login endpoint looks like.
    if not secrets.compare_digest(str(flow_state.get("state", "")), state):
        log.warning("entra: state did not match the sign-in cookie")
        return _signin_failed(settings, "denied")

    try:
        identity = client.redeem(code, entra.Flow(
            state=str(flow_state["state"]), nonce=str(flow_state["nonce"]),
            verifier=str(flow_state["verifier"])))
    except entra.EntraError as exc:
        log.warning("entra: could not complete sign-in: %s", exc)
        return _signin_failed(settings, "denied")

    log.info("entra: signed in %s (%s)", identity.subject, identity.email)
    response = RedirectResponse(destination,
                                status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(
        response,
        security.issue_session(credentials, subject=identity.subject,
                               source=security.SOURCE_ENTRA),
        settings,
        max_age=security.ENTRA_SESSION_TTL_SECONDS)
    _clear_signin_cookie(response, settings)
    return response


def _signin_failed(settings: Settings, reason: str) -> RedirectResponse:
    response = RedirectResponse(f"/?signin={reason}",
                                status_code=status.HTTP_303_SEE_OTHER)
    _clear_signin_cookie(response, settings)
    return response


def _clear_signin_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(SIGNIN_COOKIE, path="/", httponly=True,
                           samesite="lax", secure=settings.https_only)
