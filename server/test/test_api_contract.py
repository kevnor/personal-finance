"""Contract-level guarantees that hold across every route.

The spec asks for one of these by name -- "auth required on every route" --
and it is the kind of rule that is easy to satisfy today and easy to break
tomorrow, since breaking it means *forgetting* something rather than writing
something wrong. So it is asserted by enumerating the app rather than by
listing paths a person has to remember to update.
"""
from __future__ import annotations

import pytest

# Deliberately reachable without a session, and why. Keyed by (method, path),
# not path: PUT /api/auth/passcode is *not* public even though POST to the
# same path is, and collapsing the two would hide that.
#   GET  status   -- the client needs it to decide between the first-run
#                    screen, the login screen, and the app.
#   POST passcode -- first-run setup has nothing to authenticate against yet.
#   POST login    -- it is how a session is obtained.
#   POST logout   -- clearing a cookie you may no longer have must not 401.
PUBLIC_OPERATIONS = {
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/passcode"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    # The Entra round trip. Unauthenticated of necessity, exactly as
    # /api/auth/login is: they are how a session is obtained, so requiring
    # one would be circular. Listed individually rather than by prefix so
    # that a third route appearing under /api/auth/entra/ has to be added
    # here deliberately.
    ("GET", "/api/auth/entra/login"),
    ("GET", "/api/auth/entra/callback"),
}

# A placeholder for each path parameter, so the request reaches the auth
# check rather than failing to route.
PATH_PARAMS = {"transaction_id": "1", "reimbursement_id": "1", "name": "x"}


def api_operations(app) -> list[tuple[str, str]]:
    """Every (method, path) the app publishes under /api."""
    out = []
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api"):
            continue
        for method in operations:
            out.append((method.upper(), path))
    return sorted(out)


def concrete(path: str) -> str:
    for name, value in PATH_PARAMS.items():
        path = path.replace("{" + name + "}", value)
    return path


def test_the_app_publishes_the_routes_the_client_needs(app):
    """A smoke check on the shape of the API, so a router silently failing to
    register shows up here rather than as a 404 in the client."""
    paths = {path for _, path in api_operations(app)}
    assert {
        "/api/auth/login",
        "/api/budget",
        "/api/budget/config",
        "/api/categories",
        "/api/imports",
        "/api/imports/preview",
        "/api/reimbursements",
        "/api/transactions",
        "/api/transactions/bulk",
    } <= paths


def test_every_api_route_is_either_public_by_design_or_requires_a_session(
        anon, app):
    """The check hangs off the router rather than each route, so a new route
    is protected by default. This is what proves that stayed true."""
    unprotected = []
    for method, path in api_operations(app):
        if (method, path) in PUBLIC_OPERATIONS:
            continue
        response = anon.request(method, concrete(path))
        if response.status_code != 401:
            unprotected.append((method, path, response.status_code))
    assert unprotected == []


def test_the_public_routes_really_are_reachable_without_a_session(anon, app):
    """The other half of the rule: a path listed as public must not have
    quietly become protected, or first-run setup deadlocks -- no session can
    be obtained without a passcode, and no passcode set without a session."""
    for method, path in api_operations(app):
        if (method, path) not in PUBLIC_OPERATIONS:
            continue
        response = anon.request(method, concrete(path), json={})
        assert response.status_code != 401, (method, path)


def test_a_session_from_one_instance_is_not_valid_on_another(tmp_path, client):
    """Each instance generates its own signing secret, so a cookie minted by
    one is not accepted by another. This is what makes deleting the
    credentials file a real revocation."""
    from fastapi.testclient import TestClient
    from server.app import create_app
    from server.settings import Settings

    other = create_app(Settings.from_env({
        "PF_DATA_DIR": str(tmp_path / "other"),
        "PF_STATIC_DIR": str(tmp_path / "none")}))
    with TestClient(other) as second:
        second.post("/api/auth/passcode", json={"passcode": "second-app"})
        stolen = client.cookies.get("pf_session")
        second.cookies.set("pf_session", stolen)
        assert second.get("/api/budget").status_code == 401


@pytest.mark.parametrize("path", ["/api/transactions/999999",
                                  "/api/categories/No Such Category"])
def test_unknown_resources_are_404_not_500(client, path):
    method = "patch" if "categories" in path else "get"
    body = {"budget_treatment": "fixed"} if method == "patch" else None
    response = client.request(method.upper(), path, json=body)
    assert response.status_code == 404


def test_the_openapi_schema_is_served(client):
    """It is the client's contract and the only machine-readable description
    of these routes, so it must actually generate."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "personal-finance"


def test_no_route_handler_is_async(app):
    """A correctness requirement, not a style rule.

    FastAPI runs a sync handler and its sync dependencies on the same
    threadpool worker; an async handler runs on the event loop while its sync
    dependencies still run in the threadpool. sqlite3 connections are bound to
    the thread that created them, so an `async def` handler taking the `db`
    dependency raises "SQLite objects created in a thread can only be used in
    that same thread" on every request. This caught exactly that in the
    statement-upload routes, which were async for `await upload.read()`.

    Nothing in this app has anything to await -- parsing, SQLite and argon2
    are all blocking -- so the rule costs nothing to keep.
    """
    import inspect

    from server.app import PROTECTED_ROUTERS
    from server.routes import auth as auth_routes

    offenders = []
    for router in [auth_routes.router, *PROTECTED_ROUTERS]:
        for route in router.routes:
            if inspect.iscoroutinefunction(route.endpoint):
                offenders.append(f"{sorted(route.methods)} {route.path}")
    assert offenders == [], (
        "these handlers are async and will fail on the sqlite3 connection: "
        + ", ".join(offenders))
