import type { CapitalPoint, DateWindow, Metrics, Thresholds } from "../api/types";
import { h } from "../lib/dom";
import { money, num, pct, plural, tone } from "../lib/format";

type Tone = "up" | "down" | "flat";
interface Metric { label: string; hint?: string; value: (m: Metrics) => string; tone?: (m: Metrics) => Tone }
interface Group { title: string; metrics: Metric[] }

const at = (p: CapitalPoint) => `${money(p.value, true)} · ${p.date}`;
const win = (w: DateWindow) => (w.bars ? `${plural(w.days, "day")} (${w.start} → ${w.end})` : "none");
const winRet = (w: DateWindow) => (w.bars ? `${pct(w.value ?? 0, 1, true)} over ${plural(w.days, "day")}` : "none");

/** Add or reorder metrics here; the UI is generated from this table. */
const groups = (t: Thresholds): Group[] => [
  { title: "Capital", metrics: [
    { label: "Starting capital", value: (m) => money(m.initial_capital) },
    { label: "Lowest cash balance", hint: "Most negative (or lowest) cash you had; if you started with 0 this is the money you had to put in", value: (m) => at(m.min_cash), tone: (m) => tone(m.min_cash.value) },
    { label: "Highest cash balance", hint: "Most cash you held at any point", value: (m) => at(m.max_cash), tone: (m) => tone(m.max_cash.value) },
    { label: "Most cash invested at once", hint: "Starting capital minus lowest cash balance", value: (m) => money(m.max_cash_invested) },
    { label: "Peak net worth", hint: "Cash plus value of holdings, at its best", value: (m) => at(m.peak_equity), tone: (m) => tone(m.peak_equity.value - m.initial_capital) },
    { label: "Worst net worth", value: (m) => at(m.lowest_equity), tone: (m) => tone(m.lowest_equity.value - m.initial_capital) },
    { label: "Largest holdings value", hint: "Biggest position value at one time", value: (m) => money(m.max_exposure) },
    { label: "Lots held at end", value: (m) => String(m.final_position) },
    { label: "Returns measured against", hint: "Starting capital, or your peak holdings value if you started with 0", value: (m) => money(m.return_base) },
  ] },
  { title: "Profit", metrics: [
    { label: "Total profit", value: (m) => money(m.total_profit, true), tone: (m) => tone(m.total_profit) },
    { label: "Total return", value: (m) => pct(m.total_return, 1, true), tone: (m) => tone(m.total_return) },
    { label: "Annualised (CAGR)", value: (m) => pct(m.cagr, 1, true), tone: (m) => tone(m.cagr) },
    { label: "Gross profit", hint: "Sum of all winning trades", value: (m) => money(m.gross_profit), tone: () => "up" },
    { label: "Total loss", hint: "Sum of all losing trades", value: (m) => money(m.gross_loss), tone: (m) => (m.gross_loss < 0 ? "down" : "flat") },
    { label: "Charges paid", value: (m) => money(m.fees_paid) },
    { label: "Charge drag", hint: "Return lost to charges", value: (m) => pct(m.fee_drag, 1) },
    { label: "Buy & hold return", value: (m) => pct(m.benchmark_return, 1, true), tone: (m) => tone(m.benchmark_return) },
    { label: "Beat buy & hold by", value: (m) => pct(m.alpha, 1, true), tone: (m) => tone(m.alpha) },
  ] },
  { title: "Risk", metrics: [
    { label: "Max drawdown", value: (m) => `${money(m.max_drawdown_amount)} (${pct(m.max_drawdown, 1)})`, tone: () => "down" },
    { label: "Average drawdown", value: (m) => pct(m.avg_drawdown, 1) },
    { label: "Volatility (annual)", value: (m) => pct(m.volatility, 1) },
    { label: "Sharpe ratio", hint: "Return per unit of risk", value: (m) => num(m.sharpe), tone: (m) => tone(m.sharpe - t.good_sharpe) },
    { label: "Sortino ratio", hint: "Like Sharpe, only penalises losses", value: (m) => num(m.sortino) },
    { label: "Calmar ratio", hint: "CAGR / max drawdown", value: (m) => num(m.calmar) },
    { label: "Daily value at risk", hint: "Loss level that the worst days exceed (percentile set in config)", value: (m) => pct(m.daily_var, 2) },
  ] },
  { title: "Trades", metrics: [
    { label: "Round-trip trades", hint: "Buys matched with later sells (first in, first out)", value: (m) => String(m.trades) },
    { label: "Orders filled", value: (m) => String(m.fills) },
    { label: "Win rate", value: (m) => pct(m.win_rate, 0), tone: (m) => tone(m.win_rate - t.good_win_rate) },
    { label: "Profit factor", hint: "Gross profit / gross loss", value: (m) => num(m.profit_factor), tone: (m) => tone(m.profit_factor - 1) },
    { label: "Average win", value: (m) => pct(m.avg_win, 2, true), tone: () => "up" },
    { label: "Average loss", value: (m) => pct(m.avg_loss, 2, true), tone: () => "down" },
    { label: "Payoff ratio", hint: "Average win / average loss", value: (m) => num(m.payoff_ratio) },
    { label: "Expectancy per trade", value: (m) => pct(m.expectancy, 2, true), tone: (m) => tone(m.expectancy) },
    { label: "Best trade", value: (m) => pct(m.best_trade, 1, true), tone: () => "up" },
    { label: "Worst trade", value: (m) => pct(m.worst_trade, 1, true), tone: () => "down" },
    { label: "Avg holding time", value: (m) => `${m.avg_holding_days.toFixed(1)} days` },
    { label: "Longest win streak", value: (m) => String(m.max_win_streak) },
    { label: "Longest loss streak", value: (m) => String(m.max_loss_streak) },
    { label: "Time in market", value: (m) => pct(m.exposure, 0) },
  ] },
  { title: "Rhythm", metrics: [
    { label: "Profitable days", value: (m) => pct(m.positive_days, 0) },
    { label: "Best day", value: (m) => pct(m.best_day, 2, true), tone: () => "up" },
    { label: "Worst day", value: (m) => pct(m.worst_day, 2, true), tone: () => "down" },
    { label: "Profitable months", value: (m) => pct(m.positive_months, 0) },
    { label: "Best month", value: (m) => pct(m.best_month, 1, true), tone: () => "up" },
    { label: "Worst month", value: (m) => pct(m.worst_month, 1, true), tone: () => "down" },
  ] },
  { title: "Windows", metrics: [
    { label: "Best profit stretch", hint: "Most profitable continuous period", value: (m) => winRet(m.best_window), tone: () => "up" },
    { label: "Worst loss stretch", hint: "Most painful continuous period", value: (m) => winRet(m.worst_window), tone: () => "down" },
    { label: "Longest time in profit", hint: "Equity above starting capital", value: (m) => win(m.longest_in_profit), tone: () => "up" },
    { label: "Longest time in loss", hint: "Equity below starting capital", value: (m) => win(m.longest_in_loss), tone: () => "down" },
    { label: "Longest underwater", hint: "Time to recover a drawdown", value: (m) => win(m.longest_drawdown), tone: () => "down" },
  ] },
];

const hero = (t: Thresholds): Metric[] => [
  { label: "Total profit", value: (m) => money(m.total_profit, true), tone: (m) => tone(m.total_profit) },
  { label: "Return", value: (m) => pct(m.total_return, 1, true), tone: (m) => tone(m.total_return) },
  { label: "Lowest cash", value: (m) => money(m.min_cash.value, true), tone: (m) => tone(m.min_cash.value) },
  { label: "Highest cash", value: (m) => money(m.max_cash.value, true), tone: (m) => tone(m.max_cash.value) },
  { label: "Peak net worth", value: (m) => money(m.peak_equity.value, true), tone: (m) => tone(m.peak_equity.value - m.initial_capital) },
  { label: "Max drawdown", value: (m) => money(m.max_drawdown_amount), tone: () => "down" },
  { label: "Win rate", value: (m) => `${pct(m.win_rate, 0)} of ${m.trades}`, tone: (m) => tone(m.win_rate - t.good_win_rate) },
  { label: "vs buy & hold", value: (m) => pct(m.alpha, 1, true), tone: (m) => tone(m.alpha) },
];

export const heroCards = (m: Metrics, t: Thresholds) =>
  h("div", { class: "hero" }, hero(t).map((k) => h("div", { class: `kpi ${k.tone?.(m) ?? "flat"}` },
    h("span", { class: "kpi-label" }, k.label), h("strong", {}, k.value(m)))));

export const metricGroups = (m: Metrics, t: Thresholds) =>
  h("div", { class: "metric-groups" }, groups(t).map((g) => h("section", { class: "panel metric-group" },
    h("h3", {}, g.title),
    h("dl", {}, g.metrics.map((x) => h("div", { class: "metric", title: x.hint ?? "" },
      h("dt", {}, x.label), h("dd", { class: x.tone?.(m) ?? "flat" }, x.value(m))))))));
