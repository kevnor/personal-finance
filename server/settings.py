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
class EntraSettings:
    """An Entra ID app registration, when one is configured.

    Present only when all four variables are set. Partial configuration
    raises rather than degrading to passcode-only: an instance that was meant
    to federate but silently did not would still show a working login screen,
    and nobody would find out until they went looking for the sign-in that
    was supposed to be enforced.
    """
    tenant_id: str
    client_id: str
    client_secret: str
    # The origin the browser reaches this app on, used to build the redirect
    # URI. It cannot be inferred from the request: behind `tailscale serve`
    # the app sees a plain-http request on localhost, so a redirect built
    # from the request would send the browser somewhere it cannot reach, and
    # Entra would reject it for not matching the registration.
    public_origin: str

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_origin}/api/auth/entra/callback"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    migrations_dir: Path
    passcode_file: Path
    local_file: Path
    static_dir: Path
    timezone: ZoneInfo
    # None when no app registration is configured, which is the state a fresh
    # clone ships in: the passcode alone then governs access, exactly as
    # before this existed.
    entra: EntraSettings | None
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
            # Household-specific rules and corrections; see server/lib/local.py.
            local_file=Path(env.get("PF_LOCAL_FILE", data_dir / "local.json")),
            static_dir=Path(
                env.get("PF_STATIC_DIR", ROOT / "client" / "dist")),
            timezone=ZoneInfo(env.get("PF_TIMEZONE", DEFAULT_TIMEZONE)),
            entra=_entra_from_env(env),
            https_only=env.get("PF_HTTPS_ONLY", "").lower()
            in {"1", "true", "yes"},
        )


ENTRA_VARIABLES = ("PF_ENTRA_TENANT_ID", "PF_ENTRA_CLIENT_ID",
                   "PF_ENTRA_CLIENT_SECRET", "PF_PUBLIC_ORIGIN")


def _entra_from_env(env) -> EntraSettings | None:
    present = {name: env[name].strip()
               for name in ENTRA_VARIABLES if env.get(name, "").strip()}
    if not present:
        return None
    missing = [name for name in ENTRA_VARIABLES if name not in present]
    if missing:
        raise ValueError(
            "Entra is partly configured, which would silently fall back to"
            f" passcode-only. Set {', '.join(missing)}, or unset"
            f" {', '.join(present)}.")

    origin = present["PF_PUBLIC_ORIGIN"].rstrip("/")
    # Entra refuses to register a non-HTTPS redirect URI except on localhost,
    # so an http:// origin here produces a registration that cannot match and
    # a failure at sign-in rather than at startup. Caught at startup instead.
    if not (origin.startswith("https://")
            or origin.startswith("http://localhost")
            or origin.startswith("http://127.0.0.1")):
        raise ValueError(
            f"PF_PUBLIC_ORIGIN must be https:// (or localhost): {origin!r}."
            " Entra refuses to register an http:// redirect URI, so a plain"
            " LAN address like http://192.168.1.50:8000 cannot be used even"
            " for a private deployment -- put a TLS-terminating proxy in"
            " front and use its hostname. See README \"Hosting it"
            " privately\".")

    return EntraSettings(tenant_id=present["PF_ENTRA_TENANT_ID"],
                         client_id=present["PF_ENTRA_CLIENT_ID"],
                         client_secret=present["PF_ENTRA_CLIENT_SECRET"],
                         public_origin=origin)
