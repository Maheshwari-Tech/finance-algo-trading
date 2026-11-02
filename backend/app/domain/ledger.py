"""Turns a Simulation into rows a person can check by hand: orders, trades (position cycles), weeks, and the checks
that prove the numbers add up."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from .engine import Simulation
from .results import Check, Order, Trade, WeekRow

TOL = 0.01  # per-row money tolerance (one paisa)
TOTAL_TOL = 0.02  # cross-total tolerance: published rows are rounded to paise


def _r(v: float, d: int = 2) -> float:
    return round(float(v), d)


def _monday(d: pd.Timestamp) -> pd.Timestamp:
    return (d - pd.Timedelta(days=d.weekday())).normalize()


def build_trades(sim: Simulation) -> tuple[List[Trade], dict]:
    """Position cycles from the fills. Returns the trades and {fill list index: trade id} for filled orders."""
    f, idx = sim.frame, sim.frame.index
    close = f["close"].to_numpy()
    trades: List[Trade] = []
    owner: dict = {}
    cur: Optional[dict] = None

    def start(side: int, i: int, fill_no: int) -> dict:
        return {"side": side, "i0": i, "open_qty": 0.0, "open_value": 0.0, "close_qty": 0.0, "close_value": 0.0,
                "realized": 0.0, "fees": 0.0, "max_qty": 0.0, "invested": 0.0, "first": fill_no, "last": fill_no, "n": 0}

    def finish(c: dict, i: int, is_open: bool) -> None:
        unreal = float(f["unrealized"].iloc[-1]) if is_open else 0.0
        pnl = c["realized"] + unreal - c["fees"]
        trades.append(Trade(
            id=len(trades) + 1, side="long" if c["side"] > 0 else "short", qty=c["max_qty"],
            entry_date=idx[c["i0"]].strftime("%Y-%m-%d"), exit_date=idx[i].strftime("%Y-%m-%d"),
            entry_price=_r(c["open_value"] / c["open_qty"], 4) if c["open_qty"] else 0.0,
            exit_price=_r(c["close_value"] / c["close_qty"], 4) if c["close_qty"] and not is_open else _r(close[i], 4),
            bars=i - c["i0"], days=(idx[i] - idx[c["i0"]]).days, invested=_r(c["invested"]),
            realized=c["realized"], unrealized=unreal, fees=c["fees"], pnl=pnl, return_pct=0.0,
            first_order=c["first"], last_order=c["last"], orders=c["n"], is_open=is_open))

    for k, fl in enumerate(sim.fills):
        if fl.filled == 0:
            continue
        no = k + 1
        q, p0, p1 = fl.filled, fl.position_before, fl.position_after
        if p0 == 0:
            cur = start(int(np.sign(q)), fl.index, no)
        assert cur is not None
        flips = p0 != 0 and p1 != 0 and np.sign(p1) != np.sign(p0)
        closing_qty = min(abs(q), abs(p0)) if p0 != 0 and np.sign(q) != np.sign(p0) else 0.0
        opening_qty = abs(q) - closing_qty
        share_close = closing_qty / abs(q)
        cur["n"] += 1
        cur["last"] = no
        owner[k] = len(trades) + 1
        if closing_qty:
            cur["close_qty"] += closing_qty
            cur["close_value"] += closing_qty * fl.price
            cur["realized"] += fl.realized
        if not flips and opening_qty:
            cur["open_qty"] += opening_qty
            cur["open_value"] += opening_qty * fl.price
        cur["fees"] += fl.fee * (share_close if flips else 1.0)
        if not flips:
            cur["max_qty"] = max(cur["max_qty"], abs(p1))
            cur["invested"] = max(cur["invested"], abs(p1) * fl.avg_price_after)
        if p1 == 0 or flips:
            finish(cur, fl.index, False)
            cur = None
            if flips:  # the rest of this order opens a new position on the other side
                cur = start(int(np.sign(p1)), fl.index, no)
                cur.update(open_qty=abs(p1), open_value=abs(p1) * fl.price, fees=fl.fee * (1 - share_close),
                           max_qty=abs(p1), invested=abs(p1) * fl.price, n=1)
    if cur is not None:
        finish(cur, len(idx) - 1, True)
    # Round money as differences of rounded running totals, so the trades add up to the overall figures to the paisa.
    cum_r = cum_f = prev_r = prev_f = 0.0
    for t in trades:
        cum_r += t.realized
        cum_f += t.fees
        t.realized, prev_r = _r(_r(cum_r) - prev_r), _r(cum_r)
        t.fees, prev_f = _r(_r(cum_f) - prev_f), _r(cum_f)
        t.unrealized = _r(t.unrealized)
        t.pnl = _r(t.realized + t.unrealized - t.fees)
        t.return_pct = float(t.pnl / t.invested) if t.invested else 0.0
    return trades, owner


def build_orders(sim: Simulation, owner: dict) -> List[Order]:
    idx, close = sim.frame.index, sim.frame["close"].to_numpy()
    realized_total = 0.0
    rows: List[Order] = []
    for k, fl in enumerate(sim.fills):
        realized_total += fl.realized
        d = idx[fl.index]
        rows.append(Order(
            no=k + 1, date=d.strftime("%Y-%m-%d"), week=_monday(d).strftime("%Y-%m-%d"),
            action="buy" if fl.requested > 0 else "sell", requested=fl.requested, filled=fl.filled,
            price=_r(fl.price, 4), value=_r(abs(fl.filled) * fl.price), fee=_r(fl.fee),
            cash_before=_r(fl.cash_before), cash_after=_r(fl.cash_after),
            position_before=fl.position_before, position_after=fl.position_after,
            avg_price_after=_r(fl.avg_price_after, 4), realized=_r(fl.realized), realized_total=_r(realized_total),
            unrealized_after=_r((close[fl.index] - fl.avg_price_after) * fl.position_after),
            equity_after=_r(fl.cash_after + fl.position_after * close[fl.index]),
            trade_id=owner.get(k), note=fl.note, reason=fl.reason))
    return rows


def build_weeks(sim: Simulation, orders: List[Order]) -> List[WeekRow]:
    f = sim.frame
    weeks = f.index.map(lambda d: _monday(d))
    by_week = {}
    for o in orders:
        by_week.setdefault(o.week, []).append(o)
    rows: List[WeekRow] = []
    # Weekly money columns are differences of rounded running totals, so the weeks add up exactly to the totals.
    prev_equity, prev_realized, prev_fees = _r(sim.cfg.initial_capital), 0.0, 0.0
    for monday, chunk in f.groupby(weeks, sort=True):
        key = monday.strftime("%Y-%m-%d")
        os_ = by_week.get(key, [])
        filled = [o for o in os_ if o.filled != 0]
        last = chunk.iloc[-1]
        eq, real, fees = _r(last["equity"]), _r(last["realized_cum"]), _r(last["fees_cum"])
        rows.append(WeekRow(
            week_start=key, week_end=chunk.index[-1].strftime("%Y-%m-%d"),
            buys=sum(1 for o in filled if o.filled > 0), sells=sum(1 for o in filled if o.filled < 0),
            skipped=sum(1 for o in os_ if o.filled == 0),
            bought_lots=float(sum(o.filled for o in filled if o.filled > 0)),
            sold_lots=float(-sum(o.filled for o in filled if o.filled < 0)),
            buy_value=_r(sum(o.value for o in filled if o.filled > 0)), sell_value=_r(sum(o.value for o in filled if o.filled < 0)),
            fees=_r(fees - prev_fees), realized=_r(real - prev_realized),
            position_end=float(last["position"]), avg_price_end=_r(last["avg_price"], 4), close_end=_r(last["close"], 4),
            cash_end=_r(last["cash"]), unrealized_end=_r(last["unrealized"]), equity_end=eq, equity_change=_r(eq - prev_equity)))
        prev_equity, prev_realized, prev_fees = eq, real, fees
    return rows


def run_checks(sim: Simulation, orders: List[Order], trades: List[Trade], weeks: List[WeekRow]) -> List[Check]:
    """Recompute the key identities from the published rows. Any failure means a number on the page is wrong."""
    f, cfg = sim.frame, sim.cfg
    checks: List[Check] = []

    def add(name: str, errors: list, total: int, unit: str, tol: float = TOL) -> None:
        worst = max((abs(e) for e in errors), default=0.0)
        bad = sum(1 for e in errors if abs(e) > tol)
        checks.append(Check(name=name, ok=bad == 0,
                            detail=f"{total:,} {unit} checked, {bad} off (largest difference {worst:.4f})"))

    add("Every order: cash after = cash before - lots x price - charges",
        [fl.cash_after - (fl.cash_before - fl.filled * fl.price - fl.fee) for fl in sim.fills], len(sim.fills), "orders")
    add("Every order: lots after = lots before + lots filled",
        [fl.position_after - (fl.position_before + fl.filled) for fl in sim.fills], len(sim.fills), "orders")
    add("Every day: net worth = cash + lots held x closing price",
        list(f["equity"] - (f["cash"] + f["position"] * f["close"])), len(f), "days")
    add("Every day: net worth - starting capital = realised + open - charges",
        list((f["equity"] - cfg.initial_capital) - (f["realized_cum"] + f["unrealized"] - f["fees_cum"])), len(f), "days")
    profit = float(f["equity"].iloc[-1] - cfg.initial_capital)
    add("Sum of all trade P&L = total profit (rounded to paise)", [sum(t.pnl for t in trades) - profit] if trades else [profit], 1, "total", TOTAL_TOL)
    add("Weekly net worth changes add up to total profit (rounded to paise)", [sum(w.equity_change for w in weeks) - profit], 1, "total", TOTAL_TOL)
    add("Weekly charges add up to total charges (rounded to paise)", [sum(w.fees for w in weeks) - float(f["fees_cum"].iloc[-1])], 1, "total", TOTAL_TOL)
    add("Weekly realised P&L adds up to total realised (rounded to paise)", [sum(w.realized for w in weeks) - float(f["realized_cum"].iloc[-1])], 1, "total", TOTAL_TOL)
    if cfg.limit_to_cash:
        low = float(f["cash"].min())
        checks.append(Check(name="Cash never below 0", ok=low >= -TOL, detail=f"lowest cash {low:,.2f}"))
    if not cfg.allow_short:
        low = float(f["position"].min())
        checks.append(Check(name="Never short (short selling is off)", ok=low >= 0, detail=f"lowest holding {low:g} lots"))
    if cfg.max_position:
        hi = float(f["position"].abs().max())
        checks.append(Check(name=f"Never more than {cfg.max_position} lots held", ok=hi <= cfg.max_position, detail=f"largest holding {hi:g} lots"))
    return checks
