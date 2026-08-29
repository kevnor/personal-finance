"""Single-passcode authentication.

The threat model, stated plainly (and unchanged from the spec): this stops a
guest's laptop or an IoT device on the same wifi from browsing the user's
finances. It is not hardening against a determined attacker already inside
the network. The network boundary -- LAN, then Tailscale -- does the real
work. So: no user table, no roles, no registration, one passcode.

Three pieces live here, none of which touch the database. Credentials belong
on the mounted volume next to it, not in it: a database restored from a
backup must not silently restore an old passcode with it, and a dump shared
for debugging must not carry one at all.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# A passcode session lasts 30 days, per the spec. The expiry is inside the
# signed token, so a cookie kept past it is rejected by the server rather than
# merely dropped by a cooperating browser.
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
SESSION_COOKIE = "pf_session"

# An Entra session lasts an hour, and that difference is the whole point of
# federating: removing somebody in Entra has to actually lock them out, and a
# 30-day cookie would leave them working access for a month after the click.
# An hour is short enough to matter and long enough that the silent renewal
# (see routes/auth.py) is not constantly redirecting. The passcode path keeps
# 30 days because nothing in Entra governs it -- which is the standing cost of
# keeping it as a break-glass route, and is why it is documented rather than
# quietly accepted.
ENTRA_SESSION_TTL_SECONDS = 60 * 60

# How a session was obtained. Recorded in the token because the two are
# governed differently: only an Entra session can be silently renewed, and
# only an Entra session is revocable from the directory.
SOURCE_PASSCODE = "passcode"
SOURCE_ENTRA = "entra"

# The subject recorded for a passcode session. The passcode authenticates the
# household, not a person -- there is no user table behind it -- so it gets a
# fixed subject rather than a fabricated identity.
PASSCODE_SUBJECT = "household"

# Rate limit on the passcode endpoint: a short window and a small budget. A
# passcode is short by nature, so unlimited guessing is the one attack this
# design is genuinely exposed to.
RATE_LIMIT_ATTEMPTS = 10
RATE_LIMIT_WINDOW_SECONDS = 15 * 60

MIN_PASSCODE_LENGTH = 6

_hasher = PasswordHasher()


class NotConfigured(RuntimeError):
    """No passcode has been set yet."""


class AlreadyConfigured(RuntimeError):
    """A passcode is already set; it cannot be re-set without the old one."""


class WeakPasscode(ValueError):
    """The proposed passcode is too short."""


@dataclass(frozen=True)
class Credentials:
    """What lives in the config file: a passcode hash and a signing secret.

    The secret signs session cookies. It is generated once and kept, so
    sessions survive a restart -- a 30-day expiry means nothing if every
    deploy silently invalidates it. Rotating it (by deleting the file and
    setting a new passcode) invalidates every outstanding session, which is
    the recovery path if a device is lost.
    """
    passcode_hash: str
    session_secret: str


class PasscodeStore:
    """Reads and writes the credentials file on the data volume."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def is_configured(self) -> bool:
        return self.path.exists()

    def load(self) -> Credentials:
        if not self.path.exists():
            raise NotConfigured(
                f"no passcode set. POST /api/auth/passcode to set one"
                f" (it will be written to {self.path}).")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return Credentials(data["passcode_hash"], data["session_secret"])

    def set_passcode(self, passcode: str) -> Credentials:
        """Set the passcode on first run. Refuses to overwrite an existing one.

        First-run passcode setting is unauthenticated by necessity -- there is
        nothing yet to authenticate against -- so it must be available exactly
        once. Anyone who reaches an unconfigured instance first owns it; the
        network boundary is what makes that acceptable, and it is why the
        endpoint closes the moment a passcode exists.
        """
        if self.is_configured():
            raise AlreadyConfigured(
                "a passcode is already set; change it with the current one")
        return self._write(passcode, secrets.token_urlsafe(32))

    def change_passcode(self, current: str, new: str) -> Credentials:
        """Replace the passcode, keeping sessions alive.

        The signing secret is deliberately preserved: changing a passcode
        because it was weak should not log the user out of every device. To
        invalidate sessions instead -- a lost phone -- delete the credentials
        file and set a new passcode.
        """
        existing = self.load()
        if not verify(existing, current):
            raise PermissionError("current passcode is incorrect")
        return self._write(new, existing.session_secret)

    def _write(self, passcode: str, session_secret: str) -> Credentials:
        if len(passcode) < MIN_PASSCODE_LENGTH:
            raise WeakPasscode(
                f"passcode must be at least {MIN_PASSCODE_LENGTH} characters")
        credentials = Credentials(_hasher.hash(passcode), session_secret)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Written via a temporary file in the same directory so a crash
        # mid-write cannot leave a truncated credentials file -- which would
        # lock the user out with no way back except deleting it.
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "passcode_hash": credentials.passcode_hash,
            "session_secret": credentials.session_secret,
        }, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
        return credentials


def verify(credentials: Credentials, passcode: str) -> bool:
    """Check a passcode against the stored hash.

    argon2 raises rather than returning False, and distinguishes a mismatch
    from a malformed hash. Both mean "not authenticated" to a caller, so both
    are flattened here -- but a malformed hash is a corrupt credentials file
    rather than a wrong guess, and treating it as a wrong guess is the safe
    direction to fail.
    """
    try:
        return _hasher.verify(credentials.passcode_hash, passcode)
    except (VerifyMismatchError, InvalidHashError):
        return False


# --- session tokens --------------------------------------------------------
#
# Stateless and signed, rather than a server-side session table. One user on
# one small container does not need the table, and a token that survives a
# restart is what makes the 30-day expiry real. The cost is that `logout`
# clears the cookie rather than revoking the token: a copy taken off the wire
# stays valid until it expires. Against this threat model -- the network is
# the boundary, and on the tailnet it is already encrypted -- that trade is
# the intended one. Rotating the signing secret revokes everything at once.


@dataclass(frozen=True)
class Session:
    """What a valid session cookie says: who, how, and until when."""
    subject: str
    source: str
    expires_at: int

    @property
    def is_entra(self) -> bool:
        return self.source == SOURCE_ENTRA


def issue_session(credentials: Credentials, now: float | None = None,
                  subject: str = PASSCODE_SUBJECT,
                  source: str = SOURCE_PASSCODE,
                  ttl_seconds: int | None = None) -> str:
    """Sign a session token.

    The defaults describe a passcode session, so every existing caller keeps
    working unchanged; the Entra path passes all three.
    """
    if ttl_seconds is None:
        ttl_seconds = (ENTRA_SESSION_TTL_SECONDS if source == SOURCE_ENTRA
                       else SESSION_TTL_SECONDS)
    return seal(credentials.session_secret,
                {"sub": subject, "src": source}, ttl_seconds, now)


def read_session(credentials: Credentials, token: str | None,
                 now: float | None = None) -> Session | None:
    """Return the session a token carries, or None if it is not usable.

    One function for "is this valid" and "who is it", because splitting them
    invites a caller to read the subject out of a token whose signature it
    never checked. Every failure -- no cookie, a bad signature, a payload
    this version cannot parse, an expired token -- returns None: to a caller
    they all mean "not signed in", and distinguishing them in a response
    would tell an attacker which part they got right.

    A token issued before sessions carried a subject is not readable here and
    so reads as signed-out. That costs one re-login on upgrade, which is the
    right trade against carrying a second token format forever.
    """
    payload = unseal(credentials.session_secret, token, now)
    if payload is None:
        return None
    try:
        return Session(subject=str(payload["sub"]),
                       source=str(payload["src"]),
                       expires_at=int(payload["exp"]))
    except (ValueError, TypeError, KeyError):
        return None


def session_is_valid(credentials: Credentials, token: str | None,
                     now: float | None = None) -> bool:
    return read_session(credentials, token, now) is not None


def seal(secret: str, data: dict, ttl_seconds: int,
         now: float | None = None) -> str:
    """Sign a short-lived payload so it can be handed to the browser safely.

    Used for the session cookie and for the state carried through the Entra
    round trip. Signed, not encrypted: nothing sealed here is a secret from
    the person holding it -- it is their own session, or their own sign-in
    attempt -- what matters is that they cannot alter it.
    """
    payload = dict(data)
    payload["exp"] = int((now if now is not None else time.time())
                         + ttl_seconds)
    # Compact and key-ordered so identical data always signs to identical
    # bytes -- a token that differed run to run would be untestable.
    body = base64.urlsafe_b64encode(json.dumps(
        payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{body}.{_sign(secret, body)}"


def unseal(secret: str, token: str | None,
           now: float | None = None) -> dict | None:
    """The inverse of `seal`, or None if the token is not usable.

    One function for "is this genuine" and "what does it say", because
    splitting them invites a caller to read a payload whose signature it
    never checked. Every failure -- absent, altered, unparseable, expired --
    returns None: they all mean the same thing to a caller, and telling them
    apart in a response would say which part an attacker got right.
    """
    if not token or "." not in token:
        return None
    body, _, signature = token.partition(".")
    if not hmac.compare_digest(_sign(secret, body), signature):
        return None
    try:
        padding = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + padding))
        expires_at = int(payload["exp"])
    except (ValueError, TypeError, KeyError):
        return None
    if not isinstance(payload, dict):
        return None
    if expires_at <= (now if now is not None else time.time()):
        return None
    return payload


def _sign(secret: str, body: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("ascii"),
                      sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


# --- rate limiting ---------------------------------------------------------


class RateLimiter:
    """Fixed-window attempt counter, in memory.

    In memory is the right scope: there is one process, and attempts that
    predate a restart are not interesting. Keyed by client address so a
    locked-out attacker on the LAN does not also lock out the user.
    """

    def __init__(self, attempts: int = RATE_LIMIT_ATTEMPTS,
                 window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, now: float | None = None) -> bool:
        """True if another attempt is allowed. Does not record one."""
        return len(self._recent(key, now)) < self.attempts

    def record(self, key: str, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self._hits.setdefault(key, []).append(now)

    def reset(self, key: str) -> None:
        """Clear a key's history, called on a successful login."""
        self._hits.pop(key, None)

    def retry_after(self, key: str, now: float | None = None) -> int:
        recent = self._recent(key, now)
        if not recent:
            return 0
        now = now if now is not None else time.time()
        return max(0, int(recent[0] + self.window_seconds - now) + 1)

    def _recent(self, key: str, now: float | None = None) -> list[float]:
        now = now if now is not None else time.time()
        cutoff = now - self.window_seconds
        recent = [hit for hit in self._hits.get(key, []) if hit > cutoff]
        if recent:
            self._hits[key] = recent
        else:
            self._hits.pop(key, None)
        return recent
