import { h } from "../lib/dom";
import { longDate } from "./overview";

/** Page title for a result: the name on its own line, then the instrument, dates and size as quiet badges. */
export function resultsHead(title: string, symbol: string, start: string, end: string, facts: string[] = []): HTMLElement {
  return h("div", { class: "results-head" },
    h("div", { class: "results-title" },
      h("h1", {}, title),
      h("div", { class: "meta-row" },
        h("span", { class: "meta-badge symbol" }, symbol),
        h("span", { class: "meta-badge" }, `${longDate(start)} – ${longDate(end)}`),
        ...facts.map((f) => h("span", { class: "meta-badge" }, f)))));
}
