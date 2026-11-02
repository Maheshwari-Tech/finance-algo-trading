"""Typed result objects returned by the backtest service (serialised by FastAPI)."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class Trade(BaseModel):
    side: str  # "long" | "short"
    qty: float
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    bars: int
    days: int
    return_pct: float  # net of fees, fraction
    pnl: float  # currency, net of fees
    is_open: bool = False


class DateWindow(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    bars: int = 0
    days: int = 0
    value: Optional[float] = None  # window return where meaningful


class CapitalPoint(BaseModel):
    value: float
    date: str


class Metrics(BaseModel):
    # Capital (currency)
    initial_capital: float
    return_base: float  # what percentages are measured against: initial capital, or peak exposure if you start with 0
    final_equity: float
    min_cash: CapitalPoint  # most negative (or lowest) cash balance
    max_cash: CapitalPoint  # highest cash balance
    peak_equity: CapitalPoint  # best net worth (cash + holdings)
    lowest_equity: CapitalPoint  # worst net worth
    max_cash_invested: float  # most cash you had put in at once (initial capital - min cash)
    max_exposure: float  # largest value of holdings at once
    final_position: float
    # Profit
    total_profit: float
    total_return: float
    cagr: float
    gross_profit: float
    gross_loss: float
    fees_paid: float
    fee_drag: float  # return lost to fees
    # Benchmark
    benchmark_return: float
    alpha: float
    # Risk
    volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    max_drawdown_amount: float
    avg_drawdown: float
    daily_var: float
    # Trades
    trades: int
    fills: int
    win_rate: float
    avg_win: float
    avg_loss: float
    payoff_ratio: float
    profit_factor: float
    expectancy: float
    best_trade: float
    worst_trade: float
    avg_holding_days: float
    max_win_streak: int
    max_loss_streak: int
    exposure: float
    # Daily behaviour
    best_day: float
    worst_day: float
    positive_days: float
    best_month: float
    worst_month: float
    positive_months: float
    # Windows
    longest_drawdown: DateWindow
    longest_in_profit: DateWindow
    longest_in_loss: DateWindow
    best_window: DateWindow
    worst_window: DateWindow


class WindowStat(BaseModel):
    bars: int
    pct_profitable: float
    avg_return: float
    median_return: float
    best_return: float
    worst_return: float
    samples: int


class WindowAnalysis(BaseModel):
    stats: List[WindowStat]
    always_profitable_bars: int  # longest hold length that never lost money
    majority_profitable_bars: int  # longest hold length profitable >= 50% of the time
    best_hold_bars: int  # hold length with best average return per bar
    total_windows_tested: int
    majority_threshold: float


class FeePoint(BaseModel):
    fee_pct: float
    total_return: float
    trades: int


class FeeSensitivity(BaseModel):
    points: List[FeePoint]
    breakeven_fee_pct: Optional[float]


class MonthlyReturn(BaseModel):
    year: int
    month: int
    value: float


class Series(BaseModel):
    dates: List[str]
    close: List[float]
    equity: List[float]  # net worth = cash + holdings, after charges
    equity_no_fee: List[float]
    benchmark: List[float]
    cash: List[float]
    position: List[float]
    order: List[float]  # executed quantity per bar (+buy / -sell)
    drawdown: List[float]
    daily_return: List[float]


class BacktestResult(BaseModel):
    symbol: str
    strategy_id: str
    strategy_name: str
    params: Dict[str, object]
    start: str
    end: str
    bars: int
    metrics: Metrics
    series: Series
    trades: List[Trade]
    monthly: List[MonthlyReturn]
    windows: WindowAnalysis
    fees: FeeSensitivity
    return_histogram: Dict[str, List[float]]
