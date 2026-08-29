"""Passcode setup, login and logout.

The only unauthenticated router in the app. Everything else hangs off a
router carrying `require_session`, so a new route is protected unless
somebody deliberately puts it here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from server import security
from server.deps import (get_passcodes, get_rate_limiter, get_settings,
                         require_session)
from server.schemas import AuthStatus, PasscodeChangeIn, PasscodeIn
from server.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 422. Spelled as a literal because starlette renamed the constant
# (HTTP_422_UNPROCESSABLE_ENTITY -> ..._CONTENT) and deprecated the old
# name; the number is the part that is actually stable.
UNPROCESSABLE = 422


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, token: str,
                        settings: Settings) -> None:
    response.set_cookie(
        security.SESSION_COOKIE,
        token,
        max_age=security.SESSION_TTL_SECONDS,
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
            passcodes: security.PasscodeStore = Depends(get_passcodes)):
    """Whether a passcode exists and whether this caller is signed in.

    Unauthenticated on purpose: the client needs it to decide between the
    first-run setup screen, the login screen, and the app itself.
    """
    if not passcodes.is_configured():
        return AuthStatus(configured=False, authenticated=False)
    credentials = passcodes.load()
    return AuthStatus(
        configured=True,
        authenticated=security.session_is_valid(
            credentials, request.cookies.get(security.SESSION_COOKIE)))


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
    return AuthStatus(configured=True, authenticated=True)


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
    return AuthStatus(configured=True, authenticated=True)


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
