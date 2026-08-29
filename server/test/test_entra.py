"""Entra ID sign-in: the checks that decide who gets in.

The interesting tests here are the refusals. A sign-in that works is easy to
notice broken; a sign-in that accepts a token it should not is the failure
nobody sees. So every claim the app relies on gets a test that alters just
that claim and asserts the token stops being accepted -- above all `tid`,
which is what stands between a multitenant app registration and every
Microsoft account in the world.

Nothing here reaches the network. The tenant is faked with a real RSA key, so
`jwt.decode` runs for real: signature, issuer, audience and expiry are
genuinely verified rather than stubbed past.
"""
import datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server import entra
from server.test.fixtures.entra import (CLIENT_ID, OTHER_TENANT, TENANT,
                                        USER_EMAIL, USER_OID, FakeTenant)


@pytest.fixture
def tenant():
    return FakeTenant()


@pytest.fixture
def client(tenant):
    return tenant.client()


def redeem(client, tenant, flow=None, **overrides):
    flow = flow or entra.start_flow()
    tenant.token_response = {"id_token": tenant.id_token(
        nonce=flow.nonce, **overrides)}
    return client.redeem("the-code", flow)


# -- the happy path ---------------------------------------------------------

def test_a_valid_token_yields_the_identity(client, tenant):
    identity = redeem(client, tenant)
    assert identity.subject == USER_OID
    assert identity.email == USER_EMAIL
    assert identity.name == "Household Member"


def test_the_subject_is_oid_not_sub(client, tenant):
    """`sub` is pairwise: it changes if the app registration is ever
    recreated, silently orphaning anything keyed on it. `oid` is the user's
    id in the tenant and survives that."""
    identity = redeem(client, tenant)
    assert identity.subject == USER_OID != "pairwise-subject"


def test_the_code_is_exchanged_with_the_client_secret_and_verifier(
        client, tenant):
    """Proof this is a confidential client using PKCE, not a public one."""
    flow = entra.start_flow()
    redeem(client, tenant, flow)
    sent = tenant.posted[0].decode()
    assert "client_secret=s3cret" in sent
    assert f"code_verifier={flow.verifier}" in sent
    assert "grant_type=authorization_code" in sent


# -- the refusals -----------------------------------------------------------

def test_a_token_from_another_tenant_is_refused(client, tenant):
    """The one that matters. If the registration is ever switched to
    multitenant, every Microsoft account on earth gets a token whose audience
    is this app -- and `aud` alone would accept it."""
    with pytest.raises(entra.EntraError, match="tenant"):
        redeem(client, tenant, tid=OTHER_TENANT)


def test_a_token_with_no_tenant_claim_is_refused(client, tenant):
    with pytest.raises(entra.EntraError, match="tenant"):
        redeem(client, tenant, tid=None)


def test_a_replayed_nonce_is_refused(client, tenant):
    """The token is genuine and for this app, but belongs to a different
    sign-in than the one this browser started."""
    tenant.token_response = {"id_token": tenant.id_token(nonce="somebody-elses")}
    with pytest.raises(entra.EntraError, match="nonce"):
        client.redeem("the-code", entra.start_flow())


def test_a_token_for_another_audience_is_refused(client, tenant):
    with pytest.raises(entra.EntraError, match="did not validate"):
        redeem(client, tenant, aud="some-other-app")


def test_a_token_from_another_issuer_is_refused(client, tenant):
    with pytest.raises(entra.EntraError, match="did not validate"):
        redeem(client, tenant,
               iss=f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0")


def test_an_expired_token_is_refused(client, tenant):
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    with pytest.raises(entra.EntraError, match="did not validate"):
        redeem(client, tenant, exp=past, iat=past)


def test_a_token_signed_by_the_wrong_key_is_refused(client, tenant):
    """Proves the signature is actually checked rather than the payload
    merely decoded -- the failure a base64-and-trust implementation passes."""
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    flow = entra.start_flow()
    claims = jwt.decode(tenant.id_token(nonce=flow.nonce), options={
        "verify_signature": False})
    tenant.token_response = {
        "id_token": jwt.encode(claims, impostor, algorithm="RS256")}
    with pytest.raises(entra.EntraError, match="did not validate"):
        client.redeem("the-code", flow)


def test_an_unsigned_token_is_refused(client, tenant):
    """`alg: none` is the classic JWT attack, and PyJWT only resists it
    because the algorithm list is pinned to RS256."""
    flow = entra.start_flow()
    claims = jwt.decode(tenant.id_token(nonce=flow.nonce), options={
        "verify_signature": False})
    tenant.token_response = {"id_token": jwt.encode(claims, None, algorithm="none")}
    with pytest.raises(entra.EntraError, match="did not validate"):
        client.redeem("the-code", flow)


def test_a_token_response_with_no_id_token_is_refused(client, tenant):
    tenant.token_response = {"access_token": "not what we asked for"}
    with pytest.raises(entra.EntraError, match="no id_token"):
        client.redeem("the-code", entra.start_flow())


def test_a_token_identifying_nobody_is_refused(client, tenant):
    with pytest.raises(entra.EntraError):
        redeem(client, tenant, oid=None, sub=None)


# -- the redirect out -------------------------------------------------------

def test_the_authorization_url_carries_pkce_and_the_one_use_values(client):
    flow = entra.start_flow()
    url = client.authorization_url(flow)
    assert f"state={flow.state}" in url
    assert f"nonce={flow.nonce}" in url
    assert f"code_challenge={flow.challenge}" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    # The verifier is the secret half of PKCE and must never leave the server
    # by the front channel.
    assert flow.verifier not in url


def test_prompt_none_is_set_only_for_a_silent_renewal(client):
    assert "prompt=none" not in client.authorization_url(entra.start_flow())
    assert "prompt=none" in client.authorization_url(
        entra.start_flow(), silent=True)


def test_the_challenge_is_the_sha256_of_the_verifier(client):
    """Not a second random value: S256 means the server can only match them
    if the same client presents both halves."""
    import base64
    import hashlib
    flow = entra.start_flow()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(flow.verifier.encode()).digest()).decode().rstrip("=")
    assert flow.challenge == expected


def test_each_sign_in_gets_fresh_values(client):
    a, b = entra.start_flow(), entra.start_flow()
    assert {a.state, a.nonce, a.verifier} & {b.state, b.nonce, b.verifier} == set()


def test_no_directory_scopes_are_requested(client):
    """The app asks Entra to authenticate, and lets Entra decide who is
    allowed through. It never reads the directory, so it never asks for the
    permission to -- which is what keeps the app registration consentable
    without an admin granting Graph access."""
    assert entra.SCOPES == "openid profile email"
    assert "Directory" not in client.authorization_url(entra.start_flow())


# -- configuration ----------------------------------------------------------
#
# The variables are read at startup, so a mistake here is a container that
# will not boot -- which is the right place for it, and the reason partial
# configuration raises rather than quietly reverting to passcode-only.

from server.settings import Settings  # noqa: E402

BASE = {"PF_DATA_DIR": "/tmp/pf-test-data"}
FULL = {**BASE, "PF_ENTRA_TENANT_ID": TENANT, "PF_ENTRA_CLIENT_ID": CLIENT_ID,
        "PF_ENTRA_CLIENT_SECRET": "s3cret",
        "PF_PUBLIC_ORIGIN": "https://finance.example.ts.net"}


def test_no_entra_variables_means_passcode_only():
    """What a fresh clone is, and what most of the suite runs as."""
    assert Settings.from_env(BASE).entra is None


def test_all_four_variables_configure_it():
    config = Settings.from_env(FULL).entra
    assert config.tenant_id == TENANT
    assert config.redirect_uri == (
        "https://finance.example.ts.net/api/auth/entra/callback")
    assert config.authority == (
        f"https://login.microsoftonline.com/{TENANT}/v2.0")


@pytest.mark.parametrize("omitted", [
    "PF_ENTRA_TENANT_ID", "PF_ENTRA_CLIENT_ID", "PF_ENTRA_CLIENT_SECRET",
    "PF_PUBLIC_ORIGIN"])
def test_partial_configuration_raises_and_names_what_is_missing(omitted):
    """Silently falling back would leave an instance that was meant to
    federate showing a working login screen, with nobody finding out until
    they went looking for the sign-in that was supposed to be enforced."""
    env = {k: v for k, v in FULL.items() if k != omitted}
    with pytest.raises(ValueError, match=omitted):
        Settings.from_env(env)


def test_a_blank_value_counts_as_absent_not_as_configured():
    """Empty environment variables are how a compose file spells "unset"."""
    assert Settings.from_env({**BASE, "PF_ENTRA_TENANT_ID": "  "}).entra is None


def test_a_plain_http_origin_is_refused():
    """Entra will not register a non-HTTPS redirect URI, so this would
    otherwise fail at sign-in rather than at startup."""
    with pytest.raises(ValueError, match="https"):
        Settings.from_env({**FULL, "PF_PUBLIC_ORIGIN": "http://finance.box"})


@pytest.mark.parametrize("origin", ["http://localhost:8000",
                                    "http://127.0.0.1:8000"])
def test_localhost_may_be_plain_http(origin):
    """The one exception Entra itself makes, so development works."""
    assert Settings.from_env({**FULL, "PF_PUBLIC_ORIGIN": origin}).entra


def test_a_trailing_slash_does_not_double_up_in_the_redirect_uri():
    """A redirect URI that does not match the registration character for
    character is refused by Entra, and the error does not say why."""
    config = Settings.from_env(
        {**FULL, "PF_PUBLIC_ORIGIN": "https://finance.example.ts.net/"}).entra
    assert config.redirect_uri == (
        "https://finance.example.ts.net/api/auth/entra/callback")
