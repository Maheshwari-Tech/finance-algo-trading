# Key design decisions

Each decision says what was decided, why, and who decided it: **Product** (chosen by the product owner) or **Engineering default** (proposed during development and open to change). Newest decisions are added at the end; a changed decision is marked *Superseded* rather than deleted.

| # | Decision | Decided by |
|---|---|---|
| [D-01](#d-01-profit-is-matched-by-average-cost) | Profit is matched by average cost | Product |
| [D-02](#d-02-orders-fill-at-the-signal-days-close) | Orders fill at the signal day's close | Product |
| [D-03](#d-03-returns-are-measured-against-money-actually-invested-both-ways) | Returns are measured against money actually invested, both ways | Product |
| [D-04](#d-04-built-in-strategies-plan-a-target-holding-rules-plan-orders) | Built-in strategies plan a target holding; rules plan orders | Engineering default |
| [D-05](#d-05-cash-cant-go-below-0-is-an-option-and-buys-what-it-can-afford) | "Cash can't go below 0" is an option, and buys what it can afford | Product |
| [D-06](#d-06-the-inverse-swaps-buy-and-sell-and-uses-the-same-limits) | The inverse swaps buy and sell, and uses the same limits | Product |
| [D-07](#d-07-a-rule-places-its-order-on-every-day-its-conditions-are-met) | A rule places its order on every day its conditions are met | Product |
| [D-08](#d-08-every-number-is-published-row-by-row-and-checked) | Every number is published row by row, and checked | Product |
| [D-09](#d-09-weeks-run-monday-to-sunday) | Weeks run Monday to Sunday | Product |
| [D-10](#d-10-money-is-rounded-to-the-paisa-only-for-display) | Money is rounded to the paisa only for display | Engineering default |
| [D-11](#d-11-auto-deploy-every-green-push-to-main) | Auto-deploy every green push to `main` | Product |
| [D-12](#d-12-one-worker-per-container) | One worker per container | Engineering default |
| [D-13](#d-13-docker-compose-on-one-vm-managed-databases) | Docker Compose on one VM, managed databases | Product |
| [D-14](#d-14-one-shared-sign-in-code-for-the-private-beta) | One shared sign-in code for the private beta | Product |
| [D-15](#d-15-sign-in-rate-limit-in-valkey-failing-open) | Sign-in rate limit in Valkey, failing open | Engineering default |
| [D-16](#d-16-saved-strategies-and-feedback-live-in-the-database) | Saved strategies and feedback live in the database | Product / Engineering default |
| [D-17](#d-17-other--figures-use-most-money-in-positions-as-their-base) | Other % figures use "most money in positions" as their base | Engineering default |
| [D-18](#d-18-public-repository-secrets-only-in-env-and-ci) | Public repository; secrets only in `.env` and CI | Product |
| [D-19](#d-19-a-strategy-is-buy-rules--sell-rules-and-keeps-references-to-saved-rules) | A strategy is buy rules + sell rules, and keeps references to saved rules | Product |

---

### D-01 Profit is matched by average cost
**Decided by:** Product.
When a position is reduced, realised profit = (fill price − average entry price) × lots closed. Example: buy 1 at 100, buy 1 at 120, sell 1 at 130 → average 110 → **+20** (FIFO would say +30).
**Why:** matches how most Indian broker P&L screens show it, so users can reconcile with their broker.
**Consequence:** "trades" are position cycles (0 lots → back to 0), not FIFO lot pairs.

### D-02 Orders fill at the signal day's close
**Decided by:** Product.
A signal read at a day's close fills at that same close.
**Why:** simple and easy to verify against the price data.
**Trade-off:** slightly optimistic compared with filling at the next day's open. Changing it is one place in `domain/engine.py`.

### D-03 Returns are measured against money actually invested, both ways
**Decided by:** Product ("profit should be based on what amount you had actually invested"; show both).
- **Return on money in positions** = profit ÷ the most money ever held in open positions at entry price (longs and shorts).
- **Return on cash put in** = profit ÷ the most cash drawn from the account (starting capital − lowest cash). Shown as "n/a" when no cash was drawn (e.g. a strategy that only sells first).

Starting capital is never the base.

### D-04 Built-in strategies plan a target holding; rules plan orders
**Decided by:** Engineering default.
Built-in strategies output the holding they want; the engine orders the difference from what is actually held whenever the target changes. Rule-builder rules output "buy/sell N lots" orders.
**Why:** if an order is blocked (no short selling, cash limit), a delta-only plan would leave later orders out of sync, e.g. a blocked short followed by "go flat" would turn into a buy. Covered by `test_target_plan_does_not_lose_sync_when_blocked`.

### D-05 "Cash can't go below 0" is an option, and buys what it can afford
**Decided by:** Product.
An on/off switch. When on, a buy is cut to the lots cash can pay for including charges, and the order log says "filled 2 of 5: not enough cash". Sells are not limited (they bring cash in).

### D-06 The inverse swaps buy and sell, and uses the same limits
**Decided by:** Product.
The inverse of a strategy places exactly the opposite orders: every buy becomes a sell of the same size and vice versa. It runs with the same settings as the strategy.
**Property:** when both can place all their orders, strategy + inverse = −(charges of both runs): never positive, and the gap is exactly the charges. With "selling first" off or the cash limit on, one side can be blocked when the other isn't; the checks panel then says the pair isn't an exact mirror and why. Max lots applies equally to both sides and keeps the mirror.

### D-07 A rule places its order on every day its conditions are met
**Decided by:** Product.
If the conditions are met, the order is placed that day. What was bought stays held until a sell rule sells it; if the conditions are met again on another day, the rule buys again. No extra "firing mode" setting: a short-lived "every day / once" option was removed because it added theory a trader doesn't need.

### D-08 Every number is published row by row, and checked
**Decided by:** Product ("data is most important… consumer can easily verify").
Every requested order (including cut and skipped ones) with cash before/after and the reason with actual values; weekly rows; trades; downloadable CSVs. Each run recomputes identities from the published rows and shows ✓/✗. A separate reference calculator in the tests must agree with the engine on every day.

### D-09 Weeks run Monday to Sunday
**Decided by:** Product. Labelled by the Monday ("week of 2025-01-06").

### D-10 Money is rounded to the paisa only for display
**Decided by:** Engineering default.
The engine keeps full precision. Published rows are rounded to 2 decimals; weekly and per-trade money is computed as differences of rounded running totals so the rows add up exactly. Cross-total checks allow ±₹0.02 of rounding.

### D-11 Auto-deploy every green push to `main`
**Decided by:** Product.
No manual approval. Safety net: the image is smoke-tested before push, and `deploy.sh` rolls back if `/api/ready` does not answer through HTTPS within about two minutes. Branch protection on `main` requiring the CircleCI checks is agreed and still to be switched on in GitHub.

### D-12 One worker per container
**Decided by:** Engineering default.
**Why:** Prometheus counters stay exact without multi-process setup. Scale by adding containers.

### D-13 Docker Compose on one VM, managed databases
**Decided by:** Product. Aiven Postgres and Aiven Valkey; app, Caddy, Prometheus, Grafana and node-exporter on one VM. Images in GHCR, built by CircleCI.

### D-14 One shared sign-in code for the private beta
**Decided by:** Product ("keep fixed OTP for now").
**Risk:** anyone who knows the code and an admin number could sign in as admin.
**Mitigations:** production refuses guessable codes; per-number, per-IP and global wrong-code limits; optional `ALLOWED_MOBILES`. **Exit:** implement an SMS `OtpSender` and set `AUTH_MODE=prod`.

### D-15 Sign-in rate limit in Valkey, failing open
**Decided by:** Engineering default.
Per-IP counters in Valkey so limits hold across containers. If Valkey is unreachable the limiter allows requests (and logs) rather than locking everyone out; per-number and global limits in Postgres still apply.

### D-16 Saved strategies and feedback live in the database
**Decided by:** Product (saved under the user's login; feedback saved and listed for admin) / Engineering default (storage).
Feedback screenshots are stored in Postgres (≤ 5 MB, PNG/JPEG/GIF/WebP checked by content) so they survive redeploys without server disk or object storage. Revisit if volume grows: move images to object storage.

### D-17 Other % figures use "most money in positions" as their base
**Decided by:** Engineering default (flagged at the time).
Drawdown %, daily returns, volatility, Sharpe and the buy-and-hold comparison need one base; they use the most money held in positions at entry price.

### D-18 Public repository; secrets only in `.env` and CI
**Decided by:** Product. `.env` files are git-ignored; secrets live in the server's `.env` and CircleCI contexts. Credentials that were ever pasted into chat should be rotated.

### D-19 A strategy is buy rules + sell rules, and keeps references to saved rules
**Decided by:** Product.
A condition is one comparison; a rule is one action (buy or sell N lots) with one or more conditions; a strategy is a name plus buy rules and sell rules. Rules are saved on their own and a saved strategy stores the ids of its rules, so editing a saved rule changes every strategy that uses it. A rule can't be deleted while a strategy uses it. Test a rule works on one rule at a time.
