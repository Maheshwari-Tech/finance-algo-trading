import type { BacktestResult, Thresholds } from "../api/types";
import { h } from "../lib/dom";
import { money, pct, plural } from "../lib/format";

/** Plain-English takeaways so beginners do not need to read every number. */
export function insights(r: BacktestResult, t: Thresholds): HTMLElement {
  const m = r.metrics, w = r.windows;
  const lines: { kind: "good" | "bad" | "info"; text: string }[] = [];
  lines.push(m.min_cash.value < 0
    ? { kind: "info", text: `You would have needed up to ${money(m.peak_cash_in)} of cash at once (lowest cash ${money(m.min_cash.value)} on ${m.min_cash.date}).` }
    : { kind: "info", text: `Cash never went negative; lowest balance was ${money(m.min_cash.value)}.` });
  lines.push(m.alpha >= 0
    ? { kind: "good", text: `Beat buy & hold by ${pct(m.alpha, 1)} (${pct(m.total_return, 1, true)} vs ${pct(m.benchmark_return, 1, true)}).` }
    : { kind: "bad", text: `Trailed buy & hold by ${pct(-m.alpha, 1)} (${pct(m.total_return, 1, true)} vs ${pct(m.benchmark_return, 1, true)}).` });
  if (w.always_profitable_bars) lines.push({ kind: "good", text: `Any ${plural(w.always_profitable_bars, "day")} stretch of running this was profitable, from every start date tested.` });
  else lines.push({ kind: "bad", text: "There is no holding length where this strategy was always profitable." });
  const be = r.fees.breakeven_fee_pct;
  if (be != null) lines.push({ kind: be < t.low_breakeven_fee_pct ? "bad" : "info", text: `Charges of more than ${be.toFixed(2)}% per trade would wipe out the profit.` });
  if (m.fees_paid > Math.abs(m.total_profit) && m.total_profit !== 0) lines.push({ kind: "bad", text: `Charges (${money(m.fees_paid)}) are larger than the net result - this strategy trades too often.` });
  if (m.max_drawdown < -t.deep_drawdown) lines.push({ kind: "bad", text: `Deep drawdown of ${pct(m.max_drawdown, 0)}: expect to sit through large losses.` });
  if (m.fills < t.few_fills) lines.push({ kind: "info", text: "Few trades - treat these statistics as anecdotal rather than proof." });
  return h("section", { class: "panel insights" }, h("h3", {}, "Takeaways"),
    h("ul", {}, lines.map((l) => h("li", { class: l.kind }, l.text))));
}
