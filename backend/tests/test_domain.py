from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.appconfig import load_app_config
from app.data.validation import DataValidationError, parse_ohlc_csv
from app.domain.engine import EngineConfig, simulate
from app.domain.rules import RuleSet
from app.domain.strategies.indicators import rsi

from .conftest import bars_csv, make_bars


def _bars(closes):
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)


def test_buy_then_sell_moves_cash_and_books_profit():
    bars = _bars([100, 110, 121])
    sim = simulate(bars, pd.Series([1, 0, -1], index=bars.index, dtype=float), EngineConfig())
    assert sim.frame["cash"].tolist() == [-100, -100, 21]
    assert sim.frame["equity"].iloc[-1] == pytest.approx(21)
    assert len(sim.trades) == 1 and sim.trades[0].pnl == pytest.approx(21)


def test_fees_are_charged_on_both_sides():
    bars = _bars([100, 100])
    sim = simulate(bars, pd.Series([1, -1], index=bars.index, dtype=float), EngineConfig(fee_pct=1))
    assert sim.frame["equity"].iloc[-1] == pytest.approx(-2)


def test_no_short_selling_by_default_and_position_cap():
    bars = _bars([10, 10, 10, 10])
    orders = pd.Series([-1, 5, 5, -20], index=bars.index, dtype=float)
    sim = simulate(bars, orders, EngineConfig(max_position=6))
    assert sim.frame["position"].tolist() == [0, 5, 6, 0]


def test_rsi_is_100_when_price_only_rises():
    s = pd.Series(np.arange(1, 40, dtype=float))
    assert rsi(s, 14).iloc[-1] == pytest.approx(100)


def test_custom_rule_fires_on_one_percent_up_day():
    from app.domain.rules import CustomRulesStrategy

    bars = _bars([100, 102, 101, 101.5])
    rs = RuleSet(name="t", rules=[{"action": "buy", "lots": 1, "conditions": [
        {"left": {"kind": "change_pct", "period": 1}, "op": "gt", "right": {"kind": "value", "value": 1}}]}])
    orders = CustomRulesStrategy(rs).orders(bars, {}, None, bars.index[0])
    assert orders.tolist() == [0, 1, 0, 0]


def test_csv_validation_accepts_good_file_and_reports_problems():
    cfg = load_app_config().data.csv
    df = parse_ohlc_csv(bars_csv(make_bars(50)), cfg)
    assert len(df) == 50 and df.index.is_monotonic_increasing
    with pytest.raises(DataValidationError) as err:
        parse_ohlc_csv(b"date,open,high,low,close\n2024-01-01,1,1,1,1\n", cfg)
    assert "rows are required" in err.value.problems[0]
