"""Shared fixtures for the HTTP API tests.

Every fixture here points the app at a tmp_path: its own database, its own
credentials file, no static directory. Nothing touches the real `data/`.
"""
from __future__ import annotations

import pytest

from server.app import create_app
from server.settings import Settings

PASSCODE = "correct-horse"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings.from_env({
        "PF_DATA_DIR": str(tmp_path / "data"),
        "PF_STATIC_DIR": str(tmp_path / "no-client-build"),
        "PF_TIMEZONE": "Europe/Oslo",
    })


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def anon(app):
    """A client with no session.

    The TestClient context manager is what runs the lifespan handler, and the
    lifespan is what migrates the database -- so a fixture that skipped it
    would test an app whose schema does not exist.
    """
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(anon):
    """A signed-in client, with the passcode set as it would be on first run."""
    response = anon.post("/api/auth/passcode", json={"passcode": PASSCODE})
    assert response.status_code == 201, response.text
    return anon


@pytest.fixture
def con(settings):
    """A direct connection to the same database the app is using.

    For arranging state a test needs and for checking what a request actually
    wrote, rather than trusting the response body to report it.
    """
    from server.lib import store
    connection = store.connect(settings.db_path)
    yield connection
    connection.close()
