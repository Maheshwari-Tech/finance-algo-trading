"""Typed result objects returned by the backtest service (serialised by FastAPI)."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class Trade(BaseModel):
    """One position cycle: from holding 0 lots until back to 0 (or until it flips side). Average-cost accounting."""
    id: int
    side: str  # "long" | "short"
    qty: float  # most lots held during the trade
    entry_date: str
    exit_date: str  # last close of the window when still open
    entry_price: float  # average price of the orders that opened/added
    exit_price: float  # average price of the orders that reduced/closed (last close when still open)
    bars: int
    days: int
    invested: float  # most money held in this position at entry price
    realized: float  # before charges
    unrealized: float  # open part, valued at the last close
    fees: float
    pnl: float  # realized + unrealized - fees
    return_pct: float  # pnl / invested, fraction
    first_order: int
    last_order: int
    orders: int
    is_open: bool = False


class Order(BaseModel):
    """One requested order. Every row satisfies: cash_after = cash_before - filled * price - fee."""
    no: int
    date: str
    week: str  # Monday of the week (YYYY-MM-DD)
    action: str  # "buy" | "sell"
    requested: float  # signed lots asked for by the strategy
    filled: float  # signed lots actually traded (0 = skipped)
    price: float
    value: float  # |filled| * price
    fee: float
    cash_before: float
    cash_after: float
    position_before: float
    position_after: float
    avg_price_after: float
    realized: float  # realised P&L of this order, before charges
    realized_total: float
    unrealized_after: float  # open P&L at this close
    equity_after: float  # cash_after + position_after * price
    trade_id: Optional[int] = None
    note: str = ""  # why it was cut or skipped
    reason: str = ""  # why the strategy asked for it


class WeekRow(BaseModel):
    week_start: str  # Monday
    week_end: str  # last trading day in the window that week
    buys: int
    sells: int
    skipped: int
    bought_lots: float
    sold_lots: float
    buy_value: float
    sell_value: float
    fees: float
    realized: float
    position_end: float
    avg_price_end: float
    close_end: float
    cash_end: float
    unrealized_end: float
    equity_end: float
    equity_change: float


class Check(BaseModel):
    name: str
    ok: bool
    detail: str


class MirrorCheck(BaseModel):
    exact: bool  # True when no limit can block one side differently from the other
    strategy_profit: float
    inverse_profit: float
    total: float
    charges: float  # charges of both runs
    ok: bool
    note: str


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
    return_base: float  # what other % figures are measured against: peak money in positions at entry price
    final_equity: float
    min_cash: CapitalPoint  # most negative (or lowest) cash balance
    max_cash: CapitalPoint  # highest cash balance
    peak_equity: CapitalPoint  # best net worth (cash + holdings)
    lowest_equity: CapitalPoint  # worst net worth
    max_cash_invested: float  # most cash you had put in at once (initial capital - min cash)
    max_exposure: float  # largest value of holdings at once
    final_position: float
    final_avg_price: float
    peak_position_cost: float  # most money ever held in positions, at entry price (longs + shorts)
    peak_cash_in: float  # most cash ever drawn from the account (starting capital - lowest cash)
    # Profit
    total_profit: float  # = realized_pnl + unrealized_pnl - fees_paid = final_equity - initial_capital
    realized_pnl: float  # closed positions, average cost, before charges
    unrealized_pnl: float  # open position valued at the last close
    return_on_position_cost: float  # total_profit / peak_position_cost
    return_on_cash: Optional[float]  # total_profit / peak_cash_in (None when no cash was drawn)
    total_return: float  # same as return_on_position_cost
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
    orders: List[Order]
    weekly: List[WeekRow]
    checks: List[Check]
    mirror: MirrorCheck
    inverted: bool
    settings: Dict[str, object]
