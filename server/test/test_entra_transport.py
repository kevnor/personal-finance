"""The Entra client only ever talks https (or localhost, for a fake in tests).

The URLs it calls come from the tenant id and from Microsoft's discovery
document. urlopen also speaks file:// and ftp://, so nothing but this check
stands between a tampered document and a local file read.
"""
import urllib.request

import pytest

from server import entra


@pytest.fixture
def client(monkeypatch):
    def must_not_be_reached(*args, **kwargs):
        raise AssertionError("urlopen was called for a URL that must be refused")

    monkeypatch.setattr(urllib.request, "urlopen", must_not_be_reached)
    # _request uses no instance state, so skip __init__ and its configuration.
    return object.__new__(entra.Client)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
    "http://evil.example/token",
    "http://localhost.evil.example/token",
    "http://127.0.0.1.evil.example/token",
])
def test_request_refuses_urls_that_are_not_https_or_localhost(client, url):
    with pytest.raises(entra.EntraError, match="refusing"):
        client._request(urllib.request.Request(url))
