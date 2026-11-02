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

    def indicators(self, bars, p):
        ref = bars["close"].shift(1) if p["reference"] == "prev_close" else bars["open"]
        label = "Yesterday's close" if p["reference"] == "prev_close" else "Open"
        return {"Close": bars["close"], label: ref, "Move %": (bars["close"] / ref - 1) * 100,
                "Threshold %": pd.Series(p["threshold_pct"], index=bars.index)}


@register
class SmaCross(Strategy):
    id = "sma_cross"

    def signal(self, bars, p):
        fast, slow = ind.sma(bars["close"], p["fast"]), ind.sma(bars["close"], p["slow"])
        raw = pd.Series(np.sign(fast - slow), index=bars.index).fillna(0)
        return _direction(raw, p["mode"])

    def indicators(self, bars, p):
        return {f"SMA({p['fast']})": ind.sma(bars["close"], p["fast"]), f"SMA({p['slow']})": ind.sma(bars["close"], p["slow"])}


@register
class Rsi(Strategy):
    id = "rsi"

    def signal(self, bars, p):
        r = ind.rsi(bars["close"], p["period"])
        return pd.Series(np.select([r < p["oversold"], r > p["overbought"]], [1, -1], 0), index=bars.index)

    def indicators(self, bars, p):
        return {f"RSI({p['period']})": ind.rsi(bars["close"], p["period"]),
                "Buy below": pd.Series(p["oversold"], index=bars.index), "Sell above": pd.Series(p["overbought"], index=bars.index)}


@register
class Breakout(Strategy):
    id = "breakout"

    def signal(self, bars, p):
        hi = bars["high"].rolling(p["lookback"]).max().shift(1)
        lo = bars["low"].rolling(p["lookback"]).min().shift(1)
        return pd.Series(np.select([bars["close"] > hi, bars["close"] < lo], [1, -1], 0), index=bars.index)

    def indicators(self, bars, p):
        n = p["lookback"]
        return {"Close": bars["close"], f"{n}-day high": bars["high"].rolling(n).max().shift(1),
                f"{n}-day low": bars["low"].rolling(n).min().shift(1)}


@register
class Momentum(Strategy):
    id = "momentum"

    def signal(self, bars, p):
        raw = pd.Series(np.sign(bars["close"].pct_change(p["lookback"])), index=bars.index).fillna(0)
        return _direction(raw, p["mode"])

    def indicators(self, bars, p):
        return {"Close": bars["close"], f"{p['lookback']}-day change %": bars["close"].pct_change(p["lookback"]) * 100}


@register
class BuyAndHold(Strategy):
    id = "buy_hold"

    def signal(self, bars, p):
        return pd.Series(1, index=bars.index)
