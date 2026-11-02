# Backtest Lab

Build rules like "Buy 1 lot if the market is up 1%, sell 1 lot if down 1%", run them on real price history (fills at the close), and get a dashboard: cash/net-worth extremes, profit and loss, drawdowns, best/worst stretches, holding-window analysis, charge sensitivity, monthly heatmap, trade log.

## Code, config and data are separate
| Where | What |
|---|---|
| `backend/`, `frontend/` | Code only |
| `config/*.json` | Tunable behaviour: strategy params, indicator labels, analysis grids, periods, CSV limits, OTP rules, UI defaults/thresholds, example rule sets, currency |
| `.env` | Secrets and infrastructure: `DATABASE_URL`, `SECRET_KEY`, `ADMIN_MOBILES`, `OTP_DEV_CODE`, `REDIS_URL`, ... (see `.env.example`). Git-ignored |
| Database (Postgres) | All real data: `price_bars`, `instruments`, `users`, `sessions`, `otp_challenges` (schema in `backend/app/db.py`, `backend/schema.sql`) |
| `examples/` | `prices_template.csv`: header only, no numbers |

The dashboard shows only what is computed from rows in `price_bars`. With an empty database it says so.

## Run locally
Needs Python 3.11+ and Node 22.
```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cp .env.example .env            # defaults to SQLite; fill SECRET_KEY, ADMIN_MOBILES, OTP_DEV_CODE
mkdir -p var
cd frontend && npm ci && npm run build && cd ../backend
AUTO_CREATE_SCHEMA=true ../.venv/bin/uvicorn app.main:create_app --factory --port 8123   # http://localhost:8123
```
Frontend dev server: `cd frontend && npm run dev` (proxies `/api` to :8123).

Tests and lint: `cd backend && ../.venv/bin/pytest && ../.venv/bin/ruff check app tests`

Endpoints for operations: `/api/health` (process up), `/api/ready` (database and Redis reachable), `/metrics` (Prometheus).

## Login
Mobile number + OTP. Numbers in `ADMIN_MOBILES` get the admin role; everyone else is a trader.
`AUTH_MODE=dev` accepts one shared code, `OTP_DEV_CODE`, and sends no SMS. That is fine for a private beta if you:
- set `APP_ENV=production` (refuses guessable codes and short secret keys),
- keep the code private and set `ALLOWED_MOBILES` so only invited numbers can sign in.

Brute force is limited per number (`config/auth.json`), per IP (shared via `REDIS_URL` when set), and globally (`otp_global_failed_per_hour`; when it trips, sign-in pauses for everyone for up to an hour).
For real SMS, implement `OtpSender` in `backend/app/auth/otp.py` and return it from `build_sender()` for `AUTH_MODE=prod`.

## Production
One VM running Docker: `app` (FastAPI + built frontend), `caddy` (automatic HTTPS, blocks `/metrics`), `prometheus`, `grafana` (at `https://<domain>/grafana`) and `node-exporter`. Postgres and Redis/Valkey are managed services. Files are in `deploy/`.

CircleCI (`.circleci/config.yml`): on every push it lints, tests and builds the frontend and the Docker image. On `main` it also pushes the image to `ghcr.io/<owner>/algo-trading` and deploys over SSH with `deploy/deploy.sh`, which waits for `/api/ready` and rolls back if the check fails.

**First-time server setup** (Ubuntu 22.04+):
```bash
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER   # then log out and back in
sudo mkdir -p /opt/algo-trading && sudo chown $USER /opt/algo-trading
# create /opt/algo-trading/.env from deploy/.env.example (secrets live only here and in CircleCI)
```
Point your domain's A record at the server and open ports 80 and 443.

**CircleCI contexts:** `ghcr` (`GHCR_USER`, `GHCR_TOKEN` with write:packages), `production` (`DEPLOY_HOST`, `DEPLOY_USER`). Add the deploy SSH key under Project Settings → SSH Keys and put its fingerprint in `deploy_ssh_fingerprint` in the config.

**Monitoring:** Grafana loads Prometheus as a data source and the "Backtest Lab" dashboard automatically. Alert rules are in `deploy/prometheus/alerts.yml`; they show as firing in Grafana/Prometheus but nothing notifies you until you add a contact point.

## Loading real data
Sign in as admin > Admin > upload a CSV with `date, open, high, low, close` (download the template there). Replace or merge by date. Numbers like `1,234.50` are accepted.

## Extending
- Strategy: add a class in `domain/strategies/builtin.py` and its metadata in `config/strategies.json`.
- Indicator for the rule builder: add an `Operand` in `domain/rules.py` and its label in `config/rule_builder.json`.
- Chart: write a `ChartPanel` and list it in `frontend/src/charts/index.ts`.
- Storage: implement `PriceRepository`.

