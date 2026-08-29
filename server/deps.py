"""Request-scoped dependencies: the database connection and the auth gate."""
from __future__ import annotations

import datetime
import sqlite3
from typing import Iterator

from fastapi import Depends, HTTPException, Request, status

from server import entra, security
from server.lib import local, store
from server.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_passcodes(request: Request) -> security.PasscodeStore:
    return request.app.state.passcodes


def get_rate_limiter(request: Request) -> security.RateLimiter:
    return request.app.state.rate_limiter


def get_entra(request: Request) -> "entra.Client | None":
    """The Entra client, or None when no app registration is configured.

    None is the ordinary state, not a broken one: an instance with no
    registration is passcode-only, which is what the repository ships as and
    what every test that does not care about federation runs as.
    """
    return request.app.state.entra


def today(settings: Settings = Depends(get_settings)) -> datetime.date:
    """The app's idea of the current date, in its configured timezone.

    Not `date.today()`: that reads the container's clock setting, and a
    container running UTC would roll the day over at 01:00 or 02:00 local,
    putting a late-evening purchase into tomorrow's allowance.
    """
    return datetime.datetime.now(settings.timezone).date()


def db(settings: Settings = Depends(get_settings)) -> Iterator[sqlite3.Connection]:
    """A read-write connection for the length of one request.

    `same_thread=False` because FastAPI runs a sync dependency's setup, the
    route handler and the dependency's teardown on whichever threadpool
    worker is free at each step -- so this connection is legitimately used
    from more than one thread over the life of one request. Sequentially,
    never concurrently: each step awaits the one before it. See
    `store.connect` for why that is safe, and note that a TestClient will not
    reproduce the failure, because with one client and a cold pool the same
    worker tends to serve every step.
    """
    con = store.connect(settings.db_path, same_thread=False)
    try:
        yield con
    finally:
        con.close()


def db_ro(settings: Settings = Depends(get_settings)) -> Iterator[sqlite3.Connection]:
    """A read-only connection, for routes that only report.

    The same reasoning as `cli.reconcile`: a GET that promises not to mutate
    should be unable to, rather than merely intending not to. SQLite enforces
    it -- any write on this connection raises -- so a stray UPDATE in a
    reporting path is a loud 500 in a test rather than a silent edit in
    production.

    `same_thread=False` for the same reason as `db` above.
    """
    con = store.connect(settings.db_path, read_only=True, same_thread=False)
    try:
        yield con
    finally:
        con.close()


def household(settings: Settings = Depends(get_settings)) -> local.LocalData:
    """The household's own rules and corrections, or EMPTY where there are none.

    Read per request rather than cached at startup: it is one small file, and
    a user who edits it should not have to restart the server to see the
    effect. A fresh deployment has no such file at all, which is why every
    consumer degrades to the built-in rules rather than failing.
    """
    return local.load(settings.local_file)


def require_session(
    request: Request,
    passcodes: security.PasscodeStore = Depends(get_passcodes),
) -> None:
    """Reject a request without a valid session cookie.

    Applied to the whole /api router rather than route by route, so a new
    route is protected by default. Forgetting to add a decorator is a silent
    hole; forgetting to *remove* one is a visible 401.
    """
    try:
        credentials = passcodes.load()
    except security.NotConfigured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="no passcode set; POST /api/auth/passcode first")

    token = request.cookies.get(security.SESSION_COOKIE)
    if not security.session_is_valid(credentials, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not signed in")
