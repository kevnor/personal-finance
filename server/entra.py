"""OIDC client for Microsoft Entra ID.

The app is a *confidential* client: the authorization code is exchanged for
tokens by this process, over its own TLS connection to Microsoft, using a
client secret. No token from Entra ever reaches the browser. What the browser
gets is the same signed, httpOnly session cookie it got from the passcode
path, which is what keeps the rest of the app -- and the service worker's
offline gate -- unchanged. See README "Authentication".

The ID token is validated rather than trusted. OIDC Core 3.1.3.7 permits a
confidential client to skip signature checking when the token arrives
directly from the token endpoint over TLS, and that shortcut is deliberately
not taken here: it is sound only for as long as nobody moves this code to a
flow where the browser carries the token, and that is not a property a future
edit would notice it was breaking.

Five claims are checked, and `tid` is the one that matters most. If the app
registration is ever switched to multitenant -- a single dropdown in the
portal -- then without a `tid` check every Microsoft account in the world
becomes a valid sign-in. That is the failure this module exists to prevent,
so it is checked explicitly rather than left to the audience.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from server.settings import EntraSettings

# Only what the app needs: who you are. No Graph scopes, no directory reads --
# the app asks Entra to authenticate, and lets Entra decide who is allowed
# through via the enterprise app's user assignment.
SCOPES = "openid profile email"

# The code and the state cookie both live only for the round trip through
# Entra. Ten minutes is long enough for a slow sign-in with MFA and short
# enough that a state cookie left on a shared machine is not a way back in.
FLOW_TTL_SECONDS = 10 * 60

NETWORK_TIMEOUT_SECONDS = 10


class EntraError(RuntimeError):
    """Sign-in could not be completed.

    One class for every failure -- unreachable directory, a refused code, a
    token that does not validate -- because the caller does exactly the same
    thing with all of them: send the user back to the login screen. The
    message is for the log, not the browser.
    """


@dataclass(frozen=True)
class Identity:
    """Who signed in, as far as the app is concerned."""
    subject: str          # the `oid` claim: stable per user per tenant
    name: str | None
    email: str | None


@dataclass(frozen=True)
class Flow:
    """The one-use secrets of a single sign-in attempt."""
    state: str
    nonce: str
    verifier: str

    @property
    def challenge(self) -> str:
        digest = hashlib.sha256(self.verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def start_flow() -> Flow:
    return Flow(state=secrets.token_urlsafe(24),
                nonce=secrets.token_urlsafe(24),
                verifier=secrets.token_urlsafe(48))


class Client:
    """Talks to one tenant. Caches what Entra says is cacheable."""

    def __init__(self, config: EntraSettings):
        self.config = config
        self._metadata: dict | None = None
        self._jwks: PyJWKClient | None = None

    # -- discovery ----------------------------------------------------------

    def metadata(self) -> dict:
        """The tenant's OIDC discovery document, fetched once.

        Cached for the life of the process rather than given a TTL: the two
        values taken from it (the endpoints) do not move, and a cache that
        expired would turn a Microsoft outage into a sign-in failure for
        users who already had everything needed to sign in.
        """
        if self._metadata is None:
            self._metadata = self._get_json(
                f"{self.config.authority}/.well-known/openid-configuration")
        return self._metadata

    def _jwk_client(self) -> PyJWKClient:
        if self._jwks is None:
            self._jwks = PyJWKClient(self.metadata()["jwks_uri"],
                                     cache_keys=True)
        return self._jwks

    # -- the redirect out ---------------------------------------------------

    def authorization_url(self, flow: Flow, *, silent: bool = False) -> str:
        """Where to send the browser to sign in.

        `silent` sets `prompt=none`, which tells Entra to complete the sign-in
        only if it can do so without showing the user anything -- their
        directory session is still live and they are still assigned to the
        app. That is what makes an hour-long session bearable: renewal is a
        round trip, not a login. If it cannot, Entra returns `login_required`
        rather than a screen, and the caller falls back to a real sign-in.
        """
        query = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "response_mode": "query",
            "scope": SCOPES,
            "state": flow.state,
            "nonce": flow.nonce,
            "code_challenge": flow.challenge,
            "code_challenge_method": "S256",
        }
        if silent:
            query["prompt"] = "none"
        return (self.metadata()["authorization_endpoint"]
                + "?" + urllib.parse.urlencode(query))

    # -- the redirect back --------------------------------------------------

    def redeem(self, code: str, flow: Flow) -> Identity:
        """Exchange the code for tokens and return the validated identity."""
        body = urllib.parse.urlencode({
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "code_verifier": flow.verifier,
            "scope": SCOPES,
        }).encode("ascii")

        payload = self._post_form(self.metadata()["token_endpoint"], body)
        id_token = payload.get("id_token")
        if not id_token:
            raise EntraError("token response carried no id_token")
        return self._identity(id_token, flow.nonce)

    def _identity(self, id_token: str, nonce: str) -> Identity:
        try:
            key = self._jwk_client().get_signing_key_from_jwt(id_token).key
            claims = jwt.decode(
                id_token, key, algorithms=["RS256"],
                audience=self.config.client_id,
                issuer=self.config.authority,
                options={"require": ["exp", "iat", "aud", "iss", "sub"]})
        except jwt.PyJWTError as exc:
            raise EntraError(f"id_token did not validate: {exc}") from exc
        except urllib.error.URLError as exc:
            raise EntraError(f"could not fetch signing keys: {exc}") from exc

        # The claim that stops a multitenant registration from admitting the
        # whole world. `aud` alone does not: every tenant's tokens for this
        # app carry this app's client id.
        if claims.get("tid") != self.config.tenant_id:
            raise EntraError(
                f"id_token is from tenant {claims.get('tid')!r},"
                f" not {self.config.tenant_id!r}")
        if nonce and claims.get("nonce") != nonce:
            raise EntraError("id_token nonce does not match this sign-in")

        # `oid` over `sub`: `sub` is pairwise, so it changes if the app
        # registration is ever recreated, silently orphaning anything keyed
        # on it. `oid` is the user's id in the tenant and survives that.
        subject = claims.get("oid") or claims.get("sub")
        if not subject:
            raise EntraError("id_token identifies no user")
        return Identity(subject=str(subject),
                        name=claims.get("name"),
                        email=(claims.get("preferred_username")
                               or claims.get("email")))

    # -- transport ----------------------------------------------------------

    def _get_json(self, url: str) -> dict:
        return self._request(urllib.request.Request(
            url, headers={"Accept": "application/json"}))

    def _post_form(self, url: str, body: bytes) -> dict:
        return self._request(urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"}))

    def _request(self, request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(
                    request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # Entra puts a machine-readable reason in the body of a 400. It
            # is the difference between "the secret has expired" and "that
            # code was already used", so it is worth carrying into the log.
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise EntraError(f"{request.full_url} -> {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EntraError(f"{request.full_url} unreachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise EntraError(f"{request.full_url} returned non-JSON") from exc
