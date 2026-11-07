import type { BacktestResult, Order, Trade, WeekRow } from "../api/types";
import { h } from "../lib/dom";
import { lots, money2, pct, price, tone } from "../lib/format";

/** A table column: header, how to show a row, and the raw value written to CSV. */
export interface Col<T> { head: string; show: (r: T) => Node | string; raw: (r: T) => string | number; title?: string; cls?: (r: T) => string }

export const c = <T>(head: string, raw: (r: T) => string | number, show?: (r: T) => Node | string, cls?: (r: T) => string, title?: string): Col<T> =>
  ({ head, raw, show: show ?? ((r) => String(raw(r))), cls, title });

export function csv<T>(name: string, cols: Col<T>[], rows: T[]) {
  const esc = (v: string | number) => { const s = String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const text = [cols.map((x) => esc(x.head)).join(","), ...rows.map((r) => cols.map((x) => esc(x.raw(r))).join(","))].join("\n");
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type: "text/csv" })), download: name });
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Paged table with a CSV button for all rows (not just the visible page). */
export function table<T>(cols: Col<T>[], rows: T[], pageSize: number, csvName: string, onRow?: (r: T) => void): HTMLElement {
  const wrap = h("div");
  let page = 0;
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const draw = () => {
    const slice = rows.slice(page * pageSize, (page + 1) * pageSize);
    wrap.replaceChildren(
      h("div", { class: "table-tools" },
        h("span", { class: "sub" }, rows.length ? `${rows.length.toLocaleString()} rows · page ${page + 1} of ${pages}` : "No rows"),
        h("div", { class: "pager" },
          h("button", { class: "btn ghost", disabled: page === 0, on: { click: () => { page = 0; draw(); } } }, "« First"),
          h("button", { class: "btn ghost", disabled: page === 0, on: { click: () => { page--; draw(); } } }, "‹ Prev"),
          h("button", { class: "btn ghost", disabled: page >= pages - 1, on: { click: () => { page++; draw(); } } }, "Next ›"),
          h("button", { class: "btn ghost", disabled: page >= pages - 1, on: { click: () => { page = pages - 1; draw(); } } }, "Last »"),
          h("button", { class: "btn ghost", disabled: !rows.length, on: { click: () => csv(csvName, cols, rows) } }, "Download CSV"))),
      h("div", { class: "table-scroll tall" }, h("table", { class: "data ledger" },
        h("thead", {}, h("tr", {}, cols.map((x) => h("th", { title: x.title ?? "" }, x.head)))),
        h("tbody", {}, slice.map((r) => h("tr", { class: onRow ? "clickable" : "", on: onRow ? { click: () => onRow(r) } : {} },
          cols.map((x) => h("td", { class: x.cls?.(r) ?? "" }, x.show(r)))))))));
  };
  draw();
  return wrap;
}

const orderCols = (): Col<Order>[] => [
  c("#", (o) => o.no),
  c("Date", (o) => o.date),
  c("Action", (o) => o.action, (o) => h("span", { class: `tag ${o.action === "buy" ? "long" : "short"}` }, o.action)),
  c("Asked", (o) => o.requested, (o) => lots(o.requested), undefined, "Lots the strategy asked for (+ buy, - sell)"),
  c("Filled", (o) => o.filled, (o) => lots(o.filled), (o) => (o.filled !== o.requested ? "warn" : ""), "Lots actually traded"),
  c("Price", (o) => o.price, (o) => price(o.price), undefined, "Fill price = that day's close"),
  c("Value", (o) => o.value, (o) => money2(o.value), undefined, "Filled lots x price"),
  c("Charges", (o) => o.fee, (o) => money2(o.fee)),
  c("Cash before", (o) => o.cash_before, (o) => money2(o.cash_before)),
  c("Cash after", (o) => o.cash_after, (o) => money2(o.cash_after), (o) => tone(o.cash_after), "Cash before - filled x price - charges"),
  c("Lots after", (o) => o.position_after, (o) => String(o.position_after)),
  c("Avg price", (o) => o.avg_price_after, (o) => (o.position_after ? price(o.avg_price_after) : "-"), undefined, "Average entry price of what is held"),
  c("Realised", (o) => o.realized, (o) => (o.realized ? money2(o.realized, true) : "-"), (o) => tone(o.realized), "(price - avg price) x lots closed, before charges"),
  c("Realised total", (o) => o.realized_total, (o) => money2(o.realized_total, true), (o) => tone(o.realized_total)),
  c("Open P&L", (o) => o.unrealized_after, (o) => money2(o.unrealized_after, true), (o) => tone(o.unrealized_after), "(close - avg price) x lots held"),
  c("Net worth", (o) => o.equity_after, (o) => money2(o.equity_after), undefined, "Cash after + lots after x price"),
  c("Trade", (o) => o.trade_id ?? "", (o) => (o.trade_id ? `#${o.trade_id}` : "-")),
  c("Note", (o) => o.note, (o) => o.note, (o) => (o.note ? "warn small" : "small")),
  c("Why", (o) => o.reason, (o) => o.reason, () => "small reason"),
];

const weekCols = (): Col<WeekRow>[] => [
  c("Week of (Mon)", (w) => w.week_start), c("Last day", (w) => w.week_end),
  c("Buys", (w) => w.buys), c("Sells", (w) => w.sells), c("Skipped", (w) => w.skipped, (w) => (w.skipped ? String(w.skipped) : "-"), (w) => (w.skipped ? "warn" : "")),
  c("Lots bought", (w) => w.bought_lots), c("Lots sold", (w) => w.sold_lots),
  c("Bought for", (w) => w.buy_value, (w) => money2(w.buy_value)), c("Sold for", (w) => w.sell_value, (w) => money2(w.sell_value)),
  c("Charges", (w) => w.fees, (w) => money2(w.fees)),
  c("Realised", (w) => w.realized, (w) => money2(w.realized, true), (w) => tone(w.realized)),
  c("Lots at end", (w) => w.position_end), c("Avg price", (w) => w.avg_price_end, (w) => (w.position_end ? price(w.avg_price_end) : "-")),
  c("Close", (w) => w.close_end, (w) => price(w.close_end)), c("Cash", (w) => w.cash_end, (w) => money2(w.cash_end), (w) => tone(w.cash_end)),
  c("Open P&L", (w) => w.unrealized_end, (w) => money2(w.unrealized_end, true), (w) => tone(w.unrealized_end)),
  c("Net worth", (w) => w.equity_end, (w) => money2(w.equity_end)),
  c("Change", (w) => w.equity_change, (w) => money2(w.equity_change, true), (w) => tone(w.equity_change), "Net worth change vs the previous week"),
];

const tradeCols = (): Col<Trade>[] => [
  c("#", (t) => t.id), c("Side", (t) => t.side, (t) => h("span", { class: `tag ${t.side}` }, t.side)),
  c("Max lots", (t) => t.qty), c("Opened", (t) => t.entry_date), c("Closed", (t) => (t.is_open ? "open" : t.exit_date)),
  c("Avg entry", (t) => t.entry_price, (t) => price(t.entry_price)),
  c("Avg exit", (t) => t.exit_price, (t) => (t.is_open ? `${price(t.exit_price)} (last close)` : price(t.exit_price))),
  c("Days", (t) => t.days), c("Invested", (t) => t.invested, (t) => money2(t.invested), undefined, "Most money in this position at entry price"),
  c("Realised", (t) => t.realized, (t) => money2(t.realized, true), (t) => tone(t.realized)),
  c("Open P&L", (t) => t.unrealized, (t) => (t.is_open ? money2(t.unrealized, true) : "-"), (t) => tone(t.unrealized)),
  c("Charges", (t) => t.fees, (t) => money2(t.fees)),
  c("P&L", (t) => t.pnl, (t) => money2(t.pnl, true), (t) => tone(t.pnl), "Realised + open - charges"),
  c("Return", (t) => t.return_pct, (t) => pct(t.return_pct, 2, true), (t) => tone(t.return_pct), "P&L / invested"),
  c("Orders", (t) => `${t.first_order}-${t.last_order}`, (t) => `#${t.first_order}–#${t.last_order} (${t.orders})`),
];

/** Orders, weekly summary, trades and checks: every number the dashboard shows, row by row. */
export function ledgerPanel(r: BacktestResult, pageSize: number): HTMLElement {
  const body = h("div");
  const tabs = ["Orders", "Weekly", "Trades", "Checks"] as const;
  type Tab = (typeof tabs)[number];
  let active: Tab = "Orders";
  let showSkipped = true;
  let filter: { label: string; keep: (o: Order) => boolean } | null = null;
  const sym = r.symbol;
  const failed = r.checks.filter((x) => !x.ok).length + (r.mirror.ok ? 0 : 1);

  const head = h("div", { class: "tabs" });
  const render = () => {
    head.replaceChildren(...tabs.map((t) => h("button", { class: `chip${t === active ? " active" : ""}`, on: { click: () => { active = t; render(); } } },
      t === "Checks" ? `Checks ${failed ? `✗ ${failed}` : "✓"}` : t === "Orders" ? `Orders (${r.orders.filter((o) => o.filled !== 0).length})`
        : t === "Weekly" ? `Weekly (${r.weekly.length})` : `Trades (${r.trades.length})`)));
    if (active === "Orders") {
      let rows = r.orders.filter((o) => showSkipped || o.filled !== 0);
      if (filter) rows = rows.filter(filter.keep);
      body.replaceChildren(
        h("div", { class: "table-tools" },
          h("label", { class: "inline-check" }, h("input", { type: "checkbox", checked: showSkipped, on: { change: (e) => { showSkipped = (e.target as HTMLInputElement).checked; render(); } } }),
            "Show orders that were cut or skipped"),
          filter && h("span", { class: "filter-chip" }, filter.label, h("button", { class: "btn ghost", on: { click: () => { filter = null; render(); } } }, "Show all"))),
        h("p", { class: "hint" }, "Each row: cash after = cash before − filled × price − charges; net worth = cash after + lots after × price. Money is rounded to the paisa."),
        table(orderCols(), rows, pageSize, `${sym}-orders.csv`));
    } else if (active === "Weekly") {
      body.replaceChildren(h("p", { class: "hint" }, "Weeks run Monday to Sunday. Click a week to see its orders. Weekly changes add up to the total profit."),
        table(weekCols(), r.weekly, pageSize, `${sym}-weekly.csv`, (w) => {
          filter = { label: `Week of ${w.week_start}`, keep: (o) => o.week === w.week_start }; active = "Orders"; render();
        }));
    } else if (active === "Trades") {
      body.replaceChildren(h("p", { class: "hint" }, "A trade runs from holding 0 lots until back to 0 (or until it flips from long to short). P&L uses average cost. Click a trade to see its orders."),
        table(tradeCols(), r.trades, pageSize, `${sym}-trades.csv`, (t) => {
          filter = { label: `Trade #${t.id}`, keep: (o) => o.trade_id === t.id }; active = "Orders"; render();
        }));
    } else {
      const m = r.mirror;
      body.replaceChildren(h("ul", { class: "checks" },
        ...r.checks.map((x) => h("li", { class: x.ok ? "ok" : "bad" }, h("span", { class: "mark" }, x.ok ? "✓" : "✗"), h("div", {}, h("strong", {}, x.name), h("small", {}, x.detail)))),
        h("li", { class: !m.ok ? "bad" : m.exact ? "ok" : "info" }, h("span", { class: "mark" }, !m.ok ? "✗" : m.exact ? "✓" : "i"),
          h("div", {}, h("strong", {}, "Strategy + inverse = − charges"),
            h("small", {}, `${r.inverted ? "This (inverse) run" : "Strategy"} ${money2(m.strategy_profit, true)} + ${r.inverted ? "original" : "inverse"} ${money2(m.inverse_profit, true)} = ${money2(m.total, true)}; charges of both runs ${money2(m.charges)}. ${m.note}`)))));
    }
  };
  render();
  return h("section", { class: "panel ledger-panel", id: "ledger" },
    h("div", { class: "panel-head" }, h("h3", {}, "Every order, week and trade"), h("span", { class: "sub" }, "Check any number by hand, or download it")),
    head, body);
}
