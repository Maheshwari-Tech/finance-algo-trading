# Strategic Trader

**Test a trading idea on real price history, and check every rupee of the result yourself.**

## Business Goal

Every trader has ideas: *"buy when the market is up 1%, sell when it's down 1%"*, *"buy the dip below the 100-day average"*, *"follow the golden cross"*. Most never find out whether the idea would have made money, and the tools that claim to tell them show a single return figure that no one can check.

Strategic Trader turns an idea into an answer you can trust:

- **Write the rule in plain words, not code.** Pick an indicator, a comparison and a number. The rule reads back as a sentence: *"Buy 1 lot when 1-day change % > 1"*.
- **See what the rule would do before risking a rupee.** *Test a rule* marks every day it would act, with the actual values that triggered it.
- **Run it with real money settings.** Starting capital, lots, charges, selling before buying, a maximum position and a "cash can't go below 0" rule all work the way a broker account does.
- **Trust the numbers.** Every order is listed with cash before and after, the reason and the values. Profit is broken into realised + open − charges, with average-cost accounting like your broker's P&L screen. The platform re-checks its own arithmetic on every run and shows ✓ or ✗.
- **Keep it honest.** Each strategy is run against its exact inverse; the two always add up to minus the charges, never a free profit. If a limit breaks the mirror, the page says so.
- **Compare and keep your ideas.** Save rule sets to your account and compare any two side by side on the same prices and settings.

**Who it's for:** active traders who want evidence before conviction, advisors who need to show clients exactly how a result was reached, and trading educators who want students to see cause and effect order by order.

**Why it wins:** other backtesters ask you to trust a number. Strategic Trader shows you the ledger.

## Demo

Screenshots will be added after the first production deployment (taken from the live app, not mock-ups).

Pages: **Test a rule** · **Strategy** (summary, takeaways, charts, weekly and monthly overviews, daily transactions, orders, weekly view, trades, checks, all statistics; jump to any section and show only the ones you want) · **Compare** · **Feedback** · **Admin** (price data, all feedback).

## How to use this repository

**You need:** Python 3.11+, Node 22+ (26 recommended), and a Postgres database (or SQLite for a quick local try).

```bash
git clone https://github.com/Maheshwari-Tech/finance-algo-trading.git
cd finance-algo-trading
cp .env.example .env          # fill in DATABASE_URL, SECRET_KEY, ADMIN_MOBILES, OTP_DEV_CODE (see comments in the file)
./scripts/verify.sh           # installs everything, runs lint, tests, frontend build, boots the app and clicks through it
./scripts/dev.sh              # starts backend + frontend for local testing
```

`dev.sh` prints everything you need:

| What | Where |
|---|---|
| Website (hot reload) | http://localhost:5173 |
| API | http://localhost:8123/api |
| Swagger | http://localhost:8123/docs |
| Sign in | first number in `ADMIN_MOBILES` and `OTP_DEV_CODE` from `.env` |

Test the API from the terminal:
```bash
export TOKEN=$(./scripts/api-login.sh --quiet)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8123/api/symbols
```

**Load prices:** on first start, when the database has no prices, the bundled NIFTY 50 daily history (`examples/nifty50.csv`, ~5 years from Yahoo Finance `^NSEI`, unadjusted) is loaded automatically, so every user sees it after signing in. To use other data, sign in as admin → Admin → upload a CSV with `date, open, high, low, close` (template on that page). Replace or merge by date. Change or turn off the default in `config/data.json` (`default_dataset`; set it to `null` to start empty). It is only loaded when no instrument exists, so existing data is never overwritten.

**Run the checks yourself:**
```bash
cd backend && ../.venv/bin/pytest && ../.venv/bin/ruff check app tests
cd ../frontend && npm run build
```

**Repository layout**

| Where | What |
|---|---|
| `backend/` | FastAPI app: `domain/` (pure calculation), `api/`, `auth/`, `data/`, `services/` |
| `frontend/` | TypeScript single-page app (Vite, Chart.js) |
| `config/*.json` | Tunable behaviour: strategy parameters, rule-builder labels and help, periods, CSV and sign-in limits, UI defaults, example rule sets |
| `.env` | Secrets and infrastructure only. Git-ignored |
| `deploy/` | Production stack: Compose, Caddy, Prometheus, Grafana, deploy and server-setup scripts |
| `scripts/` | `dev.sh`, `verify.sh`, `api-login.sh`, `export-openapi.sh` |
| `docs/` | Architecture, API, decisions, runbook |

**Extending:** a new built-in strategy is a class in `backend/app/domain/strategies/builtin.py` plus its metadata in `config/strategies.json`. A new rule-builder indicator is an `Operand` in `backend/app/domain/rules.py` plus its label and help in `config/rule_builder.json`. A new chart is a `ChartPanel` listed in `frontend/src/charts/index.ts`.

## Architecture

[docs/architecture.md](docs/architecture.md): system context, containers, code structure, request flows, how a backtest is computed, data model, security, observability, build and deploy, with diagrams.

## Swagger

- Interactive: **`/docs`** on a running app in development (`./scripts/dev.sh` → http://localhost:8123/docs). Click **Authorize** and paste a token from `./scripts/api-login.sh`. Hidden in production (`APP_ENV=production`).
- Spec file: `docs/openapi.json`, regenerated with `./scripts/export-openapi.sh`.
- Written reference with curl examples: [docs/api.md](docs/api.md).

## Key design decisions

[docs/decisions.md](docs/decisions.md): average-cost P&L, fills at the close, returns on money actually invested, the inverse strategy, the cash rule, rule firing, rounding, deployment and sign-in choices, each with who decided and why.

## Change log

[CHANGELOG.md](CHANGELOG.md)

## Operational and Production

One VM runs Docker Compose: `app` (API + website), `caddy` (HTTPS), `prometheus`, `grafana` and `node-exporter`. CircleCI tests every push and auto-deploys green pushes to `main`, rolling back if the new version doesn't come up. Details: [architecture § 10](docs/architecture.md#10-build-and-deploy).

**Backend on Azure Kubernetes Service:** a backend-only image (`Dockerfile.api`), a Helm chart (`deploy/helm/strategic-trader`), Application Gateway for Containers and a GitHub Actions pipeline. Step-by-step setup: [docs/deploy-azure.md](docs/deploy-azure.md).

**Logs**
- App logs go to stdout, as JSON in production. On the server: `docker compose -f docker-compose.prod.yml logs -f app` in `/opt/algo-trading`.
- Kept by Docker, 5 × 20 MB per container.

**Grafana dashboard**
- `https://<your-domain>/grafana` → folder "Backtest Lab". *The production domain isn't set up yet; this link becomes real after the first deployment.*
- Shows traffic, errors, latency, backtests, sign-ins, uploads, memory, and server CPU, memory and disk. Alert rules: `deploy/prometheus/alerts.yml`.
- No notification channel yet: add a Grafana contact point to get alerts by email, Telegram or Slack.

**External dependencies**

| Kind | Dependency | Used for | If it's down |
|---|---|---|---|
| Database | **Aiven Postgres** (`DATABASE_URL`) | All data: prices, users, sessions, saved strategies, feedback | App not ready (`/api/ready` 503); alert `DatabaseUnreachable` |
| Database | **Aiven Valkey** (`REDIS_URL`, optional) | Per-IP sign-in rate limit, shared across containers | App keeps working; rate limit fails open (logged) |
| Queues | **None** | Backtests run inside the request | – |
| Service | **GitHub** | Source code | No new deploys |
| Service | **CircleCI** | Tests, builds, deploys | No new deploys; running app unaffected |
| Service | **GitHub Container Registry (GHCR)** | Docker images `ghcr.io/maheshwari-tech/finance-algo-trading` | No new deploys or rollbacks to images not on the server |
| Service | **Let's Encrypt** (via Caddy) | HTTPS certificates | Renewal retries; current certificate valid for weeks |
| Service | **Google Fonts** (loaded by the browser) | Inter and JetBrains Mono fonts | Site falls back to system fonts |
| Service | SMS provider | **None yet**: sign-in uses a shared access code (`AUTH_MODE=dev`) | – |

**Runbook**

[docs/runbook.md](docs/runbook.md): deploy and roll back, what to do for each alert, rotating the access code and credentials, a paused sign-in, Valkey down, bad price data, certificates, backups.

**Production configuration**
- Server secrets: `/opt/algo-trading/.env` (template: `deploy/.env.example`).
- CI secrets: CircleCI contexts `ghcr` (`GHCR_USER`, `GHCR_TOKEN`) and `production` (`DEPLOY_HOST`, `DEPLOY_USER`), plus the deploy SSH key.
- First-time server setup: `deploy/setup-server.sh`.
