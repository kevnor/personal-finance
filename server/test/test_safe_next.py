"""Where the browser is sent after sign-in must be a path on this origin.

`/\\evil.example` is the awkward one: it starts with a single slash, so a
check for `//` lets it through, but browsers treat a backslash as a slash and
read it as `//evil.example`.
"""
import pytest

from server.routes.auth import _safe_next


@pytest.mark.parametrize("candidate", [
    "http://evil.example",
    "https://evil.example/x",
    "//evil.example",
    "evil.example",
    "\\evil.example",
    "/\\evil.example",
    "/\\\\evil.example",
    "/\t/evil.example",
    "/\n/evil.example",
    "/\r/evil.example",
    "/\x00/evil.example",
    "",
    None,
])
def test_anything_that_is_not_a_plain_same_origin_path_falls_back_to_root(
        candidate):
    assert _safe_next(candidate) == "/"


@pytest.mark.parametrize("candidate", [
    "/",
    "/history",
    "/review?week=2026-10-12",
    "/a/b#section",
])
def test_same_origin_paths_are_kept(candidate):
    assert _safe_next(candidate) == candidate
