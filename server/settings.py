"""Where the app's files live and what timezone it thinks in.

Read from the environment so the container can point them at the mounted
volume without a code change, and so tests can point them at a tmp_path.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

# The app is one household's, in Norway, and the week boundary it draws is a
# local-midnight one. Under UTC on a server west of Oslo, "today" would flip
# an hour or two late and a Sunday-night purchase could land in the wrong
# week's envelope -- a silent error in the number the whole app is about.
DEFAULT_TIMEZONE = "Europe/Oslo"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    migrations_dir: Path
    passcode_file: Path
    static_dir: Path
    timezone: ZoneInfo
    # Set only when the app is served over HTTPS, which is what lets the
    # session cookie carry `Secure`. Local development over plain HTTP on
    # localhost must not set it, or the browser drops the cookie and login
    # silently fails to stick.
    https_only: bool

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        data_dir = Path(env.get("PF_DATA_DIR", ROOT / "data"))
        return cls(
            data_dir=data_dir,
            db_path=Path(env.get("PF_DB_PATH", data_dir / "transactions.db")),
            migrations_dir=Path(
                env.get("PF_MIGRATIONS_DIR", ROOT / "db" / "migrations")),
            passcode_file=Path(
                env.get("PF_PASSCODE_FILE", data_dir / "passcode.json")),
            static_dir=Path(
                env.get("PF_STATIC_DIR", ROOT / "client" / "dist")),
            timezone=ZoneInfo(env.get("PF_TIMEZONE", DEFAULT_TIMEZONE)),
            https_only=env.get("PF_HTTPS_ONLY", "").lower()
            in {"1", "true", "yes"},
        )
