import type { ChartConfiguration } from "chart.js";
import { color, gradient } from "../lib/theme";
import { money, pct } from "../lib/format";
import { canvasChart, dateAxis, type ChartPanel } from "./panel";

export const equityPanel: ChartPanel = {
  id: "equity", title: "Net worth", subtitle: "Cash + value of holdings, compared with with/without charges and buy & hold", wide: true,
  render: (host, r) => canvasChart(host, (canvas): ChartConfiguration => {
    const charged = r.metrics.fees_paid > 0;
    return {
      type: "line",
      data: {
        labels: r.series.dates,
        datasets: [
          { label: charged ? "Strategy (after charges)" : "Strategy", data: r.series.equity, borderColor: color.accent, backgroundColor: gradient(canvas, "124,140,255"), fill: true, borderWidth: 2, pointRadius: 0, tension: 0.1 },
          ...(charged ? [{ label: "Without charges", data: r.series.equity_no_fee, borderColor: color.accent2, borderWidth: 1.5, pointRadius: 0, tension: 0.1 }] : []),
          { label: "Buy & hold", data: r.series.benchmark, borderColor: color.muted, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { x: dateAxis, y: { ticks: { callback: (v) => money(Number(v)) } } },
        plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${money(c.parsed.y ?? 0)}` } } },
      },
    };
  }),
};

export const capitalPanel: ChartPanel = {
  id: "capital", title: "Cash balance", subtitle: "Buying spends cash, selling returns it. Markers show the lowest and highest balance", wide: true,
  render: (host, r) => canvasChart(host, (): ChartConfiguration => {
    const only = (d: string, v: number) => r.series.dates.map((x) => (x === d ? v : null));
    const { min_cash: lo, max_cash: hi } = r.metrics;
    return {
      type: "line",
      data: {
        labels: r.series.dates,
        datasets: [
          { label: "Cash", data: r.series.cash, borderColor: color.accent2, borderWidth: 2, pointRadius: 0, stepped: true },
          { label: "Net worth", data: r.series.equity, borderColor: color.accent, borderWidth: 1.25, pointRadius: 0, borderDash: [4, 3] },
          { label: `Lowest cash ${money(lo.value)}`, data: only(lo.date, lo.value), showLine: false, backgroundColor: color.down, borderColor: color.down, pointRadius: 7, pointStyle: "rectRot" },
          { label: `Highest cash ${money(hi.value)}`, data: only(hi.date, hi.value), showLine: false, backgroundColor: color.up, borderColor: color.up, pointRadius: 7, pointStyle: "rectRot" },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { x: dateAxis, y: { ticks: { callback: (v) => money(Number(v)) } } },
      },
    };
  }),
};

export const positionPanel: ChartPanel = {
  id: "position", title: "Lots held", subtitle: "Your position over time (negative = short)",
  render: (host, r) => canvasChart(host, (): ChartConfiguration => ({
    type: "line",
    data: { labels: r.series.dates, datasets: [{ label: "Lots", data: r.series.position, borderColor: color.warn, backgroundColor: "rgba(251,191,36,.15)", fill: true, borderWidth: 1.5, pointRadius: 0, stepped: true }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: dateAxis } },
  })),
};

export const pricePanel: ChartPanel = {
  id: "price", title: "Price & trades", subtitle: "Every buy and sell, filled at the closing price", wide: true,
  render: (host, r) => canvasChart(host, (): ChartConfiguration => {
    const marks = (pick: (i: number) => boolean) => r.series.close.map((y, i) => (pick(i) ? y : null));
    const buys = marks((i) => r.series.order[i] > 0), sells = marks((i) => r.series.order[i] < 0);
    return {
      type: "line",
      data: {
        labels: r.series.dates,
        datasets: [
          { label: "Close", data: r.series.close, borderColor: color.text, borderWidth: 1.25, pointRadius: 0 },
          { label: "Buy", data: buys, showLine: false, backgroundColor: color.up, borderColor: color.up, pointStyle: "triangle", pointRadius: 5 },
          { label: "Sell", data: sells, showLine: false, backgroundColor: color.down, borderColor: color.down, pointStyle: "triangle", pointRotation: 180, pointRadius: 5 },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, scales: { x: dateAxis } },
    };
  }),
};

export const drawdownPanel: ChartPanel = {
  id: "drawdown", title: "Drawdown", subtitle: "Distance from the previous equity peak",
  render: (host, r) => canvasChart(host, (canvas): ChartConfiguration => ({
    type: "line",
    data: { labels: r.series.dates, datasets: [{ label: "Drawdown", data: r.series.drawdown, borderColor: color.down, backgroundColor: gradient(canvas, "251,113,133", 0.4), fill: true, borderWidth: 1.5, pointRadius: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => pct(c.parsed.y ?? 0, 2) } } },
      scales: { x: dateAxis, y: { ticks: { callback: (v) => pct(Number(v), 0) } } },
    },
  })),
};

export const tradesPanel: ChartPanel = {
  id: "trades", title: "Trade results", subtitle: "Net return of each trade, in order",
  render: (host, r) => canvasChart(host, (): ChartConfiguration => ({
    type: "bar",
    data: {
      labels: r.trades.map((t, i) => `#${i + 1} ${t.entry_date}`),
      datasets: [{ data: r.trades.map((t) => t.return_pct), backgroundColor: r.trades.map((t) => (t.return_pct > 0 ? color.up : color.down)), borderRadius: 3 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => pct(c.parsed.y ?? 0, 2, true) } } },
      scales: { x: { display: false }, y: { ticks: { callback: (v) => pct(Number(v), 0) } } },
    },
  })),
};

export const histogramPanel: ChartPanel = {
  id: "histogram", title: "Daily return distribution", subtitle: "How lumpy are the days?",
  render: (host, r) => canvasChart(host, (): ChartConfiguration => {
    const { edges, counts } = r.return_histogram;
    const mids = counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    return {
      type: "bar",
      data: { labels: mids.map((m) => pct(m, 1)), datasets: [{ data: counts, backgroundColor: mids.map((m) => (m >= 0 ? color.up : color.down)), borderRadius: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { maxTicksLimit: 7, maxRotation: 0 }, grid: { display: false } } } },
    };
  }),
};
