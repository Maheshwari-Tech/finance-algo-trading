from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..domain.rules import RuleSet, TradeRule
from ..domain.spec import BacktestSpec


class BacktestRequest(BaseModel):
    symbol: str
    strategy_id: str = "custom"
    rules: Optional[RuleSet] = Field(None, description="Trader-defined rules; overrides strategy_id")
    params: Dict[str, Any] = Field(default_factory=dict)
    initial_capital: float = Field(0, ge=0, le=1e12, description="Starting cash. 0 is allowed.")
    charges_enabled: bool = Field(False, description="Apply a charge to every trade")
    fee_pct: float = Field(1.0, ge=0, le=10, description="Charge per trade, in percent of traded value")
    allow_short: bool = Field(False, description="Allow selling before buying")
    lots: int = Field(1, ge=1, le=10_000, description="Lots per position for built-in strategies")
    max_position: int = Field(0, ge=0, le=100_000, description="Max lots held on either side; 0 = unlimited")
    limit_to_cash: bool = Field(False, description="Cash can't go below 0: buys are cut to what cash can pay for")
    invert: bool = Field(False, description="Run the inverse strategy: every buy becomes a sell and vice versa")
    period: Optional[str] = Field("MAX", description="1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 3Y, 5Y, MAX")
    start: Optional[date] = None
    end: Optional[date] = None

    def to_spec(self) -> BacktestSpec:
        return BacktestSpec(
            symbol=self.symbol, strategy_id=self.strategy_id, params=self.params, rules=self.rules,
            initial_capital=self.initial_capital, fee_pct=self.fee_pct if self.charges_enabled else 0.0,
            allow_short=self.allow_short, lots=self.lots, max_position=self.max_position,
            limit_to_cash=self.limit_to_cash, invert=self.invert,
            period=self.period, start=self.start, end=self.end)


class SymbolOut(BaseModel):
    symbol: str
    rows: int
    start: str
    end: str


class OtpRequest(BaseModel):
    mobile: str = Field(max_length=32)


class OtpVerify(BaseModel):
    mobile: str = Field(max_length=32)
    otp: str = Field(max_length=16)


class UserOut(BaseModel):
    mobile: str
    role: str


class LoginOut(UserOut):
    token: str
    expires_at: str


class RuleTestRequest(BaseModel):
    symbol: str
    rule: TradeRule
    period: Optional[str] = Field("1Y", description="1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 3Y, 5Y, MAX")
    start: Optional[date] = None
    end: Optional[date] = None
