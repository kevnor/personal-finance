"""FastAPI application: the JSON API and the built client, one process.

One container, per the spec: a Node stage compiles the PWA to static assets
and this serves both them and the API. That is what keeps the client
same-origin, which in turn is why there is no CORS configuration here and no
cross-site token handling -- the session cookie just works.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server import security
from server.deps import require_session
from server.lib import budget, categorise, store
from server.routes import (auth, budget as budget_routes, categories, imports,
                           reimbursements, transactions)
from server.settings import Settings

# Accounts the schema is seeded with. The same list `cli.SOURCES` implies,
# stated directly here because the API has no notion of source filenames.
SEED_ACCOUNTS = [("Bankkonto", "bank"), ("Kredittkort", "credit_card")]

# Routers that require a session. Everything except auth, which cannot: the
# client needs /api/auth/status before it can know whether to show a login
# screen, and /api/auth/login is how a session is obtained in the first place.
PROTECTED_ROUTERS = [
    transactions.router,
    budget_routes.router,
    categories.router,
    reimbursements.router,
    imports.router,
]


def prepare_database(settings: Settings) -> None:
    """Bring the database up to date before the first request.

    Migrating at startup rather than on demand means a request never races a
    schema change, and a fresh volume produces a working app rather than a
    500 on the first query. `seed_default_config` is what stops the budget
    engine raising on a database with no configuration -- the spec's cold
    start.
    """
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = store.connect(settings.db_path)
    try:
        # Same order as `cli.build`: refuse a legacy database before altering
        # its schema, rather than upgrading it on the way to a refusal.
        store.require_fingerprinted_imports(con)
        store.migrate(con, settings.migrations_dir)
        store.seed_reference_data(
            con, categorise.CATEGORIES, categorise.TREATMENTS, SEED_ACCOUNTS)
        budget.seed_default_config(con)
    finally:
        con.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    A factory rather than a module-level singleton so tests can point it at a
    tmp_path, and so the container can configure it from the environment
    without either reaching into module globals.
    """
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        prepare_database(app.state.settings)
        yield

    app = FastAPI(
        title="personal-finance",
        summary="Weekly-envelope budgeting for one household.",
        version="0.1.0",
        lifespan=lifespan)

    app.state.settings = settings
    app.state.passcodes = security.PasscodeStore(settings.passcode_file)
    app.state.rate_limiter = security.RateLimiter()

    app.include_router(auth.router)
    for router in PROTECTED_ROUTERS:
        # The session check is attached to the router, not to each route, so
        # a route added later is protected by default. Forgetting a decorator
        # is a silent hole; forgetting to remove one is a visible 401.
        app.include_router(router, dependencies=[Depends(require_session)])

    _mount_client(app, settings.static_dir)
    return app


def _mount_client(app: FastAPI, static_dir: Path) -> None:
    """Serve the built PWA, if it has been built.

    Absent in development (the client runs on Vite's own dev server) and in
    tests, so a missing directory is normal rather than an error. Unknown
    paths fall back to index.html because the client routes in the browser:
    without the fallback, reloading on any screen but Home would 404.
    """
    if not static_dir.is_dir():
        return

    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (static_dir / path).resolve()
        # Confined to the static directory: `path` is caller-controlled, and
        # without this check `../../data/passcode.json` would be served.
        if (path and candidate.is_file()
                and candidate.is_relative_to(static_dir.resolve())):
            return FileResponse(candidate)
        return FileResponse(index)


# The ASGI entrypoint: `uvicorn server.app:app --host 0.0.0.0 --port 8000`.
app = create_app()
