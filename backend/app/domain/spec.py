from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional

from .rules import RuleSet


@dataclass
class BacktestSpec:
    symbol: str
    strategy_id: str = "custom"
    params: Dict[str, Any] = field(default_factory=dict)
    rules: Optional[RuleSet] = None
    initial_capital: float = 0.0
    fee_pct: float = 0.0  # 0 when charges are switched off
    allow_short: bool = False
    lots: int = 1  # position size for built-in strategies
    max_position: int = 0
    period: Optional[str] = "MAX"
    start: Optional[date] = None
    end: Optional[date] = None
