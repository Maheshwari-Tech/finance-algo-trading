import { api, ApiError } from "../api/client";
import type { BacktestRequest, BacktestResult } from "../api/types";
import { PANELS } from "../charts";
import { Controls } from "../components/controls";
import { insights } from "../components/insights";
import { heroCards, metricGroups } from "../components/metrics";
import { ledgerPanel } from "../components/ledger";
import { dailyPanel, longDate, periodPanel } from "../components/overview";
import { resultsHead } from "../components/resultsHead";
import { pnlSummary } from "../components/pnl";
import { h } from "../lib/dom";
import { takeHandOff } from "../lib/handoff";
import { ui } from "../lib/uiConfig";

export async function dashboardPage(root: HTMLElement): Promise<void> {
  const [symbols, catalog, builder] = await Promise.all([api.symbols(), api.strategies(), api.ruleBuilder()]);
  if (!symbols.length) {
    root.append(h("div", { class: "panel empty" }, "No price data has been uploaded yet. An admin can add it from the Admin page."));
    return;
  }

  const results = h("div", { class: "results" });
  const controls = new Controls(symbols, catalog, builder, (req) => void run(req), "strategy", takeHandOff());
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
    const daily = dailyPanel(r, t.page_size);
    const pick = (p: { start: string; end: string; label: string }) => daily.showRange(p.start, p.end, `${p.label} (${longDate(p.start)} → ${longDate(p.end)})`);
    const sections: Section[] = [
      { id: "dash-summary", label: "Summary", el: h("div", {}, pnlSummary(r), heroCards(r.metrics, t)) },
      { id: "dash-takeaways", label: "Takeaways", el: insights(r, t) },
      { id: "dash-charts", label: "Charts", el: grid },
      { id: "dash-weekly", label: "Weekly overview", el: periodPanel("dash-weekly-panel", "Weekly overview", "What the strategy did and earned, week by week (Monday to Sunday). Click a week to see its days.", r.weeks, r.period_total, `${r.symbol}-weekly-overview.csv`, pick) },
      { id: "dash-monthly", label: "Monthly overview", el: periodPanel("dash-monthly-panel", "Monthly overview", "The same, month by month. Click a month to see its days.", r.months, r.period_total, `${r.symbol}-monthly-overview.csv`, pick) },
      { id: "dash-daily-wrap", label: "Daily transactions", el: daily.el },
      { id: "dash-ledger", label: "Orders · weeks · trades · checks", el: ledgerPanel(r, t.page_size) },
      { id: "dash-stats", label: "All statistics", el: metricGroups(r.metrics, t) },
    ];
    results.replaceChildren(
      resultsHead(r.strategy_name, r.symbol, r.start, r.end, [`${r.bars.toLocaleString()} trading days`, ...(r.inverted ? ["Inverse"] : [])]),
      dashboardNav(sections),
      ...sections.map((x) => h("div", { class: "dash-section", id: x.id, hidden: hiddenSections().has(x.id) }, x.el)));
  }

  await run(controls.request);
}

interface Section { id: string; label: string; el: HTMLElement }
const HIDDEN_KEY = "strategic-trader.hidden-sections";

/** Which dashboard sections this viewer has switched off (kept in this browser only). */
function hiddenSections(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]") as string[]); } catch { return new Set(); }
}
function saveHidden(ids: Set<string>) {
  try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([...ids])); } catch { /* storage unavailable: choice lasts until reload */ }
}

/** "Jump to" links plus "Show" switches, so each person sees just the dashboards they want. */
function dashboardNav(sections: Section[]): HTMLElement {
  const hidden = hiddenSections();
  const jump = h("div", { class: "jump-links" });
  const show = h("div", { class: "show-chips" });
  const draw = () => {
    jump.replaceChildren(h("span", { class: "sub" }, "Jump to"),
      ...sections.filter((x) => !hidden.has(x.id)).map((x) => h("a", { href: "javascript:void 0", class: "jump", on: { click: (e) => {
        e.preventDefault(); document.getElementById(x.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      } } }, x.label)));
    show.replaceChildren(h("span", { class: "sub" }, "Show"),
      ...sections.map((x) => h("button", { type: "button", class: `chip${hidden.has(x.id) ? "" : " active"}`, title: hidden.has(x.id) ? "Hidden: click to show" : "Shown: click to hide", on: { click: () => {
        if (hidden.has(x.id)) hidden.delete(x.id); else hidden.add(x.id);
        saveHidden(hidden);
        const el = document.getElementById(x.id);
        if (el) el.hidden = hidden.has(x.id);
        draw();
      } } }, x.label)),
      ...(hidden.size ? [h("button", { type: "button", class: "btn ghost small", on: { click: () => {
        hidden.clear(); saveHidden(hidden); sections.forEach((x) => { const el = document.getElementById(x.id); if (el) el.hidden = false; }); draw();
      } } }, "Show all")] : []));
  };
  draw();
  return h("nav", { class: "panel dash-nav" }, jump, show);
}
