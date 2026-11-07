import type { ChartConfiguration } from "chart.js";
import { api, ApiError } from "../api/client";
import type { BacktestRequest, BacktestResult, Metrics, ParamValues, StrategyInfo } from "../api/types";
import { canvasChart, dateAxis } from "../charts/panel";
import { field, numberInput, select, toggle } from "../components/controls";
import { resultsHead } from "../components/resultsHead";
import { h } from "../lib/dom";
import { money2, pct, tone } from "../lib/format";
import { handOff } from "../lib/handoff";
import { savedNow } from "../lib/savedStrategies";
import { color } from "../lib/theme";
import { ui } from "../lib/uiConfig";

interface Row { label: string; hint?: string; value: (r: BacktestResult) => number | null; fmt: (v: number) => string; better?: "higher" | "lower" }

const m = (pick: (x: Metrics) => number | null) => (r: BacktestResult) => pick(r.metrics);
const ROWS: Row[] = [
  { label: "Total profit", value: m((x) => x.total_profit), fmt: (v) => money2(v, true), better: "higher" },
  { label: "Realised P&L", hint: "Closed positions, before charges", value: m((x) => x.realized_pnl), fmt: (v) => money2(v, true) },
  { label: "Open P&L", hint: "Still held, at the last close", value: m((x) => x.unrealized_pnl), fmt: (v) => money2(v, true) },
  { label: "Charges", value: m((x) => x.fees_paid), fmt: (v) => money2(v), better: "lower" },
  { label: "Net worth at end", value: m((x) => x.final_equity), fmt: (v) => money2(v) },
  { label: "Most money in positions", hint: "At entry price", value: m((x) => x.peak_position_cost), fmt: (v) => money2(v) },
  { label: "Return on money in positions", value: m((x) => x.return_on_position_cost), fmt: (v) => pct(v, 2, true), better: "higher" },
  { label: "Most cash put in", value: m((x) => x.peak_cash_in), fmt: (v) => money2(v) },
  { label: "Return on cash put in", value: m((x) => x.return_on_cash), fmt: (v) => pct(v, 2, true), better: "higher" },
  { label: "Lowest cash", value: m((x) => x.min_cash.value), fmt: (v) => money2(v, true) },
  { label: "Max drawdown", hint: "Biggest fall from a previous net worth peak", value: m((x) => x.max_drawdown_amount), fmt: (v) => money2(v), better: "higher" },
  { label: "Orders filled", value: m((x) => x.fills), fmt: (v) => v.toLocaleString() },
  { label: "Trades", value: m((x) => x.trades), fmt: (v) => v.toLocaleString() },
  { label: "Win rate", value: m((x) => x.win_rate), fmt: (v) => pct(v, 0), better: "higher" },
  { label: "Lots held at end", value: m((x) => x.final_position), fmt: (v) => String(v) },
  { label: "Strategy + its inverse", hint: "Should be minus the charges of both runs (never positive) when it is an exact mirror", value: (r) => r.mirror.total, fmt: (v) => money2(v, true) },
];

type Pick = { kind: "builtin"; id: string } | { kind: "saved"; name: string };

/** Compare two strategies that are already built (built-in or saved) on the same prices, period and money settings. */
export async function comparePage(root: HTMLElement): Promise<void> {
  const [symbols, catalog] = await Promise.all([api.symbols(), api.strategies()]);
  if (!symbols.length) {
    root.append(h("div", { class: "panel empty" }, "No price data has been uploaded yet. An admin can add it from the Admin page."));
    return;
  }
  const d = ui().defaults;
  const saved = savedNow();
  const options = [
    ...catalog.strategies.map((s) => ({ value: `b:${s.id}`, label: `${s.name} (built-in, default settings)` })),
    ...saved.map((s) => ({ value: `s:${s.name}`, label: `★ ${s.name} (saved)` })),
  ];
  const parse = (v: string): Pick => (v.startsWith("s:") ? { kind: "saved", name: v.slice(2) } : { kind: "builtin", id: v.slice(2) });
  const picks: [string, string] = [options[0].value, (options[1] ?? options[0]).value];
  const shared = { symbol: symbols[0].symbol, period: d.period as string | undefined, initial_capital: d.initial_capital, lots: d.lots,
    max_position: d.max_position, allow_short: d.allow_short, limit_to_cash: d.limit_to_cash, charges_enabled: d.charges_enabled, fee_pct: d.fee_pct };

  const form = h("aside", { class: "panel controls" });
  const results = h("div", { class: "results" });
  root.append(h("div", { class: "layout" }, form, results));
  let cleanup: (() => void) | null = null;
  let seq = 0;

  const request = (p: Pick): BacktestRequest => {
    const base = { ...shared, strategy_id: "custom", params: {} as ParamValues, invert: false };
    if (p.kind === "saved") return { ...base, rules: structuredClone(saved.find((s) => s.name === p.name)!) };
    const s = catalog.strategies.find((x) => x.id === p.id) as StrategyInfo;
    return { ...base, strategy_id: s.id, params: Object.fromEntries(s.params.map((x) => [x.key, x.default])) };
  };

  const set = <K extends keyof typeof shared>(k: K, v: (typeof shared)[K]) => { shared[k] = v; void run(); };
  const drawForm = () => {
    const L = ui().limits;
    form.replaceChildren(
      h("h2", {}, "Compare two strategies"),
      field("Strategy A", select(options, picks[0], (v) => { picks[0] = v; void run(); })),
      field("Strategy B", select(options, picks[1], (v) => { picks[1] = v; void run(); })),
      h("p", { class: "hint" }, saved.length ? "Built-in strategies use their default settings. Save your own on the Strategy page to compare them here."
        : "Save your own rule sets on the Strategy page to compare them here."),
      h("h2", { class: "spaced" }, "Same for both"),
      field("Instrument", select(symbols.map((s) => ({ value: s.symbol, label: s.symbol })), shared.symbol, (v) => set("symbol", v))),
      field("Period", select(catalog.periods.map((p) => ({ value: p, label: p })), shared.period ?? "MAX", (v) => set("period", v))),
      field(`Starting capital (${ui().currency.symbol})`, numberInput(shared.initial_capital, L.initial_capital, (v) => set("initial_capital", v))),
      field("Lots per position (built-in)", numberInput(shared.lots, L.lots, (v) => set("lots", Math.round(v)))),
      field("Max lots held (0 = no limit)", numberInput(shared.max_position, L.max_position, (v) => set("max_position", Math.round(v)))),
      toggle("Allow selling before buying", "A sell with nothing to sell opens a short position.", shared.allow_short, (v) => set("allow_short", v)),
      toggle("Don't let cash go below 0", "Buys are cut to what cash can pay for.", shared.limit_to_cash, (v) => set("limit_to_cash", v)),
      toggle("Apply charges", "A % of traded value on every buy and sell.", shared.charges_enabled, (v) => { shared.charges_enabled = v; drawForm(); void run(); }),
      ...(shared.charges_enabled ? [field("Charge per trade (%)", numberInput(shared.fee_pct, L.fee_pct, (v) => set("fee_pct", v)))] : []));
  };

  async function run() {
    const mine = ++seq;
    results.classList.add("loading");
    const reqs = [request(parse(picks[0])), request(parse(picks[1]))] as const;
    try {
      const [a, b] = await Promise.all(reqs.map((r) => api.backtest(r)));
      if (mine === seq) show(a, b, reqs);
    } catch (e) {
      if (mine === seq) results.replaceChildren(h("div", { class: "panel error" }, e instanceof ApiError ? e.message : "Something went wrong"));
    } finally {
      if (mine === seq) results.classList.remove("loading");
    }
  }

  function show(a: BacktestResult, b: BacktestResult, reqs: readonly [BacktestRequest, BacktestRequest]) {
    cleanup?.();
    const failed = (r: BacktestResult) => r.checks.filter((x) => !x.ok).length + (r.mirror.ok ? 0 : 1);
    const cell = (row: Row, r: BacktestResult, other: BacktestResult) => {
      const v = row.value(r), o = row.value(other);
      const wins = row.better && v != null && o != null && v !== o && (row.better === "higher" ? v > o : v < o);
      return h("td", { class: `${v == null ? "" : tone(v)}${wins ? " better" : ""}` }, v == null ? "n/a" : row.fmt(v));
    };
    const chartBody = h("div", { class: "panel-body" });
    results.replaceChildren(
      resultsHead(`${a.strategy_name} vs ${b.strategy_name}`, a.symbol, a.start, a.end, [`${a.bars.toLocaleString()} trading days`, "Same money settings for both"]),
      h("section", { class: "panel" }, h("div", { class: "table-scroll" }, h("table", { class: "data compare" },
        h("thead", {}, h("tr", {}, h("th", {}, ""), h("th", {}, `A · ${a.strategy_name}`), h("th", {}, `B · ${b.strategy_name}`), h("th", {}, "B − A"))),
        h("tbody", {},
          ROWS.map((row) => {
            const va = row.value(a), vb = row.value(b);
            return h("tr", { title: row.hint ?? "" }, h("td", { class: "label" }, row.label), cell(row, a, b), cell(row, b, a),
              h("td", { class: "muted" }, va == null || vb == null ? "" : row.fmt(vb - va)));
          }),
          h("tr", {}, h("td", { class: "label" }, "Checks"),
            ...[a, b].map((r) => h("td", { class: failed(r) ? "down" : "up" }, failed(r) ? `✗ ${failed(r)} failed` : `✓ all ${r.checks.length + 1} pass`)), h("td", {}, "")),
          h("tr", {}, h("td", { class: "label" }, ""),
            ...reqs.map((q) => h("td", {}, h("button", { class: "btn ghost", on: { click: () => handOff(q, "/") } }, "Open orders & trades →"))), h("td", {}, ""))))),
        h("p", { class: "hint" }, "Green marks the better of the two where higher or lower is clearly better. Every number comes from the same calculation as the Strategy page; open either one there to check its orders.")),
      h("section", { class: "panel chart-panel wide" }, h("div", { class: "panel-head" }, h("h3", {}, "Net worth over time"), h("span", { class: "sub" }, "Cash + value of holdings")), chartBody));
    cleanup = canvasChart(chartBody, (): ChartConfiguration => ({
      type: "line",
      data: { labels: a.series.dates, datasets: [
        { label: `A · ${a.strategy_name}`, data: a.series.equity, borderColor: color.accent, borderWidth: 2, pointRadius: 0 },
        { label: `B · ${b.strategy_name}`, data: b.series.equity, borderColor: color.accent2, borderWidth: 2, pointRadius: 0 },
      ] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, scales: { x: dateAxis } },
    }));
  }

  drawForm();
  await run();
}
