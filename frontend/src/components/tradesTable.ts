import type { Trade } from "../api/types";
import { h } from "../lib/dom";
import { money, pct, tone } from "../lib/format";

export function tradesTable(trades: Trade[], maxRows: number): HTMLElement {
  const rows = [...trades].reverse().slice(0, maxRows);
  return h("section", { class: "panel" },
    h("div", { class: "panel-head" }, h("h3", {}, "Trade log"), h("span", { class: "sub" }, `${trades.length} trades${trades.length > rows.length ? " · latest ${maxRows} shown" : ""}`)),
    h("div", { class: "table-scroll tall" }, h("table", { class: "data" },
      h("thead", {}, h("tr", {}, ["Side", "Lots", "Entry", "Exit", "Entry $", "Exit $", "Days", "Return", "P&L"].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((t) => h("tr", {},
        h("td", {}, h("span", { class: `tag ${t.side}` }, t.side)), h("td", {}, t.qty),
        h("td", {}, t.entry_date), h("td", {}, t.is_open ? "open" : t.exit_date),
        h("td", {}, t.entry_price.toFixed(2)), h("td", {}, t.exit_price.toFixed(2)), h("td", {}, t.days),
        h("td", { class: tone(t.return_pct) }, pct(t.return_pct, 2, true)),
        h("td", { class: tone(t.pnl) }, money(t.pnl, true))))))));
}
