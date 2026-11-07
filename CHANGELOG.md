# Changelog

All notable changes. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are when the change was committed.

## [Unreleased]

### Added
- **Test a rule** page, one rule at a time: "You will buy 1 lot on 07 Jan 2025 · 1-day change % 1.24 > 1" for every day the rule triggers, with the days marked on the chart. No money or other rules involved.
- **Saved rules**: save each rule under your name. Strategies keep references to saved rules, so editing a rule updates every strategy that uses it.
- Strategy editor split into **Buy rules** and **Sell rules**, each with "+ Add rule" and "Load a saved rule".
- **Compare** page: two already-built strategies (built-in or saved) on the same prices, period and money settings, side by side, with both net-worth lines on one chart.
- **Saved strategies** stored under each user's login (were in the browser only): a name plus references to saved rules. Shown in the Rule dropdown.
- Admin: **View** an instrument's stored prices right after upload: 10 / 20 / 50 / 100 rows per page, filters for date range, close range and newest/oldest first.
- **Feedback** page: optional message, optional type (Bug, Idea, Other), optional screenshot. Mobile number and time are saved. Admin page lists all feedback.
- Rules read as plain-English sentences; one-line help for every indicator.
- Swagger with an Authorize button, endpoint descriptions and groups; `scripts/export-openapi.sh` writes `docs/openapi.json`.
- `scripts/dev.sh` starts backend and frontend together; `scripts/api-login.sh` prints a token for curl or Swagger.
- Docs: API reference, architecture, key design decisions, runbook, this changelog.

- Strategy page dashboards restored and added (nothing removed):
  - **Weekly overview** and **Monthly overview**: days, up/down days, net worth start → end, P&L (with a bar), return, buys, sells, skipped, charges, lowest/highest cash, cash and lots at end, best/worst day, trades closed, and a **Total** row. Filters: only periods with orders, newest first; CSV. Click a week or month to see its days.
  - **Daily transactions**: every trading day with the rules that were true (R1, R2… with a legend), the action, trade value, charge, cash after, lots, holdings, net worth, day and total P&L, note and reason. Filters: all days / days with orders / buys / sells / skipped or cut / a rule was true, date range, newest first, 10/20/50/100/all rows; a summary of the selected days; CSV.
  - **Jump to** links and **Show** switches for every section (Summary, Takeaways, Charts, Weekly, Monthly, Daily, Orders·weeks·trades·checks, All statistics); the choice is remembered in the browser.
  - New checks: daily rows, weekly overview and monthly overview each add up to the total profit and charges.

### Changed
- Site renamed to **Strategic Trader**.
- Menu: Test a rule · Strategy · Compare · Feedback · Admin.

## 2026-11-02 — `802cd08` Verifiable results

### Added
- Order log of every requested order (including cut and skipped ones): cash before and after, lots, average price, realised and open P&L, net worth, and the reason with the actual values.
- Weekly view (Monday to Sunday) and trades (position cycles), clickable through to their orders; CSV download for orders, weeks and trades.
- "How the profit adds up": starting capital + realised + open − charges = net worth.
- Checks recomputed on every run, plus the strategy + inverse check.
- "Don't let cash go below 0" option (buys what cash can afford) and "Inverse strategy" switch.
- Return on money in positions and return on cash put in.
- Independent reference calculator in the tests, compared with the engine on every day.

### Changed
- Profit matched by **average cost** (was FIFO).
- Built-in strategies plan a target holding, so blocked orders don't throw later orders out of sync.

### Fixed
- CSV uploads with thousands separators (`"1,000.50"`) were rejected under pandas 3.

## 2026-11-02 — `95529f8` CI fixes
### Fixed
- Frontend build in CI: Node 22.11 was too old for Vite's bundler; CI and Docker now use Node 26.
- CircleCI test-results upload tried to read the coverage report as JUnit.

## 2026-11-02 — `9f29fb8`
### Changed
- Docker image renamed to `finance-algo-trading`.

## 2026-11-02 — `148cd04` Initial commit
### Fixed
- App did not start: broken imports, wrong service module name, strategies never registered, missing config files.
- RSI was blank when prices only rose.

### Added
- Production settings (`APP_ENV`), strong-secret and access-code checks, optional sign-in allowlist, JSON logs.
- Sign-in limits per IP (Valkey), per number and globally; expired-session cleanup.
- `/api/ready`, Prometheus `/metrics`, non-blocking CSV upload, bounded holding-window scan.
- Tests, Dockerfile, Caddy + Prometheus + Grafana stack, CircleCI pipeline with rollback deploy, `scripts/verify.sh`, `deploy/setup-server.sh`.
