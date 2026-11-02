"""Strategy contract.

A strategy turns OHLC bars into a *signal* per bar, evaluated at that bar's close:
    +1 -> bullish (be long)     -1 -> bearish (exit / go short)     0 -> no opinion (hold previous state)
The engine owns position handling, fees and execution, so strategies stay pure and tiny.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..engine import Plan


def _fmt(v) -> str:
    return "n/a" if pd.isna(v) else f"{float(v):,.2f}"


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    kind: str  # "int" | "float" | "select"
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Optional[List[Dict[str, str]]] = None  # [{"value":..,"label":..}] for "select"
    help: str = ""

    def coerce(self, raw: Any) -> Any:
        if raw is None:
            return self.default
        if self.kind == "select":
            allowed = {o["value"] for o in (self.options or [])}
            if raw not in allowed:
                raise ValueError(f"'{self.key}' must be one of {sorted(allowed)}")
            return raw
        try:
            value = int(raw) if self.kind == "int" else float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"'{self.key}' must be a number")
        if self.min is not None and value < self.min or self.max is not None and value > self.max:
            raise ValueError(f"'{self.key}' must be between {self.min} and {self.max}")
        return value


@dataclass(frozen=True)
class OrderContext:
    lots: int
    allow_short: bool


class Strategy(ABC):
    """Behaviour lives in code; name, description and parameter specs live in config/strategies.json."""
    id: str  # key into config/strategies.json

    def __init__(self, meta: Dict[str, Any]):
        self.name: str = meta["name"]
        self.description: str = meta["description"]
        self.params: List[ParamSpec] = [ParamSpec(**p) for p in meta["params"]]

    def resolve_params(self, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        raw = raw or {}
        return {p.key: p.coerce(raw.get(p.key)) for p in self.params}

    @abstractmethod
    def signal(self, bars: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
        """Return a Series (indexed like `bars`) of +1 / -1 / 0."""

    def indicators(self, bars: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, pd.Series]:
        """Values shown in each order's reason, e.g. {"SMA(10)": series}. Override per strategy."""
        return {}

    def target(self, bars: pd.DataFrame, params: Dict[str, Any], ctx: OrderContext) -> pd.Series:
        """Lots the strategy wants to hold after each close: +lots while bullish, -lots (or 0 without shorting) while bearish."""
        state = self.signal(bars, params).replace(0, np.nan).ffill().fillna(0)
        if not ctx.allow_short:
            state = state.clip(lower=0)
        return state * ctx.lots

    def plan(self, bars: pd.DataFrame, params: Dict[str, Any], ctx: OrderContext, start: pd.Timestamp) -> Plan:
        """Target holding per bar from `start` on, with a reason on every bar where the target changes.

        Indicators use the full history, so they are warmed up before `start`.
        """
        raw = self.signal(bars, params)
        target = self.target(bars, params, ctx)
        ind = self.indicators(bars, params)
        window = target.loc[start:]
        prev = window.shift(1)
        reasons = pd.Series("", index=window.index, dtype=object)
        for i, d in enumerate(window.index):
            if (i == 0 and window.iloc[0] != 0) or (i > 0 and window.iloc[i] != prev.iloc[i]):
                sig = raw.loc[d]
                mood = "bullish" if sig > 0 else "bearish" if sig < 0 else "no new signal (carried over)"
                vals = ", ".join(f"{k} = {_fmt(v.loc[d])}" for k, v in ind.items())
                start_note = "Signal already active when the period starts. " if i == 0 else ""
                was = 0 if i == 0 else prev.iloc[i]
                reasons.iloc[i] = f"{start_note}Signal {mood}{': ' + vals if vals else ''}. Target holding {was:g} -> {window.iloc[i]:g} lots."
        return Plan("target", window, reasons)

    def orders(self, bars: pd.DataFrame, params: Dict[str, Any], ctx: OrderContext, start: pd.Timestamp) -> pd.Series:
        """Quantity to buy (+) / sell (-) at each close from `start` on, if every order fills in full."""
        target = self.target(bars, params, ctx).loc[start:]
        return target.diff().fillna(target.iloc[0])

    def describe(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "params": [p.__dict__ for p in self.params],
        }




