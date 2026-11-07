# Runbook

What to do when operating Strategic Trader in production. Server paths assume the layout from `deploy/setup-server.sh`: the stack lives in `/opt/algo-trading` and runs as the `deploy` user.

```bash
ssh deploy@<server>
cd /opt/algo-trading
alias dc='docker compose -f docker-compose.prod.yml'
```

Related: [Architecture](architecture.md) · [API](api.md) · [Decisions](decisions.md)

---

## Quick reference

| Need | Command / place |
|---|---|
| Is it up? | `curl -fsS https://<domain>/api/ready` |
| Container status | `dc ps` |
| App logs (live) | `dc logs -f --tail=200 app` |
| Errors only | `dc logs app --since=1h \| grep '"level": "ERROR"'` |
| Restart the app | `dc restart app` |
| Which version is running | `grep APP_IMAGE .env` (the tag is the git commit) |
| Dashboards | `https://<domain>/grafana` → folder "Backtest Lab" (user `admin`, password = `GRAFANA_ADMIN_PASSWORD` in the server `.env`) |
| Prometheus (no public URL) | `ssh -L 9090:localhost:9090 deploy@<server>` then `dc exec prometheus wget -qO- localhost:9090/api/v1/alerts` |
| Server `.env` | `/opt/algo-trading/.env` (chmod 600, never in git) |

---

## Deploy

Normal path: merge or push to `main`. CircleCI tests, builds, pushes the image to GHCR and runs `deploy.sh <image>:<sha>` on the server. `deploy.sh` waits for `https://<domain>/api/ready` and **rolls back automatically** if it does not answer.

Deploy a specific version by hand:
```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github user> --password-stdin
./deploy.sh ghcr.io/maheshwari-tech/finance-algo-trading:<git sha>
```

## Roll back

```bash
grep APP_IMAGE .env                     # current
./deploy.sh ghcr.io/maheshwari-tech/finance-algo-trading:<previous good sha>
```
Previous shas: CircleCI pipeline history, or `docker images ghcr.io/maheshwari-tech/finance-algo-trading`.
Database schema changes are additive only (new tables), so rolling the app back does not need a database change.

---

## Alerts

| Alert | Meaning | First steps |
|---|---|---|
| **AppDown** | Prometheus cannot scrape the app for 2 min | `dc ps`; `dc logs --tail=200 app` (startup errors are usually a missing/invalid `.env` value: the message names it); `dc up -d app` |
| **DatabaseUnreachable** | `/api/ready` cannot reach Postgres for 2 min | Aiven console: service running? IP allowlist includes the server? Credentials rotated without updating `.env`? Then `dc restart app` |
| **HighErrorRate** | > 5% of requests return 5xx for 5 min | Logs for tracebacks; Grafana "Responses by status" and "Requests by route" to find the route; roll back if it started with a deploy |
| **SlowApi** | p95 latency > 1 s (excluding backtests/uploads) for 10 min | Database latency (Aiven metrics), host CPU/memory (Grafana "Server"), `dc stats` |
| **SlowBacktests** | p95 backtest > 10 s | Usually very long histories or the cash limit on (charge sensitivity reruns). Check "Backtest duration" and CPU; consider more CPU or a second app container |
| **FailedLoginSpike** | > 30 wrong codes in 15 min | Possible guessing of the shared code. Rotate `OTP_DEV_CODE` (below), consider setting `ALLOWED_MOBILES`; the global wrong-code cap will pause sign-in by itself |
| **DiskAlmostFull** | < 10% disk | `docker system df`; `docker image prune -af` (keeps running images); Prometheus keeps 30 days in its volume |
| **HighMemory** | > 90% memory for 10 min | `dc stats`; app is limited to 1 GB; restart the app; size up the VM if it recurs |

Alerts are visible in Grafana and Prometheus. A notification channel (email, Telegram, Slack) is **not configured yet**: add a Grafana contact point to receive them.

---

## Common situations

### "Sign-in is temporarily paused after too many wrong codes"
The global cap (`otp_global_failed_per_hour` in `config/auth.json`) was hit. It clears itself within an hour as old attempts age out. To clear immediately (Postgres):
```sql
UPDATE otp_challenges SET attempts = 0 WHERE created_at > now() - interval '1 hour';
```
If it was an attack, rotate the code first.

### Rotate the shared sign-in code
```bash
python3 -c "import secrets;print(f'{secrets.randbelow(10**6):06d}')"
nano .env            # OTP_DEV_CODE=<new>
dc up -d app         # recreates the container with the new value
```
Tell your users the new code. Existing sessions stay signed in.

### Sign everyone out
```sql
DELETE FROM sessions;
```

### Rotate database or Valkey credentials
1. Reset the password in the Aiven console.
2. Update `DATABASE_URL` / `REDIS_URL` in the server `.env` (and your local `.env`).
3. `dc up -d app`, then `curl https://<domain>/api/ready` should show `"database": "ok"` and `"redis": "ok"`.

### Rotate `SECRET_KEY`
Changing it makes outstanding sign-in codes invalid (they are hashed with it); sessions are unaffected. Generate with `python3 -c "import secrets;print(secrets.token_urlsafe(48))"`, update `.env`, `dc up -d app`.

### Valkey is down
Readiness shows `"redis": "degraded"` and the app keeps working: the per-IP limit allows requests (logged as a warning) while per-number and global limits in Postgres still apply. No action needed beyond restoring Valkey.

### Bad price data uploaded
Upload the corrected CSV for the same symbol with **Replace**, or delete the symbol on the Admin page and upload again.

### HTTPS certificate problems
Caddy renews automatically. Check `dc logs caddy`. Requirements: the domain's A record points at the server and ports 80 and 443 are open.

### Database backups and restore
Aiven takes automatic backups; restore from the Aiven console (point-in-time or to a new service), then point `DATABASE_URL` at it and `dc up -d app`.

---

## Where things are

| Thing | Location |
|---|---|
| Stack definition | `deploy/docker-compose.prod.yml` (copied to `/opt/algo-trading` on each deploy) |
| Proxy | `deploy/Caddyfile` |
| Alert rules | `deploy/prometheus/alerts.yml` |
| Dashboard | `deploy/grafana/dashboards/backtest-lab.json` |
| Deploy and rollback | `deploy/deploy.sh` |
| First-time server setup | `deploy/setup-server.sh` |
| Logs | Docker json-file logs, 5 × 20 MB per container |
| Pipeline | `.circleci/config.yml`, contexts `ghcr` and `production` |
