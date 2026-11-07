import type { ChartConfiguration } from "chart.js";
import { api, ApiError } from "../api/client";
import type { BuilderCatalog, RuleEvent, RuleTestResult, SymbolInfo, TradeRule } from "../api/types";
import { canvasChart, dateAxis } from "../charts/panel";
import { field, select } from "../components/controls";
import { c, table } from "../components/ledger";
import { resultsHead } from "../components/resultsHead";
import { RuleEditor } from "../components/ruleEditor";
import { debounce, h } from "../lib/dom";
import { price } from "../lib/format";
import { onSavedChange, rulesNow } from "../lib/savedStrategies";
import { color } from "../lib/theme";
import { ui } from "../lib/uiConfig";

const longDate = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(ui().currency.locale, { day: "2-digit", month: "short", year: "numeric" });

/** One rule at a time: on which days would this rule place its order, and why? No money, no other rules. */
export async function testRulePage(root: HTMLElement): Promise<void> {
  const [symbols, catalog, periods] = await Promise.all([api.symbols(), api.ruleBuilder(), api.strategies().then((s) => s.periods)]);
  if (!symbols.length) {
    root.append(h("div", { class: "panel empty" }, "No price data has been uploaded yet. An admin can add it from the Admin page."));
    return;
  }
  const state = { symbol: symbols[0].symbol, period: "1Y" };
  let rule: TradeRule = structuredClone({ ...ui().new_rule, action: "buy", conditions: [structuredClone(ui().new_condition.buy)] });
  const form = h("aside", { class: "panel controls" });
  const results = h("div", { class: "results" });
  root.append(h("div", { class: "layout" }, form, results));
  let cleanup: (() => void) | null = null;
  let seq = 0;
  const rerun = debounce(() => void run(), 300);

  const drawForm = () => {
    const saved = rulesNow();
    const editor = new RuleEditor(catalog as BuilderCatalog, rule, { onChange: rerun, onStructure: rerun });
    form.replaceChildren(
      h("h2", {}, "Test a rule"),
      h("p", { class: "hint" }, "See every day one rule would place its order, and why. Nothing else is applied: no money, no other rules."),
      field("Instrument", select((symbols as SymbolInfo[]).map((s) => ({ value: s.symbol, label: `${s.symbol} · ${s.rows.toLocaleString()} days` })), state.symbol,
        (v) => { state.symbol = v; void run(); })),
      field("Period", select(periods.map((p) => ({ value: p, label: p })), state.period, (v) => { state.period = v; void run(); })),
      field("Load one of your saved rules", h("select", { disabled: !saved.length, on: { change: (e) => {
        const s = saved.find((x) => x.id === Number((e.target as HTMLSelectElement).value));
        if (!s) return;
        const { used_by: _ignored, ...r } = s;
        rule = structuredClone(r);
        drawForm(); void run();
      } } }, h("option", { value: "" }, saved.length ? "Choose a rule..." : "No saved rules yet"),
        saved.map((s) => h("option", { value: String(s.id) }, `${s.action === "buy" ? "Buy" : "Sell"} · ${s.name}`)))),
      h("button", { type: "button", class: "btn ghost block", on: { click: () => {
        rule = structuredClone({ ...ui().new_rule, action: "buy", conditions: [structuredClone(ui().new_condition.buy)] });
        drawForm(); void run();
      } } }, "Start a new rule"),
      h("h2", { class: "spaced" }, "The rule"),
      editor.el);
  };

  async function run() {
    const mine = ++seq;
    results.classList.add("loading");
    try {
      const r = await api.ruleTest({ symbol: state.symbol, rule, period: state.period });
      if (mine === seq) show(r);
    } catch (e) {
      if (mine === seq) results.replaceChildren(h("div", { class: "panel error" }, e instanceof ApiError ? e.message : "Something went wrong"));
    } finally {
      if (mine === seq) results.classList.remove("loading");
    }
  }

  function show(r: RuleTestResult) {
    cleanup?.();
    const s = r.rules[0];
    const verb = rule.action === "buy" ? "buy" : "sell";
    const chartBody = h("div", { class: "panel-body" });
    const cols = [
      c<RuleEvent>("Date", (e) => e.date, (e) => longDate(e.date)),
      c<RuleEvent>("You will", (e) => `${e.action} ${e.lots}`, (e) => h("span", { class: `tag ${e.action === "buy" ? "long" : "short"}` }, `${e.action} ${e.lots} lot${e.lots === 1 ? "" : "s"}`)),
      c<RuleEvent>("Close that day", (e) => e.close, (e) => price(e.close)),
      c<RuleEvent>("Because", (e) => e.reason, (e) => e.reason, () => "small reason"),
    ];
    results.replaceChildren(
      resultsHead(s.sentence, r.symbol, r.start, r.end, [`True on ${s.days} of ${r.bars.toLocaleString()} trading days`]),
      h("section", { class: "panel" }, h("h3", {}, s.days ? `When you will ${verb}` : `This rule never triggers in this period`),
        h("ul", { class: "will-list" }, r.events.slice(0, 10).map((e) => h("li", {},
          h("strong", { class: e.action === "buy" ? "up" : "down" }, `You will ${verb} ${e.lots} lot${e.lots === 1 ? "" : "s"} on ${longDate(e.date)}`),
          h("span", { class: "sub" }, ` · close ${price(e.close)} · ${e.reason}`)))),
        r.events.length > 10 && h("p", { class: "hint" }, `…and ${r.events.length - 10} more days in the table below.`),
        h("p", { class: "hint" }, r.note)),
      h("section", { class: "panel chart-panel wide" }, h("div", { class: "panel-head" }, h("h3", {}, "Where it triggers on the price"),
        h("span", { class: "sub" }, verb === "buy" ? "▲ = you buy at that day's close" : "▼ = you sell at that day's close")), chartBody),
      h("section", { class: "panel" }, h("div", { class: "panel-head" }, h("h3", {}, "Every day it triggers"), h("span", { class: "sub" }, "Oldest first")),
        table(cols, r.events, ui().thresholds.page_size, `${r.symbol}-${(rule.name || "rule").replace(/\W+/g, "-")}.csv`)));
    const hit = new Map(r.events.map((e) => [e.date, e]));
    cleanup = canvasChart(chartBody, (): ChartConfiguration => ({
      type: "line",
      data: {
        labels: r.dates,
        datasets: [
          { label: "Close", data: r.close, borderColor: color.text, borderWidth: 1.25, pointRadius: 0 },
          { label: verb === "buy" ? "You buy" : "You sell", data: r.dates.map((d, i) => (hit.has(d) ? r.close[i] : null)), showLine: false,
            backgroundColor: verb === "buy" ? color.up : color.down, borderColor: verb === "buy" ? color.up : color.down,
            pointStyle: "triangle", pointRotation: verb === "buy" ? 0 : 180, pointRadius: 6 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, scales: { x: dateAxis },
        plugins: { tooltip: { callbacks: { afterBody: (items) => { const e = hit.get(r.dates[items[0].dataIndex]); return e ? [`You ${verb} ${e.lots}: ${e.reason}`] : []; } } } },
      },
    }));
  }

  onSavedChange(() => drawForm());
  drawForm();
  await run();
}
