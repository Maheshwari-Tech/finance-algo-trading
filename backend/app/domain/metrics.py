from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from ..appconfig import AnalysisConfig
from .engine import Simulation
from .results import CapitalPoint, DateWindow, Metrics, MonthlyReturn


def longest_run(mask: np.ndarray) -> Tuple[int, int, int]:
    """Longest run of True: (length, start_idx, end_idx). Length 0 if none."""
    best = (0, 0, 0)
    start = None
    for i, v in enumerate(np.append(mask, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start > best[0]:
                best = (i - start, start, i - 1)
            start = None
    return best


def _window(idx: pd.DatetimeIndex, run: Tuple[int, int, int], value: float = None) -> DateWindow:
    length, s, e = run
    if length == 0:
        return DateWindow()
    return DateWindow(start=idx[s].strftime("%Y-%m-%d"), end=idx[e].strftime("%Y-%m-%d"),
                      bars=length, days=(idx[e] - idx[s]).days + 1, value=value)


def _extreme_window(idx: pd.DatetimeIndex, daily: np.ndarray, best: bool) -> DateWindow:
    """Kadane over daily results: the contiguous period with the largest gain (or loss)."""
    vals = daily if best else -daily
    cur, cur_start, top, span = 0.0, 0, 0.0, (0, 0)
    for i, x in enumerate(vals):
        if cur <= 0:
            cur, cur_start = x, i
        else:
            cur += x
        if cur > top:
            top, span = cur, (cur_start, i)
    if top <= 0:
        return DateWindow()
    return _window(idx, (span[1] - span[0] + 1, span[0], span[1]), float(top if best else -top))


def _streak(values: List[bool], target: bool) -> int:
    best = cur = 0
    for v in values:
        cur = cur + 1 if v == target else 0
        best = max(best, cur)
    return best


def monthly_returns(ret: pd.Series) -> List[MonthlyReturn]:
    m = ret.groupby([ret.index.year, ret.index.month]).sum()
    return [MonthlyReturn(year=int(y), month=int(mo), value=float(v)) for (y, mo), v in m.items()]


def _point(f: pd.DataFrame, col: str, kind: str) -> CapitalPoint:
    i = int(getattr(f[col].to_numpy(), "argmin" if kind == "min" else "argmax")())
    return CapitalPoint(value=float(f[col].iloc[i]), date=f.index[i].strftime("%Y-%m-%d"))


def compute_metrics(sim: Simulation, monthly: List[MonthlyReturn], cfg: AnalysisConfig) -> Metrics:
    TRADING_DAYS = cfg.trading_days_per_year
    f, idx, trades, base = sim.frame, sim.frame.index, sim.trades, sim.return_base
    capital = sim.cfg.initial_capital
    ret, eq = f["ret"], f["equity"].to_numpy()
    years = max((idx[-1] - idx[0]).days / 365.25, 1 / 365.25)
    final = float(eq[-1])
    profit = final - capital
    total_ret = profit / base
    cagr = (1 + total_ret) ** (1 / years) - 1 if total_ret > -1 else -1.0
    bench_ret = float(f["benchmark"].iloc[-1] - capital) / base
    vol = float(ret.std(ddof=0) * np.sqrt(TRADING_DAYS))
    downside = float(ret[ret < 0].std(ddof=0) * np.sqrt(TRADING_DAYS)) if (ret < 0).sum() > 1 else 0.0
    dd = f["drawdown"].to_numpy()
    mdd = float(dd.min())
    fees = float(f["fee"].sum())

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gp, gl = sum(t.pnl for t in wins), sum(t.pnl for t in losses)
    avg_win = float(np.mean([t.return_pct for t in wins])) if wins else 0.0
    avg_loss = float(np.mean([t.return_pct for t in losses])) if losses else 0.0
    outcomes = [t.pnl > 0 for t in trades]
    mvals = np.array([m.value for m in monthly]) if monthly else np.array([0.0])
    equity_peak_run = np.maximum.accumulate(np.concatenate(([capital], eq)))[1:]

    return Metrics(
        initial_capital=capital, return_base=base, final_equity=final,
        min_cash=_point(f, "cash", "min"), max_cash=_point(f, "cash", "max"),
        peak_equity=_point(f, "equity", "max"), lowest_equity=_point(f, "equity", "min"),
        max_cash_invested=max(0.0, capital - float(f["cash"].min())),
        max_exposure=float((f["position"] * f["close"]).abs().max()), final_position=float(f["position"].iloc[-1]),
        total_profit=profit, total_return=total_ret, cagr=float(cagr),
        gross_profit=float(gp), gross_loss=float(gl), fees_paid=fees, fee_drag=fees / base,
        benchmark_return=bench_ret, alpha=total_ret - bench_ret,
        volatility=vol, sharpe=float(ret.mean() * TRADING_DAYS / vol) if vol > 0 else 0.0,
        sortino=float(ret.mean() * TRADING_DAYS / downside) if downside > 0 else 0.0,
        calmar=float(cagr / abs(mdd)) if mdd < 0 else 0.0,
        max_drawdown=mdd, max_drawdown_amount=float(f["drawdown_amount"].min()),
        avg_drawdown=float(dd[dd < 0].mean()) if (dd < 0).any() else 0.0,
        daily_var=float(np.percentile(ret, cfg.var_percentile)),
        trades=len(trades), fills=int((f["order"] != 0).sum()), win_rate=len(wins) / len(trades) if trades else 0.0,
        avg_win=avg_win, avg_loss=avg_loss, payoff_ratio=abs(avg_win / avg_loss) if avg_loss else 0.0,
        profit_factor=float(gp / abs(gl)) if gl else 0.0,
        expectancy=float(np.mean([t.return_pct for t in trades])) if trades else 0.0,
        best_trade=max((t.return_pct for t in trades), default=0.0), worst_trade=min((t.return_pct for t in trades), default=0.0),
        avg_holding_days=float(np.mean([t.days for t in trades])) if trades else 0.0,
        max_win_streak=_streak(outcomes, True), max_loss_streak=_streak(outcomes, False),
        exposure=float((f["position"] != 0).mean()),
        best_day=float(ret.max()), worst_day=float(ret.min()), positive_days=float((ret > 0).mean()),
        best_month=float(mvals.max()), worst_month=float(mvals.min()), positive_months=float((mvals > 0).mean()),
        longest_drawdown=_window(idx, longest_run(eq < equity_peak_run), mdd),
        longest_in_profit=_window(idx, longest_run(eq > capital)),
        longest_in_loss=_window(idx, longest_run(eq < capital)),
        best_window=_extreme_window(idx, ret.to_numpy(), True),
        worst_window=_extreme_window(idx, ret.to_numpy(), False),
    )
