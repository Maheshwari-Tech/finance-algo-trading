import type { BacktestResult } from "../api/types";
import { h } from "../lib/dom";
import { money2, pct, price, tone } from "../lib/format";

/** "How the profit adds up": starting capital + realised + open - charges = net worth, with the inputs shown. */
export function pnlSummary(r: BacktestResult): HTMLElement {
  const m = r.metrics, s = r.settings;
  const sum = m.realized_pnl + m.unrealized_pnl - m.fees_paid;
  const ok = Math.abs(sum - m.total_profit) < 0.02 && Math.abs(m.initial_capital + m.total_profit - m.final_equity) < 0.02;
  const term = (label: string, v: number, hint: string, sign = "") =>
    h("div", { class: `term ${tone(v)}`, title: hint }, h("span", {}, label), h("strong", {}, `${sign}${money2(v)}`));
  const failed = r.checks.filter((x) => !x.ok).length + (r.mirror.ok ? 0 : 1);
  return h("section", { class: "panel pnl-summary" },
    h("div", { class: "panel-head" }, h("h3", {}, "How the profit adds up"),
      h("a", { class: `check-badge ${failed ? "bad" : "ok"}`, href: "#ledger" }, failed ? `✗ ${failed} check(s) failed` : `✓ all ${r.checks.length + 1} checks pass`)),
    h("div", { class: "equation" },
      term("Starting capital", m.initial_capital, "What you started with"), h("span", { class: "op" }, "+"),
      term("Realised P&L", m.realized_pnl, "Closed positions, average cost, before charges"), h("span", { class: "op" }, "+"),
      term("Open P&L", m.unrealized_pnl, `${m.final_position} lots held at average ${price(m.final_avg_price)}, valued at the last close`), h("span", { class: "op" }, "−"),
      term("Charges", m.fees_paid, "All charges paid"), h("span", { class: "op" }, "="),
      term("Net worth", m.final_equity, "Cash + lots held x last close")),
    h("p", { class: `hint ${ok ? "" : "down"}` },
      `Total profit ${money2(m.total_profit, true)} = ${money2(m.realized_pnl, true)} realised + ${money2(m.unrealized_pnl, true)} open − ${money2(m.fees_paid)} charges ${ok ? "✓" : "✗ does not add up"}`),
    h("div", { class: "invested" },
      h("div", {}, h("span", {}, "Most money in positions (entry price)"), h("strong", {}, money2(m.peak_position_cost)),
        h("em", { class: tone(m.return_on_position_cost) }, m.peak_position_cost ? `${pct(m.return_on_position_cost, 2, true)} return on it` : "nothing was held")),
      h("div", {}, h("span", {}, "Most cash put in (start − lowest cash)"), h("strong", {}, money2(m.peak_cash_in)),
        h("em", { class: tone(m.return_on_cash ?? 0) }, m.return_on_cash == null ? "no cash was drawn, so no %" : `${pct(m.return_on_cash, 2, true)} return on it`))),
    h("p", { class: "sub settings-line" }, [
      `P&L: ${s.pnl_method}`, `fills at ${s.fill_price}`, `weeks ${s.week}`,
      `charges ${Number(s.fee_pct)}% per order`, `selling first ${s.allow_short ? "allowed" : "off"}`,
      `max lots ${Number(s.max_position) || "no limit"}`, `cash below 0 ${s.limit_to_cash ? "not allowed" : "allowed"}`,
      r.inverted ? "INVERSE run" : "",
    ].filter(Boolean).join(" · ")));
}
