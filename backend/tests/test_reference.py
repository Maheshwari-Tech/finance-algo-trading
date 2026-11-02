"""Checks the engine against a second, deliberately simple calculator written separately from it, plus cases worked
out by hand. If the engine and the reference ever disagree on any day, these tests fail."""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pytest

from app.appconfig import load_app_config
from app.domain.engine import EngineConfig, Plan, invert, simulate
from app.domain.ledger import build_orders, build_trades, build_weeks, run_checks
from app.domain.rules import CustomRulesStrategy, RuleSet
from app.domain.strategies import build_strategies
from app.domain.strategies.base import OrderContext

CFG = load_app_config()


# ---------------------------------------------------------------------------------------------------------------
# Reference calculator. Tracks the cost basis (money paid for what is held) instead of an average price, and walks
# the orders one lot at a time, so it shares no logic with the engine.
# ---------------------------------------------------------------------------------------------------------------
def reference(close, plan: Plan, capital, fee_pct, allow_short, max_position, limit_to_cash):
    rate = fee_pct / 100
    cash, held, basis, realized, fees = float(capital), 0, 0.0, 0.0, 0.0  # basis: signed money in the position
    last_target = 0.0
    out = []
    for t, price in enumerate(close):
        v = float(plan.values.iloc[t])
        if plan.kind == "target":
            ask = (v - held) if (v != last_target or (t == 0 and v != 0)) else 0
            last_target = v
        else:
            ask = v
        step = 1 if ask > 0 else -1
        for _ in range(int(abs(ask))):  # one lot at a time
            nxt = held + step
            if nxt < 0 and not allow_short:
                break
            if max_position and abs(nxt) > max_position:
                break
            if limit_to_cash and step > 0 and cash < price * (1 + rate) - 1e-9:
                break
            fee = price * rate
            if held == 0 or (held > 0) == (step > 0):  # adding
                basis += step * price
            else:  # closing one lot at the average basis per lot
                per_lot = basis / held  # entry price per lot (basis and held have the same sign)
                realized += (price - per_lot) * (-step)
                basis -= per_lot * (1 if held > 0 else -1)
            held = nxt
            cash -= step * price + fee
            fees += fee
        out.append((cash, held, cash + held * price, realized, (held * price - basis), fees))
    return pd.DataFrame(out, columns=["cash", "position", "equity", "realized_cum", "unrealized", "fees_cum"])


def make_bars(n=600, seed=11):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.014, n)))
    o = c * (1 + rng.normal(0, 0.003, n))
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.004, "low": np.minimum(o, c) * 0.996, "close": c},
                        index=pd.bdate_range("2021-01-04", periods=n))


SETTINGS = [
    dict(capital=0, fee_pct=0, allow_short=True, max_position=0, limit_to_cash=False),
    dict(capital=0, fee_pct=0.1, allow_short=True, max_position=0, limit_to_cash=False),
    dict(capital=0, fee_pct=0.1, allow_short=False, max_position=4, limit_to_cash=False),
    dict(capital=1500, fee_pct=0.05, allow_short=False, max_position=0, limit_to_cash=True),
    dict(capital=800, fee_pct=0.2, allow_short=True, max_position=6, limit_to_cash=True),
]
STRATEGIES = build_strategies(CFG.strategies)
CASES = [(sid, None) for sid in STRATEGIES] + [("custom", t["name"]) for t in CFG.rule_templates]


def plan_for(sid, template, bars, settings, lots=2):
    if template:
        rules = RuleSet(**next(t for t in CFG.rule_templates if t["name"] == template))
        return CustomRulesStrategy(rules).plan(bars, {}, OrderContext(lots, settings["allow_short"]), bars.index[0])
    s = STRATEGIES[sid]
    return s.plan(bars, s.resolve_params({}), OrderContext(lots, settings["allow_short"]), bars.index[0])


@pytest.mark.parametrize("case,settings,inverse", list(itertools.product(CASES, SETTINGS, [False, True])))
def test_engine_matches_reference_every_day(case, settings, inverse):
    bars = make_bars()
    plan = plan_for(*case, bars, settings)
    if inverse:
        plan = invert(plan)
    cfg = EngineConfig(settings["capital"], settings["fee_pct"], settings["allow_short"], settings["max_position"], settings["limit_to_cash"])
    sim = simulate(bars, plan, cfg)
    ref = reference(bars["close"].to_numpy(), plan, **settings)
    for col in ["cash", "position", "equity", "realized_cum", "unrealized", "fees_cum"]:
        np.testing.assert_allclose(sim.frame[col].to_numpy(), ref[col].to_numpy(), atol=1e-6, err_msg=f"{case} {settings} {col}")
    trades, owner = build_trades(sim)
    orders = build_orders(sim, owner)
    failed = [c for c in run_checks(sim, orders, trades, build_weeks(sim, orders)) if not c.ok]
    assert not failed, failed


@pytest.mark.parametrize("case", CASES)
def test_strategy_plus_inverse_equals_minus_charges(case):
    """The mirror image with no limits: profits cancel exactly, leaving only the charges of both (never positive)."""
    bars = make_bars(seed=5)
    settings = dict(allow_short=True)
    plan = plan_for(*case, bars, settings)
    cfg = EngineConfig(0, 0.1, True, 0, False)
    a, b = simulate(bars, plan, cfg), simulate(bars, invert(plan), cfg)
    total = a.frame["equity"].iloc[-1] + b.frame["equity"].iloc[-1]
    charges = a.frame["fees_cum"].iloc[-1] + b.frame["fees_cum"].iloc[-1]
    assert total == pytest.approx(-charges, abs=1e-6)
    assert total <= 1e-9


# ---------------------------------------------------------------------------------------------------------------
# Hand-worked cases
# ---------------------------------------------------------------------------------------------------------------
def bars_of(close):
    idx = pd.bdate_range("2024-01-01", periods=len(close))
    c = np.array(close, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)


def test_hand_case_short_first_from_zero():
    """Start with 0 and 0 lots, selling first allowed. Every number below is worked out by hand."""
    b = bars_of([100, 110, 105, 95, 100, 120])
    sim = simulate(b, pd.Series([-1, -1, 1, 1, 1, 0], index=b.index, dtype=float), EngineConfig(allow_short=True))
    f = sim.frame
    assert f["position"].tolist() == [-1, -2, -1, 0, 1, 1]
    assert f["cash"].tolist() == [100, 210, 105, 10, -90, -90]
    assert f["equity"].tolist() == [0, -10, 0, 10, 10, 30]
    # average short price after day 2 = (100 + 110) / 2 = 105; buying back at 105 realises 0, at 95 realises +10
    assert f["realized_cum"].tolist() == [0, 0, 0, 10, 10, 10]
    assert f["unrealized"].iloc[-1] == 20  # 1 lot bought at 100, now 120
    assert sim.peak_cash_in == 90  # lowest cash -90
    assert f["position_cost"].max() == 210  # two shorts at 105 average
    trades = sim.trades
    assert [(t.side, t.pnl, t.is_open) for t in trades] == [("short", 10, False), ("long", 20, True)]


def test_hand_case_average_cost():
    """Bought 1 at 100 and 1 at 120, sold 1 at 130: average cost 110, so the sale realises +20."""
    b = bars_of([100, 120, 130])
    sim = simulate(b, pd.Series([1, 1, -1], index=b.index, dtype=float), EngineConfig())
    assert sim.frame["realized_cum"].iloc[-1] == 20
    assert sim.frame["avg_price"].iloc[-1] == 110


def test_hand_case_not_enough_cash_buys_what_it_can():
    """Cash 250, price 100, rule says buy 5 -> buys 2, cash left 50."""
    b = bars_of([100])
    sim = simulate(b, pd.Series([5], index=b.index, dtype=float), EngineConfig(initial_capital=250, limit_to_cash=True))
    (fill,) = sim.fills
    assert fill.requested == 5 and fill.filled == 2 and fill.cash_after == 50
    assert "not enough cash" in fill.note


def test_hand_case_cash_limit_counts_charges():
    """Cash 201, price 100, 1% charge: 2 lots would cost 202, so only 1 fills."""
    b = bars_of([100])
    sim = simulate(b, pd.Series([2], index=b.index, dtype=float), EngineConfig(initial_capital=201, fee_pct=1, limit_to_cash=True))
    assert sim.fills[0].filled == 1 and sim.fills[0].cash_after == pytest.approx(201 - 100 - 1)


def test_hand_case_flip_long_to_short():
    """Long 2 at 50, sell 5 at 60: closes 2 (+20 realised) and opens a 3-lot short at 60."""
    b = bars_of([50, 60, 55])
    sim = simulate(b, pd.Series([2, -5, 0], index=b.index, dtype=float), EngineConfig(allow_short=True))
    f = sim.frame
    assert f["position"].tolist() == [2, -3, -3]
    assert f["realized_cum"].iloc[-1] == 20 and f["avg_price"].iloc[-1] == 60
    assert f["unrealized"].iloc[-1] == 15  # short 3 at 60, now 55
    t1, t2 = sim.trades
    assert (t1.side, t1.pnl, t1.is_open) == ("long", 20, False)
    assert (t2.side, t2.pnl, t2.is_open) == ("short", 15, True)


def test_target_plan_does_not_lose_sync_when_blocked():
    """A blocked short must not turn the later 'back to flat' order into a buy."""
    b = bars_of([10, 11, 12])
    plan = Plan("target", pd.Series([-1.0, 0.0, 0.0], index=b.index), pd.Series("", index=b.index, dtype=object))
    sim = simulate(b, plan, EngineConfig(allow_short=False))
    assert sim.frame["position"].tolist() == [0, 0, 0]
    assert sim.fills[0].filled == 0 and "short selling is off" in sim.fills[0].note


def test_weeks_run_monday_to_sunday():
    b = bars_of([10] * 8)  # Mon 1 Jan 2024 .. Wed 10 Jan 2024 (business days)
    sim = simulate(b, pd.Series([1, 0, 0, 0, 0, 1, 0, 0], index=b.index, dtype=float), EngineConfig())
    trades, owner = build_trades(sim)
    weeks = build_weeks(sim, build_orders(sim, owner))
    assert [(w.week_start, w.week_end, w.buys) for w in weeks] == [("2024-01-01", "2024-01-05", 1), ("2024-01-08", "2024-01-10", 1)]


def test_reasons_show_rule_values():
    b = bars_of([100, 102, 101])
    rules = RuleSet(name="t", rules=[{"action": "buy", "lots": 1, "conditions": [
        {"left": {"kind": "change_pct", "period": 1}, "op": "gt", "right": {"kind": "value", "value": 1}}]}])
    plan = CustomRulesStrategy(rules).plan(b, {}, OrderContext(1, False), b.index[0])
    assert plan.reasons.iloc[1] == "Rule 1 BUY 1: 1-day change % 2.00 > 1"
    assert plan.reasons.iloc[0] == plan.reasons.iloc[2] == ""


def test_affordable_rounding_is_safe():
    b = bars_of([0.1 * 3])  # 0.30000000000000004
    sim = simulate(b, pd.Series([10], index=b.index, dtype=float), EngineConfig(initial_capital=3.0, limit_to_cash=True))
    assert sim.fills[0].filled in (9, 10) and sim.frame["cash"].iloc[-1] >= -1e-9
    assert not math.isnan(sim.frame["equity"].iloc[-1])


def test_rule_can_fire_only_when_it_becomes_true():
    """Close above 100 on days 2-4 and 6: 'every day' fires 4 times, 'becomes true' only on days 2 and 6."""
    b = bars_of([99, 101, 102, 103, 98, 104])
    cond = [{"left": {"kind": "price", "field": "close"}, "op": "gt", "right": {"kind": "value", "value": 100}}]
    every = CustomRulesStrategy(RuleSet(name="e", rules=[{"action": "buy", "lots": 1, "conditions": cond}]))
    once = CustomRulesStrategy(RuleSet(name="o", rules=[{"action": "buy", "lots": 1, "when": "becomes_true", "conditions": cond}]))
    assert every.plan(b, {}, OrderContext(1, False), b.index[0]).values.tolist() == [0, 1, 1, 1, 0, 1]
    p = once.plan(b, {}, OrderContext(1, False), b.index[0])
    assert p.values.tolist() == [0, 1, 0, 0, 0, 1]
    assert p.reasons.iloc[1] == "Rule 1 BUY 1 (first day true): Close 101.00 > 100"


def test_becomes_true_uses_history_before_the_window():
    """Already true the day before the window starts, so it does not fire on the first window day."""
    b = bars_of([101, 102, 99, 103])
    rule = [{"action": "buy", "lots": 1, "when": "becomes_true", "conditions": [
        {"left": {"kind": "price", "field": "close"}, "op": "gt", "right": {"kind": "value", "value": 100}}]}]
    p = CustomRulesStrategy(RuleSet(name="o", rules=rule)).plan(b, {}, OrderContext(1, False), b.index[1])
    assert p.values.tolist() == [0, 0, 1]
