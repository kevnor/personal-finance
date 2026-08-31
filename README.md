# personal-finance

A weekly-envelope budgeting app for one household. Bank and credit-card
statements are imported into SQLite, categorised by rule, and turned into a
daily spending allowance.

The design lives in
[`docs/superpowers/specs/2026-08-22-personal-finance-app-design.md`](docs/superpowers/specs/2026-08-22-personal-finance-app-design.md);
the data itself — where it comes from, what the columns mean, and why the
categorisation rules are shaped the way they are — is documented in
[`db/README.md`](db/README.md).

## Layout

| Path | What it is |
|---|---|
| `server/app.py` | FastAPI app: JSON API plus the built client |
| `server/routes/` | One module per resource |
| `server/security.py` | Passcode, sessions, rate limit |
| `server/settings.py` | Paths and timezone, from the environment |
| `server/cli.py` | `import`, `reconcile` and `budget` commands |
| `server/lib/importer.py` | The import step the CLI and API share |
| `server/lib/ingest/` | Statement readers; one module per source format |
| `server/lib/categorise.py` | Pure: description text in, category out |
| `server/lib/derive.py` | Splits an itemised row (a loan term) into its parts |
| `server/lib/budget.py` | The weekly-envelope engine |
| `server/lib/store.py` | Connections, migrations, transaction writes |
| `server/corrections.py` | Applies the household's one-off corrections |
| `server/lib/local.py` | Reads `data/local.json` — the household's own facts |
| `db/migrations/` | Numbered SQL migrations, applied in filename order |
| `client/` | React PWA |
| `client/src/sw.js` | Service worker; its rules live in `lib/swStrategy.js` |
| `docker/` | Dockerfile and compose file |
| `data/` | The live database — gitignored |
| `input/` | Drop-zone for statements — gitignored |

## Running it

Python 3.11 or newer. The CLI below needs nothing installed — ingest,
categorisation and the budget engine are pure stdlib. The HTTP server has
dependencies; see "The server".

```bash
# Drop the statement exports into input/, then:
python3 -m server.cli import

# Report an existing database without touching it:
python3 -m server.cli reconcile

# This week's envelope and today's allowance:
python3 -m server.cli budget
python3 -m server.cli budget --date 2026-07-15
```

`import` is additive and idempotent: re-running it, or re-importing a
statement whose period overlaps one already loaded, inserts nothing new. Row
identity is a content fingerprint plus an occurrence index, so a re-export
with the rows reordered is recognised, while two genuinely separate
same-day purchases of the same amount are both kept.

`reconcile` and `budget` open the database read-only, so their promise not to
write is enforced by SQLite rather than by good intentions.

### The server

```bash
pip install -e .
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Or with Docker, which builds the client and serves it from the same process:

```bash
docker compose -f docker/compose.yaml up --build
```

On first run there is no passcode. `GET /api/auth/status` reports
`configured: false`, and `POST /api/auth/passcode` sets one — that endpoint
closes permanently the moment a passcode exists, so an instance is claimed
once. Everything under `/api` except the four auth endpoints requires the
session cookie it hands back.

| Route | What it does |
|---|---|
| `GET /api/budget` | Today's allowance, the week's envelope, and the pools behind them |
| `GET`/`PUT /api/budget/config` | Savings target, income mode, week start — versioned |
| `GET /api/transactions` | History and, with `needs_review=true`, the review queue |
| `POST /api/transactions` | Hand entry, categorised by the same rules as an import |
| `POST /api/transactions/bulk` | Programmatic entry; all-or-nothing |
| `PATCH /api/transactions/{id}` | Recategorise, override treatment, annotate; `teach` writes a merchant rule |
| `GET`/`PATCH /api/categories` | Per-category budget treatment |
| `GET`/`POST /api/reimbursements` | What is owed, and settling it |
| `POST /api/imports/preview` | What uploading this statement would do — writes nothing |
| `POST /api/imports` | Commit the upload |

Interactive docs at `/docs`, schema at `/openapi.json`.

Configuration is environment variables, all optional: `PF_DATA_DIR`,
`PF_DB_PATH`, `PF_PASSCODE_FILE`, `PF_LOCAL_FILE` (see [Local
configuration](#local-configuration)), `PF_STATIC_DIR`, `PF_MIGRATIONS_DIR`,
`PF_TIMEZONE` (default `Europe/Oslo`), the four Entra variables
`PF_ENTRA_TENANT_ID`, `PF_ENTRA_CLIENT_ID`, `PF_ENTRA_CLIENT_SECRET` and
`PF_PUBLIC_ORIGIN` (see [Authentication](#authentication)), and
`PF_HTTPS_ONLY` — set that last
one only when something in front terminates TLS, since a `Secure` cookie sent
over plain HTTP is dropped by the browser and login then fails to stick.

### The client

```bash
cd client
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api` to `http://127.0.0.1:8000`, so run uvicorn
alongside it (override with `PF_API_ORIGIN`). In production one FastAPI
process serves both, and the client's same-origin `/api` paths work
unchanged — which is what keeps the session cookie working with no CORS
configuration anywhere.

Every screen reads the API. There is no fixture data left in the client, and
no second copy of any rule: the category a hand-entered row gets is decided
by the same `categorise` the importer runs, and the weekly figures come from
`/api/budget` rather than being recomputed in the browser. Where the client
does aggregate — per-day bars, the Stats page — it filters exactly as the
server's `_variable_spent` does, so the two agree.

Category names are English identifiers that rules key on; the interface is
Norwegian. `GET /api/categories` serves both a `name` and a `label`, and the
client displays the label while sending the name back. Keeping the mapping
server-side is deliberate: a table in the client would go stale the moment a
category was added, and go stale silently.

## Local configuration

Some of what this app needs to categorise correctly identifies the people
using it: a card account number, an employer's name, a payment to a named
person whose purpose no rule can infer. Those are facts about one household,
not about budgeting, so they are **not** in this repository. They live in one
gitignored file beside the database — `data/local.json`, on the same volume,
for the same reason the passcode is there rather than in the database.
`PF_LOCAL_FILE` moves it if something else owns that path — a mounted secret,
say — but the default keeps it on the volume the backup already covers.

Everything in it is optional, and a clone with no file at all runs fine: it
categorises by the built-in rules alone and applies no corrections, which is
the right behaviour for an instance with no household attached to it yet.

```json
{
  "rules": [
    { "pattern": "til\\s*:\\s*12345678901", "category": "Credit card payment" },
    { "pattern": "giro.*acme", "category": "Employer reimbursement", "needs_review": true }
  ],
  "recategorisations": [
    { "date": "2026-07-28", "description": "<the row's exact description>",
      "amount": -166.0, "category": "Gifts" }
  ],
  "reimbursements": [
    { "date": "2026-07-30", "description": "<the row's exact description>",
      "amount": -13990.0, "expected_from": "Acme AS", "note": "employer-paid phone" }
  ]
}
```

- **`rules`** are regexes tested *before* the built-in rules and *after*
  anything taught in the UI, because they are more specific than any generic
  rule can be — an account number matches one account and nothing else.
- **`recategorisations`** and **`reimbursements`** are corrections about one
  specific payment, keyed on that row's own content rather than its id (ids
  are assigned by insertion order and mean nothing across databases). They
  are re-applied on every import and are idempotent, because a correction
  that changes no amount cannot be noticed missing by the reconciliation
  invariant.

A malformed file raises rather than being ignored: silently continuing would
mean a household's corrections quietly stop being applied, which is the
failure this arrangement exists to prevent.

## Tests

```bash
python3 -m pip install -e . pytest httpx
python3 -m pytest -q

cd client && npm test
```

The suite is in three parts:

- **Structural tests**, which run everywhere. They use synthetic statements
  built by `server/test/fixtures/statements.py`, which writes real `.xlsx`
  files at test time from a readable table of rows. This is what covers the
  ingest invariants the spec calls the highest-value tests in the project:
  re-importing a file is a no-op, overlapping periods do not duplicate, two
  identical same-day purchases are both retained, and identity is scoped per
  account.
- **API contract tests**, driven through `fastapi.testclient`. The load-
  bearing one enumerates every route the app publishes and asserts each is
  either listed as public by design or answers 401 without a session, so a
  route added later is covered without anyone remembering to add it here.
- **Client tests**, under `client/src/test/`, run with vitest against a fake
  server. They cover the API wrapper's error handling, the auth gate's three
  states, the write paths — where a bug means bad data rather than a bad
  render: the sign on a hand-entered amount, a correction that teaches a
  rule, preview-before-commit on an upload — and the service worker's caching
  rules, which are the worst thing in a web app to get wrong, since a worker
  persists across reloads and keeps serving whatever it decided to keep.
- **Real-data tests**, which assert this dataset's own figures — 181 rows,
  net 14 084,24, the 48 counterparty values, the −13 288,75 loan term. The
  statements are gitignored, so these skip unless `input/` is populated.
  `pytest -rs` lists what skipped and why.

A golden-file regression suite (`server/test/fixtures/categorisation.json`)
pins the categorisation of every real transaction description. Because
`categorise.py` is pure, it needs no database and no I/O.

## Migrations

Migrations are applied in filename order and recorded by name with a content
checksum. Editing an applied migration is refused: it would reach a freshly
built database and never reach an existing one, and the two would diverge
silently. Add a new migration instead.

Numbers must stay contiguous — a gap is the same divergence hazard, since
migrations are skipped by name but ordered by filename. `004_reserved.sql`
holds a slot that was skipped during development; a test enforces the rule.

## Offline and installation

The client is a PWA: `manifest.webmanifest` plus a service worker registered
from the root, so it installs to a home screen and opens without a browser
chrome. Both need a **secure context** — service workers only register over
HTTPS or on `localhost`. Served as `http://192.168.1.x:8000` there is no
worker and no install prompt, which is why `tailscale serve` is part of the
design rather than a nicety.

What the worker caches, and why (the rules are one pure function,
`src/lib/swStrategy.js`, with its own tests):

| Request | Strategy |
|---|---|
| Navigations | Network first, cached shell behind it — a reload works with no signal |
| `/assets/*` | Cache first; Vite content-hashes them, so a URL's bytes never change |
| `GET /api/*` | Network first, last response as fallback — this is the offline promise |
| `/api/auth/*` | Never cached: a stale `authenticated: true` would show the app to someone the server has already stopped accepting |
| Writes | Never cached, never queued |

**Reads survive going offline; writes do not.** A write queue means conflict
resolution and a sync state machine, and worse, a user who believes an
expense was recorded when it was not. The app says so rather than hiding it:
offline it shows a standing notice, and a save fails with a message instead
of appearing to work.

One consequence worth knowing: because auth state is never cached, the app
falls back to a local note (`localStorage`) to decide it may open offline.
That is not an authentication decision and cannot be used as one — it only
unlocks data already in this browser's own cache, put there by an
authenticated session on this device. Every request still goes to the server,
and a session it no longer accepts comes back 401, which clears the note and
returns to the login screen.

## Hosting it privately

One Raspberry Pi on the home network, reached only by the household, with
Microsoft sign-in. That combination has exactly one hard constraint, and it
decides the whole shape of the deployment:

> **Entra will not accept an `http://` redirect URI, and browsers will not
> register a service worker outside a secure context.** `http://192.168.1.50:8000`
> fails both. Private hosting therefore still needs real HTTPS on a hostname
> with a certificate the browser already trusts — it does *not* need the app
> to be reachable from the internet.

Those are different things, and the difference is what makes this work.
Entra never connects to the Pi. The **browser** does the redirecting, and the
**Pi** makes its own outbound call to Microsoft to exchange the code. So the
sign-in works perfectly well against a host that only exists on your own
network — as long as the browser can reach it over trusted TLS.

Sign-in does need the Pi to have working outbound internet. When it does not,
Entra sign-in fails with a 503 that says so, and the passcode is the way in —
which is what it is there for.

### Tailscale (recommended)

```bash
tailscale serve --bg 8000
tailscale serve status      # prints the https://<machine>.<tailnet>.ts.net URL
```

Tailscale provisions a genuine Let's Encrypt certificate for that hostname and
terminates TLS itself. The name resolves publicly but only *routes* inside
your tailnet, so the Pi stays unreachable from the internet while the browser
gets exactly the trusted HTTPS both Entra and the service worker require.
Nothing to renew, no certificate to install on each device, no ports opened on
the router — and it keeps working away from home, which for an app you check
in a shop is the point rather than a bonus.

Set `PF_PUBLIC_ORIGIN` to that URL, and register it plus
`/api/auth/entra/callback` as the redirect URI.

### Your own domain on the LAN

If you would rather not put Tailscale on each device, and you have a domain
whose DNS you control:

1. Point `finance.yourdomain.com` at the Pi's **private** address
   (`A 192.168.1.50`). A private address in public DNS is unroutable from the
   internet, so this publishes a name, not a service.
2. Have Caddy obtain the certificate over the **DNS-01** challenge, which
   proves the domain by writing a DNS record rather than by accepting an
   inbound connection — so still no ports open. It needs an API token for
   your DNS provider, on the Pi.

```caddyfile
finance.yourdomain.com {
    tls { dns cloudflare {env.CF_API_TOKEN} }
    reverse_proxy 127.0.0.1:8000
}
```

Two things to know before choosing this: it only works while you are on the
home network, and many routers refuse public DNS answers that point at
private addresses ("DNS rebinding protection"), which breaks resolution until
you add a local override. Neither applies to the Tailscale route.

### Either way

In `docker/compose.yaml`, set `PF_HTTPS_ONLY: "1"` once TLS is actually
terminated in front — the proxy is then the only thing that can reach the app
at all, since the published port is bound to loopback — and
`PF_PUBLIC_ORIGIN` to the HTTPS origin above if Entra is configured. The app
itself needs no proxy awareness: it builds no absolute URLs from the request,
takes the redirect URI from `PF_PUBLIC_ORIGIN`, and decides the cookie's
`Secure` flag from `PF_HTTPS_ONLY` rather than from the scheme it sees.

The login rate limit does read one thing from the proxy. Behind any of these,
every request arrives over loopback, so `request.client.host` is `127.0.0.1`
for every caller and limiting on it would give the whole network one shared
budget — which, once spent, locks the household out along with whoever spent
it. `_client_key` in `routes/auth.py` reads the real address from
`X-Forwarded-For` (rightmost entry) or `Cf-Connecting-Ip`, and only when the
direct connection is loopback, so nothing reachable from the network can
claim an address it does not have. A proxy that sets neither falls back to one
shared bucket — coarse, but the callers who can reach it are already only the
household.

### Not exposing it publicly

Deliberately undocumented. The threat model below assumes the network
boundary does the real work; put this on the open internet and a short
passcode and one Entra tenant become the only boundary, in front of every
scanner on it. Entra with **Assignment required** would carry most of that
weight, but the honest answer is that nothing here has been hardened for it,
so the guidance is the private routes above.

## Authentication

Two ways in, and they are not equals. Microsoft Entra ID is the normal one;
the passcode stays as a break-glass route for when it cannot be reached.

Nothing here is required. With none of the four Entra variables set —
which is what a fresh clone is — the app is passcode-only and behaves exactly
as it did before any of this existed. Setting *some* of them raises at
startup rather than quietly falling back: an instance meant to federate but
silently not doing so still shows a working login screen, and nobody finds
out until they go looking for the sign-in that was supposed to be enforced.

### Registering the app

In the Entra portal, App registrations → New registration:

1. **Supported account types: "Accounts in this organizational directory
   only" (single tenant).** This is the setting that matters most. Multitenant
   means every Microsoft account in the world can present a valid token for
   your app. The server checks the `tid` claim against your tenant and
   refuses anything else, so a mis-set registration fails closed rather than
   open — but set it correctly as well, rather than relying on that check
   alone.
2. **Redirect URI**, of type Web: `https://<your-host>/api/auth/entra/callback`.
   It must match `PF_PUBLIC_ORIGIN` exactly.
3. **Certificates & secrets → New client secret.** That value is
   `PF_ENTRA_CLIENT_SECRET`. Entra shows it once. Note its expiry: when it
   lapses, sign-in fails and the passcode is how you get back in to fix it.

Then, in Enterprise applications → your app → Properties, set **Assignment
required = Yes**, and add the household under Users and groups. That is where
user management actually happens: adding and removing people is a click in
Entra, not a change to this repository. Entra ID Free assigns *users*
individually; assigning a *group* needs P1, which at household scale is a
distinction without a difference.

```bash
PF_ENTRA_TENANT_ID=<directory (tenant) ID>
PF_ENTRA_CLIENT_ID=<application (client) ID>
PF_ENTRA_CLIENT_SECRET=<the secret value, not its ID>
PF_PUBLIC_ORIGIN=https://finance.your-tailnet.ts.net
```

`PF_PUBLIC_ORIGIN` cannot be inferred from the request: behind `tailscale
serve` the app sees plain HTTP on localhost, so a redirect built from what
the request says would send the browser somewhere it cannot reach — and Entra
would reject it for not matching the registration. Tailscale is otherwise no
obstacle: Entra never calls this server, the browser does, so a tailnet-only
hostname is fine. The server needs outbound access to
`login.microsoftonline.com`, nothing inbound.

### How a session works

The app is a confidential client. It exchanges the authorization code for
tokens over its own TLS connection to Microsoft, and no Entra token ever
reaches the browser — what the browser gets is the same signed, httpOnly
cookie the passcode path issues. That is what keeps the service worker and
the offline gate unchanged.

An Entra session lasts **one hour**, against the passcode's 30 days, and the
difference is the whole point of federating: removing somebody in Entra has
to actually lock them out, and a 30-day cookie would leave them a month of
access after the click. When the hour lapses the client redirects once
through Entra with `prompt=none` — no typing, but a brief full-page
navigation. If the directory session is still live and the user is still
assigned, they land back where they were. If they have been removed, Entra
answers `login_required` and they get the login screen.

The standing cost of keeping the passcode: a passcode session is still 30
days and Entra governs nothing about it, so revoking someone in the directory
does not touch a session they obtained that way. Rotating the signing secret
(delete the credentials file, set a new passcode) is what revokes those.

Sign-in requires a passcode to already be set, because the credentials file
is where the signing secret lives. The ordering is deliberate rather than
incidental: an instance that federated before it had a passcode would have no
way in when the directory is unreachable, which is the one situation
break-glass exists for.

### What Entra ID Free does not give you

Conditional Access (IP or device restrictions), group-based app assignment,
dynamic groups and self-service password reset are all P1 features. Of those,
only group-based assignment is even adjacent to this app, and assigning a
household individually costs nothing. MFA is available on Free through
security defaults, and is worth turning on.

## Security

One passcode, argon2-hashed, in a file on the data volume beside the database
rather than inside it — so a database restored from backup does not bring an
old passcode with it. Sessions are stateless signed cookies (httpOnly,
SameSite=Lax, `Secure` when `PF_HTTPS_ONLY` is set, 30 days). Login is
rate-limited per client address. Optionally federated to Entra ID; see
[Authentication](#authentication) above for what that changes, including the
one-hour session and what it does *not* revoke.

Stated plainly, unchanged from the spec: this stops a guest's laptop or an
IoT device on the same wifi from browsing the user's finances. It is not
hardening against a determined attacker already inside the network — the
network boundary does the real work. `logout` clears the cookie rather than
revoking the token; to revoke every session, delete the credentials file and
set a new passcode, which rotates the signing secret.

## Not built yet

The bank fetch, deliberately deferred — see "Deferred: bank integration" in
the spec. The ingest pipeline is shaped so it lands as a fourth source.
