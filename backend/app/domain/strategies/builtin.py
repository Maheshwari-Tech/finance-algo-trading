from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from . import indicators as ind
from .base import Strategy
from .registry import register


def _direction(raw: pd.Series, mode: str) -> pd.Series:
    return -raw if mode == "contrarian" else raw


@register
class PriceMove(Strategy):
    id = "price_move"

    def signal(self, bars: pd.DataFrame, p: Dict[str, Any]) -> pd.Series:
        ref = bars["close"].shift(1) if p["reference"] == "prev_close" else bars["open"]
        move = bars["close"] / ref - 1
        t = p["threshold_pct"] / 100
        raw = pd.Series(np.select([move > t, move < -t], [1, -1], 0), index=bars.index)
        return _direction(raw, p["mode"])


@register
class SmaCross(Strategy):
    id = "sma_cross"

    def signal(self, bars, p):
        fast, slow = ind.sma(bars["close"], p["fast"]), ind.sma(bars["close"], p["slow"])
        raw = pd.Series(np.sign(fast - slow), index=bars.index).fillna(0)
        return _direction(raw, p["mode"])


@register
class Rsi(Strategy):
    id = "rsi"

    def signal(self, bars, p):
        r = ind.rsi(bars["close"], p["period"])
        return pd.Series(np.select([r < p["oversold"], r > p["overbought"]], [1, -1], 0), index=bars.index)


@register
class Breakout(Strategy):
    id = "breakout"

    def signal(self, bars, p):
        hi = bars["high"].rolling(p["lookback"]).max().shift(1)
        lo = bars["low"].rolling(p["lookback"]).min().shift(1)
        return pd.Series(np.select([bars["close"] > hi, bars["close"] < lo], [1, -1], 0), index=bars.index)


@register
class Momentum(Strategy):
    id = "momentum"

    def signal(self, bars, p):
        raw = pd.Series(np.sign(bars["close"].pct_change(p["lookback"])), index=bars.index).fillna(0)
        return _direction(raw, p["mode"])


@register
class BuyAndHold(Strategy):
    id = "buy_hold"

    def signal(self, bars, p):
        return pd.Series(1, index=bars.index)
