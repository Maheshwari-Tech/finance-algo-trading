"""Lot-based trading engine with a cash account.

Execution model: orders generated from bar t's data are filled at bar t's close.
Every fill moves cash (buy: cash out, sell: cash in) and pays a fee proportional to traded value.
Cash may go negative: that is exactly the "capital you needed" figure the dashboard reports.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from .results import Trade


@dataclass(frozen=True)
class EngineConfig:
    initial_capital: float = 0.0
    fee_pct: float = 0.0  # percent of traded value, per fill
    allow_short: bool = False  # "sell before buy"
    max_position: int = 0  # max lots held on either side; 0 = unlimited


@dataclass
class Simulation:
    frame: pd.DataFrame
    trades: List[Trade]
    cfg: EngineConfig
    return_base: float
    turnover: float  # total traded value, used for fee sensitivity


def execute_orders(close: np.ndarray, orders: np.ndarray, cfg: EngineConfig) -> np.ndarray:
    """Apply position limits; returns the quantity actually filled on each bar."""
    filled, pos = np.zeros(len(close)), 0.0
    for t, want in enumerate(orders):
        new = pos + want
        if not cfg.allow_short:
            new = max(new, 0.0)
        if cfg.max_position:
            new = min(max(new, -cfg.max_position if cfg.allow_short else 0.0), cfg.max_position)
        filled[t], pos = new - pos, new
    return filled


def simulate(bars: pd.DataFrame, orders: pd.Series, cfg: EngineConfig) -> Simulation:
    """`bars`/`orders` must already be sliced to the evaluation window."""
    close = bars["close"].to_numpy(dtype=float)
    filled = execute_orders(close, orders.to_numpy(dtype=float), cfg)
    position = np.cumsum(filled)
    fee = np.abs(filled) * close * cfg.fee_pct / 100
    cash = cfg.initial_capital - np.cumsum(filled * close + fee)
    equity = cash + position * close
    exposure = float(np.abs(position * close).max())
    base = cfg.initial_capital if cfg.initial_capital > 0 else max(exposure, 1.0)

    f = pd.DataFrame(index=bars.index)
    f["close"], f["order"], f["position"], f["cash"], f["fee"], f["equity"] = close, filled, position, cash, fee, equity
    f["equity_no_fee"] = equity + np.cumsum(fee)
    prev_eq = np.concatenate(([cfg.initial_capital], equity[:-1]))
    f["pnl"] = equity - prev_eq
    f["ret"] = f["pnl"] / base
    peak = np.maximum.accumulate(np.concatenate(([cfg.initial_capital], equity)))[1:]
    f["drawdown_amount"] = equity - peak
    f["drawdown"] = f["drawdown_amount"] / base
    f["benchmark"] = cfg.initial_capital + base * (close / close[0] - 1)
    return Simulation(f, build_trades(f, cfg.fee_pct / 100), cfg, base, float((np.abs(filled) * close).sum()))


def build_trades(f: pd.DataFrame, fee_rate: float) -> List[Trade]:
    """Pair fills first-in-first-out into round-trip trades; still-open lots are marked at the last close."""
    close, orders, dates = f["close"].to_numpy(), f["order"].to_numpy(), f.index
    open_lots: deque = deque()  # [qty, index, price, side]
    trades: List[Trade] = []

    def record(side: int, qty: float, i0: int, i1: int, is_open: bool) -> None:
        p0, p1 = close[i0], close[i1]
        pnl = side * (p1 - p0) * qty - fee_rate * qty * (p0 + (0 if is_open else p1))
        trades.append(Trade(
            side="long" if side > 0 else "short", qty=float(qty),
            entry_date=dates[i0].strftime("%Y-%m-%d"), exit_date=dates[i1].strftime("%Y-%m-%d"),
            entry_price=float(p0), exit_price=float(p1), bars=i1 - i0, days=(dates[i1] - dates[i0]).days,
            return_pct=float(pnl / (p0 * qty)), pnl=float(pnl), is_open=is_open))

    for t, q in enumerate(orders):
        if q == 0:
            continue
        side, remaining = int(np.sign(q)), abs(q)
        while remaining > 1e-12 and open_lots and open_lots[0][3] == -side:
            lot = open_lots[0]
            matched = min(remaining, lot[0])
            record(lot[3], matched, lot[1], t, False)
            lot[0] -= matched
            remaining -= matched
            if lot[0] <= 1e-12:
                open_lots.popleft()
        if remaining > 1e-12:
            open_lots.append([remaining, t, close[t], side])
    for qty, i0, _, side in open_lots:
        record(side, qty, i0, len(close) - 1, True)
    return sorted(trades, key=lambda tr: (tr.entry_date, tr.exit_date))
