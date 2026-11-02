import type { ChartConfiguration } from "chart.js";
import { h } from "../lib/dom";
import { color } from "../lib/theme";
import { MONTHS, pct, plural } from "../lib/format";
import { canvasChart, type ChartPanel } from "./panel";

export const windowsPanel: ChartPanel = {
  id: "windows", title: "How long should you stay in?", wide: true,
  subtitle: "For every possible start date: how often is a hold of N days profitable?",
  render: (host, r) => {
    const w = r.windows;
    host.append(h("div", { class: "callouts" },
      callout("Never lost money", w.always_profitable_bars ? `up to ${plural(w.always_profitable_bars, "day")}` : "no safe window", "up"),
      callout(`Profitable ${Math.round(w.majority_threshold * 100)}%+ of the time`, w.majority_profitable_bars ? `up to ${plural(w.majority_profitable_bars, "day")}` : "never", "accent"),
      callout("Best return per day", `holding ~${plural(w.best_hold_bars, "day")}`, "accent"),
    ));
    return canvasChart(host, (): ChartConfiguration => ({
      type: "bar",
      data: {
        labels: w.stats.map((s) => `${s.bars}d`),
        datasets: [
          { label: "% of windows profitable", data: w.stats.map((s) => s.pct_profitable * 100), backgroundColor: w.stats.map((s) => (s.pct_profitable >= w.majority_threshold ? "rgba(52,211,153,.75)" : "rgba(251,113,133,.75)")), borderRadius: 4, yAxisID: "y" },
          { type: "line", label: "Average return", data: w.stats.map((s) => s.avg_return * 100), borderColor: color.warn, pointRadius: 3, borderWidth: 2, yAxisID: "y1" },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false } },
          y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } },
          y1: { position: "right", grid: { display: false }, ticks: { callback: (v) => `${v}%` } },
        },
      },
    }));
  },
};

function callout(label: string, value: string, kind: string): HTMLElement {
  return h("div", { class: `callout ${kind}` }, h("span", { class: "callout-label" }, label), h("strong", {}, value));
}

export const feesPanel: ChartPanel = {
  id: "fees", title: "Charge sensitivity", subtitle: "Total return as the charge per trade grows",
  render: (host, r) => {
    const be = r.fees.breakeven_fee_pct;
    host.append(h("p", { class: "note" }, be == null
      ? "Not profitable even with zero charges."
      : `Break-even charge: ${be.toFixed(2)}% per trade. Above that this strategy loses money.`));
    return canvasChart(host, (): ChartConfiguration => ({
      type: "bar",
      data: {
        labels: r.fees.points.map((p) => `${p.fee_pct}%`),
        datasets: [{ data: r.fees.points.map((p) => p.total_return), backgroundColor: r.fees.points.map((p) => (p.total_return > 0 ? color.accent : color.down)), borderRadius: 4 }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, title: { display: true, text: "charge per trade" } }, y: { ticks: { callback: (v) => pct(Number(v), 0) } } } },
    }));
  },
};

export const monthlyPanel: ChartPanel = {
  id: "monthly", title: "Monthly returns", subtitle: "Spot seasonality and bad stretches at a glance", wide: true,
  render: (host, r) => {
    const years = [...new Set(r.monthly.map((m) => m.year))].sort();
    const max = Math.max(0.01, ...r.monthly.map((m) => Math.abs(m.value)));
    const lookup = new Map(r.monthly.map((m) => [`${m.year}-${m.month}`, m.value]));
    const cell = (v: number | undefined) => {
      if (v === undefined) return h("td", { class: "hm empty" });
      const a = Math.min(1, Math.abs(v) / max) * 0.85 + 0.1;
      const bg = v >= 0 ? `rgba(52,211,153,${a})` : `rgba(251,113,133,${a})`;
      return h("td", { class: "hm", style: `background:${bg}`, title: pct(v, 2, true) }, (v * 100).toFixed(1));
    };
    host.append(h("div", { class: "table-scroll" }, h("table", { class: "heatmap" },
      h("thead", {}, h("tr", {}, h("th"), MONTHS.map((m) => h("th", {}, m)))),
      h("tbody", {}, years.map((y) => h("tr", {}, h("th", {}, y), MONTHS.map((_, i) => cell(lookup.get(`${y}-${i + 1}`)))))),
    )));
  },
};

