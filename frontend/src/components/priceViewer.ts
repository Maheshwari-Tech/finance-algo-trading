import { api, ApiError } from "../api/client";
import type { PricePage } from "../api/types";
import { h } from "../lib/dom";
import { price } from "../lib/format";

const SIZES = [10, 20, 50, 100];

/** Stored prices of one instrument: paged, with date range, close range and order filters. */
export function priceViewer(symbol: string): HTMLElement {
  const q = { page: 1, size: 20, order: "newest", start: "", end: "", min_close: "", max_close: "" };
  const body = h("div");
  const input = (type: string, key: "start" | "end" | "min_close" | "max_close", placeholder: string) =>
    h("input", { type, placeholder, value: q[key], step: type === "number" ? "any" : undefined,
      on: { change: (e) => { q[key] = (e.target as HTMLInputElement).value; q.page = 1; void load(); } } });
  const filters = h("div", { class: "price-filters" },
    h("label", { class: "field" }, h("span", {}, "From"), input("date", "start", "")),
    h("label", { class: "field" }, h("span", {}, "To"), input("date", "end", "")),
    h("label", { class: "field" }, h("span", {}, "Close from (₹)"), input("number", "min_close", "any")),
    h("label", { class: "field" }, h("span", {}, "Close to (₹)"), input("number", "max_close", "any")),
    h("label", { class: "field" }, h("span", {}, "Order"), h("select", { on: { change: (e) => { q.order = (e.target as HTMLSelectElement).value; q.page = 1; void load(); } } },
      h("option", { value: "newest" }, "Newest first"), h("option", { value: "oldest" }, "Oldest first"))),
    h("label", { class: "field" }, h("span", {}, "Rows per page"), h("select", { on: { change: (e) => { q.size = Number((e.target as HTMLSelectElement).value); q.page = 1; void load(); } } },
      SIZES.map((n) => h("option", { value: String(n), selected: n === q.size }, String(n))))),
    h("button", { type: "button", class: "btn ghost", on: { click: () => {
      Object.assign(q, { page: 1, start: "", end: "", min_close: "", max_close: "" });
      filters.querySelectorAll("input").forEach((i) => { (i as HTMLInputElement).value = ""; });
      void load();
    } } }, "Clear filters"));

  const draw = (p: PricePage) => {
    const go = (page: number) => { q.page = page; void load(); };
    body.replaceChildren(
      h("div", { class: "table-tools" },
        h("span", { class: "sub" }, p.total ? `${p.total.toLocaleString()} rows · page ${p.page} of ${p.pages}` : "No rows match these filters"),
        h("div", { class: "pager" },
          h("button", { class: "btn ghost", disabled: p.page <= 1, on: { click: () => go(1) } }, "« First"),
          h("button", { class: "btn ghost", disabled: p.page <= 1, on: { click: () => go(p.page - 1) } }, "‹ Prev"),
          h("button", { class: "btn ghost", disabled: p.page >= p.pages, on: { click: () => go(p.page + 1) } }, "Next ›"),
          h("button", { class: "btn ghost", disabled: p.page >= p.pages, on: { click: () => go(p.pages) } }, "Last »"))),
      h("div", { class: "table-scroll tall" }, h("table", { class: "data" },
        h("thead", {}, h("tr", {}, ["Date", "Open", "High", "Low", "Close"].map((c) => h("th", {}, c)))),
        h("tbody", {}, p.rows.map((r) => h("tr", {}, h("td", {}, r.date), h("td", {}, price(r.open)), h("td", {}, price(r.high)),
          h("td", {}, price(r.low)), h("td", {}, h("strong", {}, price(r.close)))))))));
  };

  async function load() {
    body.classList.add("loading");
    try {
      draw(await api.datasetRows(symbol, q));
    } catch (e) {
      body.replaceChildren(h("p", { class: "msg error" }, e instanceof ApiError ? e.message : "Could not load prices"));
    } finally {
      body.classList.remove("loading");
    }
  }

  void load();
  return h("section", { class: "panel price-viewer", id: "price-viewer" },
    h("div", { class: "panel-head" }, h("h2", {}, `Prices: ${symbol}`), h("span", { class: "sub" }, "As stored, after upload")),
    filters, body);
}
