"""The credentials file holds the session-signing secret, so it must be private
from the moment it exists, not only after a later chmod."""
import os
import stat

from server import security


def test_credentials_file_is_created_private(tmp_path, monkeypatch):
    # chmod is neutralised: if the file is only made private by a chmod after
    # it was written, then under the default umask the secret sits readable by
    # others in between. It has to be created 0600 in the first place.
    monkeypatch.setattr(os, "chmod", lambda *args, **kwargs: None)
    previous = os.umask(0o022)
    try:
        store = security.PasscodeStore(tmp_path / "passcode.json")
        store.set_passcode("a-long-enough-passcode")
    finally:
        os.umask(previous)

    mode = stat.S_IMODE((tmp_path / "passcode.json").stat().st_mode)
    assert mode == 0o600
