"""Lot-based trading engine with a cash account and average-cost accounting.

Execution model: an order decided from bar t's data fills at bar t's close.
Every fill moves cash (buy: cash out, sell: cash in) and pays a charge proportional to traded value.

Two kinds of plan come from strategies:
  * "target": the holding the strategy wants (built-in signal strategies). When the target changes, the engine
    orders the difference between the target and what is actually held.
  * "delta":  a quantity to buy (+) or sell (-) on that bar (rule builder).

Limits are applied in this order: no short selling, max lots held, cash can't go below 0. Each one that changes
an order is written into that order's note, so the order log explains every requested order.

Accounting (average cost):
  realised P&L  = (fill price - average entry price) x lots closed x direction   (charges are kept separate)
  open P&L      = (close - average entry price) x lots held
  net worth     = cash + lots held x close  ==  starting capital + realised + open - charges
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

EPS = 1e-9


@dataclass(frozen=True)
class EngineConfig:
    initial_capital: float = 0.0
    fee_pct: float = 0.0  # percent of traded value, per fill
    allow_short: bool = False  # "sell before buy"
    max_position: int = 0  # max lots held on either side; 0 = unlimited
    limit_to_cash: bool = False  # cash can't go below 0: buys are cut to what cash can pay for


@dataclass(frozen=True)
class Plan:
    kind: str  # "target" | "delta"
    values: pd.Series  # indexed like the evaluation window
    reasons: pd.Series  # str per bar ("" where nothing was decided)


@dataclass
class Fill:
    """One requested order and what happened to it. Money values are exact (unrounded)."""
    index: int  # bar position in the window
    requested: float
    filled: float
    price: float
    fee: float
    cash_before: float
    cash_after: float
    position_before: float
    position_after: float
    avg_price_before: float
    avg_price_after: float
    realized: float  # realised P&L of this order, before charges
    note: str
    reason: str


@dataclass
class Simulation:
    frame: pd.DataFrame
    fills: List[Fill]
    cfg: EngineConfig
    return_base: float  # peak money in positions at entry price (fallback 1.0 when nothing was ever held)
    peak_cash_in: float  # most cash drawn from the account (starting capital - lowest cash), >= 0
    turnover: float  # total traded value

    @property
    def trades(self):
        """Position cycles (see ledger.build_trades)."""
        from .ledger import build_trades
        return build_trades(self)[0]


def _affordable(cash: float, price: float, fee_rate: float) -> int:
    if cash <= 0:
        return 0
    return int(math.floor(cash / (price * (1 + fee_rate)) + EPS))


def simulate(bars: pd.DataFrame, plan, cfg: EngineConfig) -> Simulation:
    """`bars` and `plan` must already be sliced to the evaluation window. A plain Series is a delta plan."""
    if isinstance(plan, pd.Series):
        plan = Plan("delta", plan, pd.Series("", index=plan.index, dtype=object))
    close = bars["close"].to_numpy(dtype=float)
    values = plan.values.reindex(bars.index).fillna(0).to_numpy(dtype=float)
    reasons = plan.reasons.reindex(bars.index).fillna("").to_numpy(dtype=object)
    fee_rate = cfg.fee_pct / 100
    n = len(close)

    cash, pos, avg = float(cfg.initial_capital), 0.0, 0.0
    realized_cum = fees_cum = turnover = 0.0
    prev_target = 0.0
    fills: List[Fill] = []
    cols = {k: np.zeros(n) for k in ("requested", "order", "position", "avg_price", "cash", "fee", "fees_cum",
                                       "realized_cum", "unrealized", "equity", "position_cost")}

    for t in range(n):
        price = close[t]
        requested = 0.0
        if plan.kind == "target":
            target = values[t]
            if target != prev_target or (t == 0 and target != 0):
                requested = target - pos
            prev_target = target
        else:
            requested = values[t]

        fee = 0.0
        if requested != 0:
            notes = []
            want = pos + requested
            if not cfg.allow_short and want < 0:
                want = 0.0
                notes.append("short selling is off")
            if cfg.max_position and abs(want) > cfg.max_position:
                want = math.copysign(cfg.max_position, want)
                notes.append(f"max {cfg.max_position} lots held")
            qty = want - pos
            if cfg.limit_to_cash and qty > 0:
                can = _affordable(cash, price, fee_rate)
                if qty > can:
                    qty = float(can)
                    notes.append(f"not enough cash (could pay for {can})")
            if qty != requested:
                head = "skipped" if qty == 0 else f"filled {abs(qty):g} of {abs(requested):g}"
                note = f"{head}: {'; '.join(notes)}"
            else:
                note = ""

            pos0, avg0, cash0 = pos, avg, cash
            realized = 0.0
            if qty != 0:
                fee = abs(qty) * price * fee_rate
                cash = cash0 - qty * price - fee
                if pos0 == 0 or np.sign(qty) == np.sign(pos0):  # opening or adding
                    avg = (abs(pos0) * avg0 + abs(qty) * price) / (abs(pos0) + abs(qty))
                    pos = pos0 + qty
                else:  # reducing, closing or flipping
                    closed = min(abs(qty), abs(pos0))
                    realized = (price - avg0) * closed * np.sign(pos0)
                    pos = pos0 + qty
                    if abs(pos) < EPS:
                        pos, avg = 0.0, 0.0
                    elif np.sign(pos) != np.sign(pos0):
                        avg = price  # flipped: the remainder is a new position opened at this price
                realized_cum += realized
                fees_cum += fee
                turnover += abs(qty) * price
            fills.append(Fill(t, requested, qty, price, fee, cash0, cash, pos0, pos, avg0, avg, realized, note, str(reasons[t] or "")))

        cols["requested"][t] = requested
        cols["order"][t] = fills[-1].filled if requested != 0 else 0.0
        cols["position"][t], cols["avg_price"][t], cols["cash"][t] = pos, avg, cash
        cols["fee"][t], cols["fees_cum"][t], cols["realized_cum"][t] = fee, fees_cum, realized_cum
        cols["unrealized"][t] = (price - avg) * pos
        cols["equity"][t] = cash + pos * price
        cols["position_cost"][t] = abs(pos) * avg

    f = pd.DataFrame(cols, index=bars.index)
    f.insert(0, "close", close)
    capital = float(cfg.initial_capital)
    peak_cost = float(f["position_cost"].max()) if n else 0.0
    base = peak_cost if peak_cost > 0 else 1.0
    peak_cash_in = max(0.0, capital - float(f["cash"].min())) if n else 0.0

    equity = f["equity"].to_numpy()
    f["equity_no_fee"] = equity + f["fees_cum"].to_numpy()
    f["pnl"] = equity - np.concatenate(([capital], equity[:-1]))
    f["ret"] = f["pnl"] / base
    peak = np.maximum.accumulate(np.concatenate(([capital], equity)))[1:]
    f["drawdown_amount"] = equity - peak
    f["drawdown"] = f["drawdown_amount"] / base
    f["benchmark"] = capital + base * (close / close[0] - 1)
    return Simulation(f, fills, cfg, base, peak_cash_in, turnover)


def invert(plan: Plan) -> Plan:
    """The mirror strategy: every buy becomes a sell of the same size and vice versa."""
    reasons = plan.reasons.where(plan.reasons == "", "Inverse of: " + plan.reasons)
    return Plan(plan.kind, -plan.values, reasons)


def realized_open_charges(sim: Simulation) -> tuple:
    f = sim.frame
    return float(f["realized_cum"].iloc[-1]), float(f["unrealized"].iloc[-1]), float(f["fees_cum"].iloc[-1])


def last_fill_index(sim: Simulation) -> Optional[int]:
    return sim.fills[-1].index if sim.fills else None
