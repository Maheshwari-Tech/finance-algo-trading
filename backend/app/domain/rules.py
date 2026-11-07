"""Declarative rule builder: traders compose conditions; nothing user-supplied is ever executed as code.

Extend by adding an `Operand` to OPERANDS (a new indicator) or an entry to OPERATORS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from ..config import ConfigError
from .engine import Plan
from .strategies import indicators as ind
from .strategies.base import Strategy

Bars = pd.DataFrame


@dataclass(frozen=True)
class Operand:
    """How an operand is computed. Labels and default periods live in config/rule_builder.json."""
    kind: str
    evaluate: Callable[[Bars, Optional[int], Optional[float], Optional[str]], pd.Series]
    uses_period: bool = False
    uses_field: bool = False
    uses_value: bool = False


PRICE_FIELDS = ("open", "high", "low", "close", "prev_close")


def _price(bars: Bars, _p, _v, field: Optional[str]) -> pd.Series:
    if field == "prev_close":
        return bars["close"].shift(1)
    if field not in PRICE_FIELDS:
        raise ValueError("Unknown price field")
    return bars[field]


OPERANDS: Dict[str, Operand] = {o.kind: o for o in [
    Operand("price", _price, uses_field=True),
    Operand("sma", lambda b, p, v, f: ind.sma(b["close"], p), uses_period=True),
    Operand("ema", lambda b, p, v, f: b["close"].ewm(span=p, adjust=False, min_periods=p).mean(), uses_period=True),
    Operand("rsi", lambda b, p, v, f: ind.rsi(b["close"], p), uses_period=True),
    Operand("change_pct", lambda b, p, v, f: b["close"].pct_change(p) * 100, uses_period=True),
    Operand("highest", lambda b, p, v, f: b["high"].rolling(p).max().shift(1), uses_period=True),
    Operand("lowest", lambda b, p, v, f: b["low"].rolling(p).min().shift(1), uses_period=True),
    Operand("value", lambda b, p, v, f: pd.Series(v, index=b.index, dtype=float), uses_value=True),
]}

OPERATORS: Dict[str, Callable[[pd.Series, pd.Series], pd.Series]] = {
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "crosses_above": lambda a, b: (a > b) & (a.shift(1) <= b.shift(1)),
    "crosses_below": lambda a, b: (a < b) & (a.shift(1) >= b.shift(1)),
}


class OperandSpec(BaseModel):
    kind: str
    period: Optional[int] = Field(None, ge=1, le=500)
    value: Optional[float] = Field(None, ge=-1e9, le=1e9)
    field: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in OPERANDS:
            raise ValueError(f"Unknown operand '{v}'")
        return v

    def evaluate(self, bars: Bars) -> pd.Series:
        op = OPERANDS[self.kind]
        if op.uses_period and self.period is None:
            raise ValueError(f"'{self.kind}' needs a number of days")
        if op.uses_value and self.value is None:
            raise ValueError("A number is required")
        return op.evaluate(bars, self.period, self.value, self.field).astype(float)


class Condition(BaseModel):
    left: OperandSpec
    op: str
    right: OperandSpec

    @field_validator("op")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in OPERATORS:
            raise ValueError(f"Unknown comparison '{v}'")
        return v

    def evaluate(self, bars: Bars) -> pd.Series:
        a, b = self.left.evaluate(bars), self.right.evaluate(bars)
        return OPERATORS[self.op](a, b).fillna(False) & a.notna() & b.notna()


class TradeRule(BaseModel):
    """One order instruction: <action> <lots> when <conditions>. No conditions means every day."""
    id: Optional[int] = None  # the saved rule this came from, if any
    name: Optional[str] = Field(None, max_length=60)
    action: str
    lots: int = Field(1, ge=1, le=10_000)
    match: str = "all"
    conditions: List[Condition] = Field(default_factory=list, max_length=8)

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        if v not in ("buy", "sell"):
            raise ValueError("action must be 'buy' or 'sell'")
        return v

    @field_validator("match")
    @classmethod
    def _match(cls, v: str) -> str:
        if v not in ("all", "any"):
            raise ValueError("match must be 'all' or 'any'")
        return v

    def fires(self, bars: Bars) -> pd.Series:
        """Every day the conditions are met, this rule places its order."""
        if not self.conditions:
            return pd.Series(True, index=bars.index)
        hits = pd.concat([c.evaluate(bars) for c in self.conditions], axis=1)
        return hits.all(axis=1) if self.match == "all" else hits.any(axis=1)

    @property
    def signed_lots(self) -> int:
        return self.lots if self.action == "buy" else -self.lots


class RuleSet(BaseModel):
    name: str = Field(max_length=60)
    rules: List[TradeRule] = Field(min_length=1, max_length=10)


class CustomRulesStrategy(Strategy):
    """Per-request strategy built from a RuleSet. Not registered; it carries its own rules."""
    id = "custom"
    description = ""

    def __init__(self, rules: RuleSet):
        self.rules, self.name = rules, rules.name
        self.params = []

    def signal(self, bars: Bars, params) -> pd.Series:
        raise NotImplementedError("custom rules emit orders directly")

    def orders(self, bars: Bars, params, ctx, start: pd.Timestamp) -> pd.Series:
        total = pd.Series(0.0, index=bars.index)
        for rule in self.rules.rules:
            total += rule.fires(bars).astype(float) * rule.signed_lots
        return total.loc[start:]

    def events(self, bars: Bars, start: pd.Timestamp, end: Optional[pd.Timestamp] = None) -> List[tuple]:
        """(date, rule number, rule, explanation) for every day a rule fires in [start, end], in date order."""
        window = bars.index[(bars.index >= start) & ((bars.index <= end) if end is not None else True)]
        out = []
        for n, rule in enumerate(self.rules.rules, 1):
            fired = rule.fires(bars).loc[window]
            if not fired.any():
                continue
            evaluated = [(c, c.left.evaluate(bars), c.right.evaluate(bars)) for c in rule.conditions]
            joiner = " AND " if rule.match == "all" else " OR "
            for d in fired.index[fired.to_numpy()]:
                if evaluated:
                    i = bars.index.get_loc(d)
                    why = joiner.join(p for p in (_explain(c, a, b, i, rule.match == "any") for c, a, b in evaluated) if p)
                else:
                    why = "no conditions (every day)"
                out.append((d, n, rule, why))
        return sorted(out, key=lambda e: (e[0], e[1]))

    def plan(self, bars: Bars, params, ctx, start: pd.Timestamp) -> Plan:
        """Net lots to buy/sell per bar, with the rules that fired and the values they compared."""
        window = bars.index[bars.index >= start]
        total = pd.Series(0.0, index=window)
        texts = {d: [] for d in window}
        for d, n, rule, why in self.events(bars, start):
            total.loc[d] += rule.signed_lots
            label = f"Rule {n} ({rule.name})" if rule.name else f"Rule {n}"
            texts[d].append(f"{label} {rule.action.upper()} {rule.lots}: {why}")
        reasons = pd.Series(["; ".join(texts[d]) for d in window], index=window, dtype=object)
        return Plan("delta", total, reasons)


def rule_sentence(rule: TradeRule) -> str:
    """'Buy 1 lot when 1-day change % > 1'."""
    head = f"{rule.action.capitalize()} {rule.lots} lot{'s' if rule.lots != 1 else ''}"
    if not rule.conditions:
        return f"{head} every day"
    joiner = " and " if rule.match == "all" else " or "
    conds = joiner.join(f"{operand_label(c.left)} {OP_TEXT[c.op]} {operand_label(c.right)}" for c in rule.conditions)
    return f"{head} when {conds}"


OP_TEXT = {"gt": ">", "lt": "<", "crosses_above": "crosses above", "crosses_below": "crosses below"}


def operand_label(o: OperandSpec) -> str:
    if o.kind == "value":
        return f"{o.value:g}"
    if o.kind == "price":
        return {"prev_close": "Yesterday's close"}.get(o.field or "close", (o.field or "close").capitalize())
    names = {"sma": "SMA({p})", "ema": "EMA({p})", "rsi": "RSI({p})", "change_pct": "{p}-day change %",
             "highest": "{p}-day high", "lowest": "{p}-day low"}
    return names.get(o.kind, o.kind).format(p=o.period)


def _num(v: float) -> str:
    return "n/a" if pd.isna(v) else f"{float(v):,.2f}"


def _explain(c: Condition, a: pd.Series, b: pd.Series, i: int, only_true: bool) -> str:
    """Text for one condition at bar i, with the actual values. With 'any' matching only the true ones are listed."""
    hit = bool(OPERATORS[c.op](a, b).iloc[i]) and pd.notna(a.iloc[i]) and pd.notna(b.iloc[i])
    if only_true and not hit:
        return ""
    left = f"{operand_label(c.left)} {_num(a.iloc[i])}" if c.left.kind != "value" else operand_label(c.left)
    right = f"{operand_label(c.right)} {_num(b.iloc[i])}" if c.right.kind != "value" else operand_label(c.right)
    text = f"{left} {OP_TEXT[c.op]} {right}"
    if c.op.startswith("crosses") and i > 0:
        text += f" (yesterday {_num(a.iloc[i - 1])} vs {_num(b.iloc[i - 1])})"
    return text


def builder_catalog(cfg: dict) -> dict:
    """Merge computation capabilities (code) with labels/defaults (config/rule_builder.json)."""
    labels, ops = cfg["operands"], cfg["operators"]
    if set(labels) != set(OPERANDS) or set(ops) != set(OPERATORS):
        raise ConfigError("config/rule_builder.json operands/operators do not match the implementation")
    return {
        "operands": [{"kind": o.kind, "label": labels[o.kind]["label"], "help": labels[o.kind].get("help", ""), "uses_period": o.uses_period,
                      "default_period": labels[o.kind].get("default_period"), "uses_field": o.uses_field, "uses_value": o.uses_value}
                     for o in OPERANDS.values()],
        "price_fields": [f for f in cfg["price_fields"] if f["value"] in PRICE_FIELDS],
        "operators": [{"value": k, "label": v} for k, v in ops.items()],
        "limits": cfg["limits"],
    }
