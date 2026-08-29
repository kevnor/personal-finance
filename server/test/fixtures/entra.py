"""A fake Entra tenant: real RSA signing, no network.

Shared by the unit tests for the OIDC client and the HTTP tests for the
sign-in routes, so both exercise the same token-minting path. The key is
real and `jwt.decode` runs for real against it -- what is faked is only the
transport, so a test that stopped verifying signatures would still fail.
"""
from __future__ import annotations

import datetime
import functools

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from server import entra
from server.settings import EntraSettings

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
OTHER_TENANT = "99999999-9999-9999-9999-999999999999"
USER_OID = "33333333-3333-3333-3333-333333333333"
USER_EMAIL = "member@example.onmicrosoft.com"
PUBLIC_ORIGIN = "https://finance.example.ts.net"

CONFIG = EntraSettings(tenant_id=TENANT, client_id=CLIENT_ID,
                       client_secret="s3cret", public_origin=PUBLIC_ORIGIN)

ENVIRONMENT = {
    "PF_ENTRA_TENANT_ID": TENANT,
    "PF_ENTRA_CLIENT_ID": CLIENT_ID,
    "PF_ENTRA_CLIENT_SECRET": "s3cret",
    "PF_PUBLIC_ORIGIN": PUBLIC_ORIGIN,
}


@functools.lru_cache(maxsize=1)
def signing_key():
    """Generated once per session: it is the slow part of these tests."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _Key:
    def __init__(self, key):
        self.key = key


class FakeTenant:
    """Stands in for one tenant's OIDC endpoints."""

    def __init__(self):
        self.keypair = signing_key()
        self.token_response: dict = {}
        self.posted: list[bytes] = []
        # Set to an EntraError to make discovery fail, which is how the
        # "directory unreachable" path is reached without a network.
        self.discovery_error: Exception | None = None

    def install(self, client: entra.Client) -> entra.Client:
        base = f"https://login.microsoftonline.com/{TENANT}"
        if self.discovery_error is None:
            client._metadata = {
                "authorization_endpoint": f"{base}/oauth2/v2.0/authorize",
                "token_endpoint": f"{base}/oauth2/v2.0/token",
                "jwks_uri": f"{base}/discovery/v2.0/keys",
            }
        else:
            def explode():
                raise self.discovery_error
            client.metadata = explode
        client._jwks = self
        client._post_form = self._post_form
        return client

    def client(self) -> entra.Client:
        return self.install(entra.Client(CONFIG))

    # -- stands in for PyJWKClient
    def get_signing_key_from_jwt(self, token):
        return _Key(self.keypair.public_key())

    def _post_form(self, url, body):
        self.posted.append(body)
        return self.token_response

    def id_token(self, **overrides) -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        claims = {
            "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "aud": CLIENT_ID,
            "tid": TENANT,
            "oid": USER_OID,
            "sub": "pairwise-subject",
            "name": "Household Member",
            "preferred_username": USER_EMAIL,
            "iat": now,
            "exp": now + datetime.timedelta(hours=1),
        }
        claims.update(overrides)
        return jwt.encode(claims, self.keypair, algorithm="RS256")

    def will_return(self, **overrides) -> None:
        """Arm the token endpoint with an id_token carrying these claims."""
        self.token_response = {"id_token": self.id_token(**overrides)}
