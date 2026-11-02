import { api, ApiError } from "../api/client";
import type { BacktestRequest, BacktestResult } from "../api/types";
import { PANELS } from "../charts";
import { Controls } from "../components/controls";
import { insights } from "../components/insights";
import { heroCards, metricGroups } from "../components/metrics";
import { tradesTable } from "../components/tradesTable";
import { h } from "../lib/dom";
import { ui } from "../lib/uiConfig";

export async function dashboardPage(root: HTMLElement): Promise<void> {
  const [symbols, catalog, builder] = await Promise.all([api.symbols(), api.strategies(), api.ruleBuilder()]);
  if (!symbols.length) {
    root.append(h("div", { class: "panel empty" }, "No price data has been uploaded yet. An admin can add it from the Admin page."));
    return;
  }

  const results = h("div", { class: "results" });
  const controls = new Controls(symbols, catalog, builder, (req) => void run(req));
  root.append(h("div", { class: "layout" }, controls.el, results));

  const cleanups: (() => void)[] = [];
  let seq = 0;

  async function run(req: BacktestRequest) {
    const mine = ++seq;
    results.classList.add("loading");
    try {
      const result = await api.backtest(req);
      if (mine === seq) show(result);
    } catch (e) {
      if (mine === seq) results.replaceChildren(h("div", { class: "panel error" }, e instanceof ApiError ? e.message : "Something went wrong"));
    } finally {
      if (mine === seq) results.classList.remove("loading");
    }
  }

  function show(r: BacktestResult) {
    const t = ui().thresholds;
    cleanups.splice(0).forEach((fn) => fn());
    const grid = h("div", { class: "grid" });
    for (const p of PANELS) {
      const body = h("div", { class: "panel-body" });
      grid.append(h("section", { class: `panel chart-panel${p.wide ? " wide" : ""}`, id: `panel-${p.id}` },
        h("div", { class: "panel-head" }, h("h3", {}, p.title), p.subtitle && h("span", { class: "sub" }, p.subtitle)), body));
      const cleanup = p.render(body, r);
      if (cleanup) cleanups.push(cleanup);
    }
    results.replaceChildren(
      h("div", { class: "results-head" },
        h("div", {}, h("h1", {}, `${r.strategy_name} on ${r.symbol}`), h("p", { class: "sub" }, `${r.start} → ${r.end} · ${r.bars.toLocaleString()} trading days`))),
      heroCards(r.metrics, t), insights(r, t), grid, metricGroups(r.metrics, t), tradesTable(r.trades, t.max_trade_log_rows));
  }

  await run(controls.request);
}
