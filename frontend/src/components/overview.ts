import type { BacktestResult, DayRow, PeriodRow } from "../api/types";
import { h } from "../lib/dom";
import { money, money2, pct, price, tone } from "../lib/format";
import { c, csv, type Col } from "./ledger";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2025-11-03" -> "03 Nov 2025" */
export const longDate = (iso: string) => { const [y, m, d] = iso.split("-"); return `${d} ${MON[Number(m) - 1]} ${y}`; };

const signedMoney = (v: number) => (v ? money(v, true) : money(0));
const orders = (n: number, lots: number) => (n ? `${n} (${lots} lot${lots === 1 ? "" : "s"})` : "–");

// ---------------------------------------------------------------- weekly / monthly overview

const periodCols = (): Col<PeriodRow>[] => [
  c("Period", (p) => p.label, (p) => h("span", { class: "period-label" }, p.label, p.label !== "Total" ? h("small", {}, `${longDate(p.start)} → ${longDate(p.end)}`) : null)),
  c("Days", (p) => p.days),
  c("Up / down days", (p) => `${p.up_days} / ${p.down_days}`, (p) => h("span", {}, h("span", { class: "up" }, String(p.up_days)), " / ", h("span", { class: "down" }, String(p.down_days))), undefined, "Days net worth rose / fell"),
  c("Net worth", (p) => `${p.net_worth_start} -> ${p.net_worth_end}`, (p) => `${money(p.net_worth_start)} → ${money(p.net_worth_end)}`, undefined, "Cash + value of holdings, start → end"),
  c("P&L", (p) => p.pnl, (p) => signedMoney(p.pnl), (p) => `strong ${tone(p.pnl)}`, "Change in net worth"),
  c("Return", (p) => p.return_pct, (p) => pct(p.return_pct, 2, true), (p) => tone(p.return_pct), "P&L / most money held in positions during the run"),
  c("Buys", (p) => p.buys, (p) => orders(p.buys, p.bought_lots), (p) => (p.buys ? "up" : "muted")),
  c("Sells", (p) => p.sells, (p) => orders(p.sells, p.sold_lots), (p) => (p.sells ? "down" : "muted")),
  c("Skipped", (p) => p.skipped, (p) => (p.skipped ? String(p.skipped) : "–"), (p) => (p.skipped ? "warn" : "muted"), "Orders asked for where nothing could be filled"),
  c("Charges", (p) => p.charges, (p) => (p.charges ? money2(p.charges) : "–")),
  c("Lowest cash", (p) => p.lowest_cash, (p) => money(p.lowest_cash), (p) => tone(p.lowest_cash)),
  c("Highest cash", (p) => p.highest_cash, (p) => money(p.highest_cash), (p) => tone(p.highest_cash)),
  c("Cash at end", (p) => p.cash_end, (p) => money(p.cash_end), (p) => tone(p.cash_end)),
  c("Lots at end", (p) => p.lots_end),
  c("Best day", (p) => p.best_day, (p) => signedMoney(p.best_day), (p) => tone(p.best_day)),
  c("Worst day", (p) => p.worst_day, (p) => signedMoney(p.worst_day), (p) => tone(p.worst_day)),
  c("Trades closed", (p) => p.trades_closed, (p) => (p.trades_closed ? `${p.trades_closed} · ${signedMoney(p.trades_closed_pnl)}` : "–"), (p) => (p.trades_closed ? tone(p.trades_closed_pnl) : "muted"), "Trades that ended in this period, and their P&L"),
];

/** Weekly or monthly overview with a Total row, a small P&L bar per row, and click-through to the days. */
export function periodPanel(id: string, title: string, subtitle: string, rows: PeriodRow[], total: PeriodRow | null, csvName: string,
  onPick: (p: PeriodRow) => void): HTMLElement {
  const cols = periodCols();
  let newest = false, onlyActive = false;
  const body = h("div");
  const maxAbs = Math.max(1, ...rows.map((p) => Math.abs(p.pnl)));
  const bar = (v: number) => h("span", { class: `pnl-bar ${tone(v)}`, style: `width:${Math.round((Math.abs(v) / maxAbs) * 100)}%` });
  const draw = () => {
    let list = onlyActive ? rows.filter((p) => p.buys || p.sells || p.skipped || p.trades_closed) : rows;
    if (newest) list = [...list].reverse();
    const up = rows.filter((p) => p.pnl > 0).length, down = rows.filter((p) => p.pnl < 0).length;
    body.replaceChildren(
      h("div", { class: "table-tools" },
        h("span", { class: "sub" }, `${list.length} of ${rows.length} · `, h("span", { class: "up" }, `${up} up`), " · ", h("span", { class: "down" }, `${down} down`)),
        h("div", { class: "pager" },
          h("label", { class: "inline-check" }, h("input", { type: "checkbox", checked: onlyActive, on: { change: (e) => { onlyActive = (e.target as HTMLInputElement).checked; draw(); } } }), "Only with orders"),
          h("label", { class: "inline-check" }, h("input", { type: "checkbox", checked: newest, on: { change: (e) => { newest = (e.target as HTMLInputElement).checked; draw(); } } }), "Newest first"),
          h("button", { class: "btn ghost", on: { click: () => csv(csvName, cols, total ? [...rows, total] : rows) } }, "Download CSV"))),
      h("div", { class: "table-scroll tall" }, h("table", { class: "data ledger overview" },
        h("thead", {}, h("tr", {}, cols.map((x) => h("th", { title: x.title ?? "" }, x.head)))),
        h("tbody", {}, list.map((p) => h("tr", { class: "clickable", title: "Show these days in Daily transactions", on: { click: () => onPick(p) } },
          cols.map((x, i) => h("td", { class: x.cls?.(p) ?? "" }, x.show(p), i === 4 ? bar(p.pnl) : null))))),
        total && h("tfoot", {}, h("tr", { class: "total" }, cols.map((x) => h("td", { class: x.cls?.(total) ?? "" }, x.show(total))))))));
  };
  draw();
  return h("section", { class: "panel overview-panel", id },
    h("div", { class: "panel-head" }, h("h3", {}, title), h("span", { class: "sub" }, subtitle)), body);
}

// ---------------------------------------------------------------- daily transactions

type ActionFilter = "all" | "orders" | "buy" | "sell" | "skipped" | "rules";
const FILTERS: [ActionFilter, string][] = [["all", "All days"], ["orders", "Days with orders"], ["buy", "Buys"], ["sell", "Sells"], ["skipped", "Skipped / cut"], ["rules", "A rule was true"]];

export interface DailyPanel { el: HTMLElement; showRange: (from: string, to: string, label: string) => void }

export function dailyPanel(r: BacktestResult, pageSize: number): DailyPanel {
  const legend = r.rule_legend;
  const ruleSide = (n: number) => {
    const s = legend.find((x) => x.rule === n)?.sentence ?? "";
    const buy = s.toLowerCase().startsWith("buy");
    return (r.inverted ? !buy : buy) ? "buy" : "sell";
  };
  const actionText = (d: DayRow): Node => {
    if (d.action === "buy" || d.action === "sell") {
      const cut = d.filled !== d.requested ? ` of ${Math.abs(d.requested)}` : "";
      return h("span", { class: `tag ${d.action === "buy" ? "long" : "short"}` }, `${d.action.toUpperCase()} ${Math.abs(d.filled)}${cut}`);
    }
    if (d.action === "skipped") return h("span", { class: "tag skipped" }, `${d.requested > 0 ? "BUY" : "SELL"} ${Math.abs(d.requested)} skipped`);
    return h("span", { class: "muted" }, d.action);
  };
  const cols: Col<DayRow>[] = [
    c("Date", (d) => d.date, (d) => longDate(d.date)),
    c("Close", (d) => d.close, (d) => price(d.close)),
    c("Day move", (d) => (d.day_move == null ? "" : d.day_move), (d) => (d.day_move == null ? "–" : pct(d.day_move, 2, true)), (d) => tone(d.day_move ?? 0), "Close vs the previous close"),
    ...(legend.length ? [c<DayRow>("Rules", (d) => d.rules.map((n) => `R${n}`).join(" "),
      (d) => (d.rules.length ? h("span", { class: "rule-pills" }, d.rules.map((n) => h("span", { class: `rule-pill ${ruleSide(n)}`, title: legend.find((x) => x.rule === n)?.sentence ?? "" }, `R${n}`))) : "–"),
      undefined, "Rules whose conditions were true that day")] : []),
    c("Action", (d) => (d.action === "buy" || d.action === "sell" ? `${d.action.toUpperCase()} ${Math.abs(d.filled)}` : d.action), actionText),
    c("Trade value", (d) => d.trade_value, (d) => (d.trade_value ? money2(d.trade_value) : "–"), (d) => (d.trade_value > 0 ? "down" : d.trade_value < 0 ? "up" : "muted"), "+ paid for a buy, − received for a sell"),
    c("Charge", (d) => d.fee, (d) => (d.fee ? money2(d.fee) : "–")),
    c("Cash after", (d) => d.cash_after, (d) => money2(d.cash_after), (d) => tone(d.cash_after)),
    c("Lots held", (d) => d.lots),
    c("Holdings", (d) => d.holdings, (d) => money2(d.holdings), undefined, "Lots held × close"),
    c("Net worth", (d) => d.net_worth, (d) => money2(d.net_worth), (d) => `strong ${tone(d.net_worth - (r.metrics.initial_capital))}`, "Cash after + holdings"),
    c("Day P&L", (d) => d.day_pnl, (d) => (d.day_pnl ? money2(d.day_pnl, true) : "–"), (d) => tone(d.day_pnl)),
    c("Total P&L", (d) => d.total_pnl, (d) => money2(d.total_pnl, true), (d) => tone(d.total_pnl), "Net worth − starting capital"),
    c("Note", (d) => d.note, (d) => d.note,(d) => (d.note ? "warn small" : "small")),
    c("Why", (d) => d.reason, (d) => d.reason, () => "small reason"),
  ];

  let filter: ActionFilter = "all";
  let newest = false;
  let from = r.start, to = r.end, rangeLabel = "";
  let size = pageSize, page = 0;
  const body = h("div");
  const fromIn = h("input", { type: "date", min: r.start, max: r.end, value: from, on: { change: (e) => { from = (e.target as HTMLInputElement).value || r.start; rangeLabel = ""; page = 0; draw(); } } });
  const toIn = h("input", { type: "date", min: r.start, max: r.end, value: to, on: { change: (e) => { to = (e.target as HTMLInputElement).value || r.end; rangeLabel = ""; page = 0; draw(); } } });

  const keep = (d: DayRow) => {
    if (d.date < from || d.date > to) return false;
    switch (filter) {
      case "orders": return d.order_no != null;
      case "buy": return d.action === "buy";
      case "sell": return d.action === "sell";
      case "skipped": return d.action === "skipped" || (d.filled !== d.requested && d.order_no != null);
      case "rules": return d.rules.length > 0;
      default: return true;
    }
  };

  const draw = () => {
    let rows = r.daily.filter(keep);
    if (newest) rows = rows.reverse();
    const pages = size ? Math.max(1, Math.ceil(rows.length / size)) : 1;
    page = Math.min(page, pages - 1);
    const slice = size ? rows.slice(page * size, (page + 1) * size) : rows;
    const inRange = r.daily.filter((d) => d.date >= from && d.date <= to);
    const pnl = inRange.reduce((s, d) => s + d.day_pnl, 0);
    const counts = { buy: inRange.filter((d) => d.action === "buy").length, sell: inRange.filter((d) => d.action === "sell").length, skipped: inRange.filter((d) => d.action === "skipped").length };
    fromIn.value = from; toIn.value = to;
    body.replaceChildren(
      h("div", { class: "chips" }, FILTERS.filter(([f]) => f !== "rules" || legend.length).map(([f, label]) =>
        h("button", { class: `chip${f === filter ? " active" : ""}`, on: { click: () => { filter = f; page = 0; draw(); } } }, label))),
      h("div", { class: "table-tools" },
        h("div", { class: "date-range" }, h("span", { class: "sub" }, "From"), fromIn, h("span", { class: "sub" }, "to"), toIn,
          (from !== r.start || to !== r.end) && h("span", { class: "filter-chip" }, rangeLabel || "Custom dates",
            h("button", { class: "btn ghost", on: { click: () => { from = r.start; to = r.end; rangeLabel = ""; page = 0; draw(); } } }, "All dates"))),
        h("label", { class: "inline-check" }, h("input", { type: "checkbox", checked: newest, on: { change: (e) => { newest = (e.target as HTMLInputElement).checked; draw(); } } }), "Newest first")),
      h("div", { class: "day-summary" },
        h("span", {}, h("b", {}, String(inRange.length)), " days"),
        h("span", { class: "up" }, h("b", {}, String(counts.buy)), " buys"),
        h("span", { class: "down" }, h("b", {}, String(counts.sell)), " sells"),
        counts.skipped ? h("span", { class: "warn" }, h("b", {}, String(counts.skipped)), " skipped") : null,
        h("span", { class: tone(pnl) }, "P&L ", h("b", {}, money2(pnl, true)))),
      h("div", { class: "table-tools" },
        h("span", { class: "sub" }, `${rows.length.toLocaleString()} of ${r.daily.length.toLocaleString()} days${size ? ` · page ${page + 1} of ${pages}` : ""}`),
        h("div", { class: "pager" },
          h("select", { class: "inline", title: "Rows per page", on: { change: (e) => { size = Number((e.target as HTMLSelectElement).value); page = 0; draw(); } } },
            [10, 20, 50, 100, 0].map((n) => h("option", { value: String(n), selected: n === size }, n ? `${n} per page` : "All rows"))),
          h("button", { class: "btn ghost", disabled: page === 0, on: { click: () => { page--; draw(); } } }, "‹ Prev"),
          h("button", { class: "btn ghost", disabled: page >= pages - 1, on: { click: () => { page++; draw(); } } }, "Next ›"),
          h("button", { class: "btn ghost", disabled: !rows.length, on: { click: () => csv(`${r.symbol}-daily.csv`, cols, rows) } }, "Download CSV"))),
      h("div", { class: "table-scroll tall" }, h("table", { class: "data ledger daily" },
        h("thead", {}, h("tr", {}, cols.map((x) => h("th", { title: x.title ?? "" }, x.head)))),
        h("tbody", {}, slice.length ? slice.map((d) => h("tr", { class: `day ${d.action}` }, cols.map((x) => h("td", { class: x.cls?.(d) ?? "" }, x.show(d)))))
          : [h("tr", {}, h("td", { colSpan: cols.length, class: "muted" }, "No days match these filters"))]))));
  };
  draw();

  const el = h("section", { class: "panel daily-panel", id: "dash-daily" },
    h("div", { class: "panel-head" }, h("h3", {}, "Daily transactions"), h("span", { class: "sub" }, "Every trading day: what the rules said, what was done, and where the account stood")),
    legend.length ? h("div", { class: "rule-legend" }, legend.map((x) => h("span", { class: "legend-item" }, h("span", { class: `rule-pill ${ruleSide(x.rule)}` }, `R${x.rule}`), x.sentence)),
      r.inverted ? h("span", { class: "sub" }, "Inverse run: each rule's buy and sell are swapped.") : null) : null,
    h("p", { class: "hint" }, "Orders fill at that day's closing price. Net worth = cash after + lots held × close. Click a week or month above to see just its days."),
    body);
  return {
    el,
    showRange: (a, b, label) => { from = a; to = b; rangeLabel = label; filter = "all"; page = 0; draw(); el.scrollIntoView({ behavior: "smooth", block: "start" }); },
  };
}
