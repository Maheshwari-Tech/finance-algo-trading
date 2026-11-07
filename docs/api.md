# API reference

Base URL: `http://localhost:8123` locally (`./scripts/dev.sh`), `https://<your domain>` in production.
Interactive version: **Swagger at `/docs`** (development only; hidden when `APP_ENV=production`). The same spec as JSON: `docs/openapi.json` (`./scripts/export-openapi.sh`).

- All bodies are JSON unless noted. Errors are `{"detail": "<message>"}` (validation errors: `{"detail": [...]}` from FastAPI, or `{"detail": {"message", "problems"}}` for CSV uploads).
- Money is in the currency set in `config/ui.json` (₹ by default). Fractions (returns) are decimals: `0.125` = 12.5%.

## Authentication

1. `POST /api/auth/request-otp` with your mobile number.
2. `POST /api/auth/verify-otp` with the number and code returns a `token`.
3. Send `Authorization: Bearer <token>` on every other call. In Swagger click **Authorize** and paste the token.

`./scripts/api-login.sh` does steps 1 and 2 and prints the token.

| Who | Can call |
|---|---|
| Anyone | `Operations`, `Sign-in` (except `/me`, `/logout`) |
| Signed in (trader or admin) | everything except `Admin` |
| Admin (number in `ADMIN_MOBILES`) | everything |

With `AUTH_MODE=dev` no SMS is sent: the code is the shared `OTP_DEV_CODE`. If `ALLOWED_MOBILES` is set, only those numbers (and admins) can sign in; others get the same "sent" answer but can never verify.

**Limits:** per IP, `ip_requests_per_minute` (default 10) calls per minute to `request-otp` + `verify-otp` (shared across app replicas when `REDIS_URL` is set). Per number: one code per `otp_cooldown_seconds`, at most `otp_hourly_limit` per hour, `otp_max_attempts` wrong tries per code. Globally: after `otp_global_failed_per_hour` wrong codes in an hour (all numbers together) sign-in pauses for everyone. All in `config/auth.json`.

```bash
export BASE=http://localhost:8123
export TOKEN=$(./scripts/api-login.sh --quiet)
auth=(-H "Authorization: Bearer $TOKEN")
```

---

## Operations

### `GET /api/health` — liveness
Process is up. Does not touch the database. `200 {"status": "ok"}`

### `GET /api/ready` — readiness
Database (and Redis if configured) reachable. Used by the Docker healthcheck and the deploy smoke test.
`200 {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}` · `503` when the database is down. Redis down shows `"degraded"` but stays `200` (rate limiting falls back to allowing requests).

### `GET /metrics` — Prometheus metrics
Plain-text Prometheus format. Blocked from the internet by Caddy; scraped by Prometheus on the internal network. Not in Swagger.

---

## Sign-in

### `GET /api/auth/config`
`200 {"country_code": "91", "mode": "dev", "otp_length": 6}`

### `POST /api/auth/request-otp`
```json
{"mobile": "9876543210"}
```
`200 {"sent": true, "cooldown_seconds": 30}` · `422` invalid number · `429` too soon / too many codes / IP limit.
Accepts 10-digit local numbers (country code from `DEFAULT_COUNTRY_CODE` is added), `+<country><number>` or `00<country><number>`.

### `POST /api/auth/verify-otp`
```json
{"mobile": "9876543210", "otp": "482915"}
```
`200`
```json
{"mobile": "+919876543210", "role": "admin", "token": "…", "expires_at": "2026-11-09T12:00:00+00:00"}
```
`400` wrong or expired code · `429` too many wrong tries for this code, global pause, or IP limit.

### `GET /api/auth/me`
`200 {"mobile": "+919876543210", "role": "trader"}` · `401` no/expired token.

### `POST /api/auth/logout`
Ends this token's session. `200 {"ok": true}`

---

## Catalog

### `GET /api/symbols`
```json
[{"symbol": "NIFTY", "rows": 2480, "start": "2016-01-01", "end": "2025-12-31"}]
```

### `GET /api/strategies`
Built-in strategies with their parameters, and the period presets.
```json
{"strategies": [{"id": "sma_cross", "name": "Moving Average Crossover", "description": "…",
  "params": [{"key": "fast", "label": "Fast period", "kind": "int", "default": 10, "min": 2, "max": 200, "step": 1}]}],
 "periods": ["1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "3Y", "5Y", "MAX"]}
```

### `GET /api/rule-builder`
What rules can be made of: `operands` (with `label`, `help`, `default_period`), `operators`, `price_fields` and `limits`. Labels and help text come from `config/rule_builder.json`.

### `GET /api/ui-config`
Currency, defaults, input limits, thresholds and example rule sets (`config/ui.json`, `config/rule_templates.json`).

---

## Rules (used by Test a rule, Strategy and Saved strategies)

A **rule set** is a name and up to 10 rules:
```json
{"name": "Buy the dip",
 "rules": [
  {"action": "buy", "lots": 1, "match": "all",
   "conditions": [{"left": {"kind": "change_pct", "period": 1}, "op": "lt", "right": {"kind": "value", "value": -2}}]},
  {"action": "sell", "lots": 1, "match": "any",
   "conditions": [{"left": {"kind": "rsi", "period": 14}, "op": "gt", "right": {"kind": "value", "value": 70}}]}
 ]}
```
| Field | Values |
|---|---|
| `action` | `buy`, `sell` |
| `lots` | 1 – 10,000 |
| `match` | `all` (every condition true) or `any` |
| `conditions` | 0 – 8. None = every day |
| operand `kind` | `price` (with `field`: `open`, `high`, `low`, `close`, `prev_close`), `sma`, `ema`, `rsi`, `change_pct`, `highest`, `lowest` (with `period` 1–500), `value` (with `value`) |
| `op` | `gt`, `lt`, `crosses_above`, `crosses_below` |

Rules are data, never code: nothing a user sends is executed.

---

## Test a rule

### `POST /api/rule-test`
Every day **one rule** places its order in the period, with the values compared. No money, holdings, charges, limits or other rules.
```json
{"symbol": "NIFTY", "period": "1Y",
 "rule": {"name": "Up day", "action": "buy", "lots": 1, "match": "all",
          "conditions": [{"left": {"kind": "change_pct", "period": 1}, "op": "gt", "right": {"kind": "value", "value": 1}}]}}
```
`200`
```json
{"symbol": "NIFTY", "strategy_name": "Up day", "start": "2025-01-02", "end": "2025-12-31", "bars": 248,
 "dates": ["…"], "close": [0.0],
 "rules": [{"rule": 1, "sentence": "Buy 1 lot when 1-day change % > 1", "days": 31}],
 "events": [{"date": "2025-01-07", "close": 23707.9, "action": "buy", "lots": 1, "rule": 1, "reason": "1-day change % 1.24 > 1"}],
 "note": "Only this rule, exactly as written: …"}
```

---

## Strategy

### `POST /api/backtest`
Runs a built-in strategy (`strategy_id` + `params`) or your `rules` with money.

| Field | Default | Meaning |
|---|---|---|
| `symbol` | required | instrument |
| `strategy_id` / `params` | `custom` / `{}` | built-in strategy and its parameters (see `/api/strategies`) |
| `rules` | – | a rule set; overrides `strategy_id` |
| `initial_capital` | 0 | starting cash |
| `charges_enabled`, `fee_pct` | false, 1.0 | charge per order, % of traded value |
| `allow_short` | false | selling before buying opens a short |
| `lots` | 1 | lots per position for built-in strategies |
| `max_position` | 0 | most lots held on either side (0 = no limit) |
| `limit_to_cash` | false | cash can't go below 0: buys are cut to what cash can pay for |
| `invert` | false | run the inverse: every buy becomes a sell of the same size and vice versa |
| `period` or `start`/`end` | `MAX` | window; indicators still use the full history |

```bash
curl -s "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"symbol":"NIFTY","strategy_id":"sma_cross","params":{"fast":10,"slow":40,"mode":"trend"},"period":"2Y","initial_capital":100000,"limit_to_cash":true}' \
  $BASE/api/backtest
```
`200` — main parts of the response:

| Key | What it is |
|---|---|
| `metrics` | totals: `total_profit` = `realized_pnl` + `unrealized_pnl` − `fees_paid` = `final_equity` − `initial_capital`; `peak_position_cost` and `return_on_position_cost`; `peak_cash_in` and `return_on_cash`; drawdown, trade stats, etc. |
| `orders[]` | every requested order: `no, date, week, action, requested, filled, price, value, fee, cash_before, cash_after, position_before, position_after, avg_price_after, realized, realized_total, unrealized_after, equity_after, trade_id, note, reason`. `cash_after = cash_before − filled × price − fee` on every row. `note` says why an order was cut or skipped. `reason` says why the strategy asked for it, with values. |
| `weekly[]` | Monday-to-Sunday rows: buys, sells, skipped, lots, values, charges, realised, end-of-week holding, cash, open P&L, net worth, change. Weekly changes add up to `total_profit`. |
| `daily[]` | Every trading day: close, day move, `rules` (numbers of the rules true that day), action (`buy`, `sell`, `skipped`, `holding`, `short`, `flat`), lots asked and filled, trade value (+ paid, − received), charge, cash after, lots held, holdings, net worth, day P&L, total P&L, order number, note and reason. Day P&L adds up to `total_profit`. |
| `weeks[]`, `months[]`, `period_total` | Weekly (Monday to Sunday) and monthly overviews and the Total row: days, up/down days, net worth start → end, P&L, return, buys, sells, skipped, charges, lowest/highest cash, cash and lots at end, best and worst day, trades closed and their P&L. Rows add up to the Total. |
| `rule_legend[]` | For rule-built strategies: rule number and its sentence (the R1, R2… in `daily[].rules`). |
| `trades[]` | position cycles (0 lots → back to 0, or until it flips side), average cost: `invested, realized, unrealized, fees, pnl, return_pct, first_order, last_order`. |
| `checks[]` | identities recomputed from the published rows (`name, ok, detail`). |
| `mirror` | strategy + inverse: `strategy_profit, inverse_profit, total, charges, exact, ok, note`. When `exact`, `total` = −`charges`. |
| `series` | per-day arrays for charts: `dates, close, equity, equity_no_fee, benchmark, cash, position, order, drawdown, daily_return`. |
| `settings` | the settings used (P&L method, fill price, week definition, limits). |

Errors: `404` unknown symbol · `422` invalid strategy, parameters, rules or period.

---

## Saved rules

Each user's own rules (by mobile number); nobody else sees them. Up to 300. A rule is the rule object above with a `name` (unique per user).

| Call | Body | Result |
|---|---|---|
| `GET /api/rules` | – | `[{id, name, action, lots, match, conditions, used_by: [strategy names]}]` |
| `POST /api/rules` | a rule with a `name` | updated list (the new rule has an `id`). `422` missing or duplicate name |
| `PUT /api/rules/{id}` | a rule | updated list. **Every saved strategy using this rule uses the new version.** `404` unknown id |
| `DELETE /api/rules/{id}` | – | updated list. `422` while a saved strategy still uses it |

---

## Saved strategies

A saved strategy is a name and the ids of saved rules (buy and sell). It keeps **references**, so editing a rule changes the strategy. Up to 100 per user.

| Call | Body | Result |
|---|---|---|
| `GET /api/saved` | – | `[{name, rule_ids, rules: [current version of each rule], missing: [ids of deleted rules]}]` |
| `POST /api/saved` | `{"name": "Dip & rip", "rule_ids": [12, 15]}` | updated list; same name replaces. `422` if a rule id isn't one of your saved rules |
| `DELETE /api/saved/{name}` | – | updated list; its rules stay saved. `404` if you have none with that name |

To run a saved strategy, send its `rules` as `rules` to `/api/backtest`.

---

## Feedback

### `POST /api/feedback` (multipart form, signed in)
Everything is optional, but send at least a message or a screenshot. Your mobile number and the time are saved automatically.

| Form field | Meaning |
|---|---|
| `message` | up to 5,000 characters |
| `category` | `Bug`, `Idea` or `Other` |
| `screenshot` | PNG, JPEG, GIF or WebP, up to 5 MB (checked by file content, not name; SVG refused) |

```bash
curl -s "${auth[@]}" -F message="Compare page is great" -F category=Idea $BASE/api/feedback
curl -s "${auth[@]}" -F screenshot=@shot.png $BASE/api/feedback
```
`200 {"saved": true, "id": 12}` · `422` nothing sent, unknown category, too long, too large or not an image.

---

## Admin

### `POST /api/admin/datasets` (multipart form)
| Form field | Meaning |
|---|---|
| `symbol` | letters, digits, `. _ & -`, up to 20 (stored upper-case) |
| `mode` | `replace` (default; deletes existing rows first) or `merge` (adds/updates by date) |
| `file` | CSV with `date, open, high, low, close` (case-insensitive headers; `1,234.50` accepted) |

```bash
curl -s "${auth[@]}" -F symbol=NIFTY -F mode=replace -F file=@nifty.csv $BASE/api/admin/datasets
```
`200 {"symbol": "NIFTY", "rows": 2480, "start": "…", "end": "…"}` · `413` too large · `422 {"detail": {"message": "Invalid data", "problems": ["3 rows violate low <= open/close <= high"]}}`

### `GET /api/admin/datasets/{symbol}/rows`
Browse the stored prices of one instrument, one page at a time.

| Query | Default | Meaning |
|---|---|---|
| `page` | 1 | page number |
| `size` | 20 | rows per page: 10, 20, 50 or 100 |
| `order` | `newest` | `newest` or `oldest` first |
| `start`, `end` | – | date range (inclusive), `YYYY-MM-DD` |
| `min_close`, `max_close` | – | close price range (inclusive) |

```bash
curl -s "${auth[@]}" "$BASE/api/admin/datasets/NIFTY/rows?size=50&start=2025-01-01&min_close=22000"
```
`200 {"symbol": "NIFTY", "total": 182, "page": 1, "size": 50, "pages": 4, "rows": [{"date": "2025-12-31", "open": …, "high": …, "low": …, "close": …}]}` · `404` unknown symbol · `422` bad size or order.

### `DELETE /api/admin/datasets/{symbol}`
`200 {"deleted": "NIFTY"}` · `404` unknown.

### `GET /api/admin/upload-spec`
`200 {"columns": ["date","open","high","low","close"], "min_rows": 30, "max_upload_mb": 20}`

### `GET /api/admin/template.csv`
Header-only CSV.

### `GET /api/admin/feedback`
All feedback, newest first: `[{"id", "mobile", "created_at", "category", "message", "has_screenshot"}]`.

### `GET /api/admin/feedback/{id}/screenshot`
The image as uploaded (`image/png` etc.). `404` if that feedback has no screenshot.

`403` for any admin call by a non-admin.
