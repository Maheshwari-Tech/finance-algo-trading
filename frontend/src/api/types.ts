export interface SymbolInfo { symbol: string; rows: number; start: string; end: string }

export interface ParamSpec {
  key: string; label: string; kind: "int" | "float" | "select"; default: number | string;
  min?: number; max?: number; step?: number; options?: { value: string; label: string }[]; help: string;
}
export interface StrategyInfo { id: string; name: string; description: string; params: ParamSpec[] }
export interface StrategyCatalog { strategies: StrategyInfo[]; periods: string[] }

export type ParamValues = Record<string, number | string>;

export interface BacktestRequest {
  symbol: string; strategy_id: string; rules?: RuleSet; params: ParamValues; initial_capital: number;
  charges_enabled: boolean; fee_pct: number; allow_short: boolean; lots: number; max_position: number;
  period?: string; start?: string; end?: string;
}

export interface DateWindow { start: string | null; end: string | null; bars: number; days: number; value: number | null }

export interface CapitalPoint { value: number; date: string }

export interface Metrics {
  initial_capital: number; return_base: number; final_equity: number;
  min_cash: CapitalPoint; max_cash: CapitalPoint; peak_equity: CapitalPoint; lowest_equity: CapitalPoint;
  max_cash_invested: number; max_exposure: number; final_position: number;
  total_profit: number; total_return: number; cagr: number;
  gross_profit: number; gross_loss: number; fees_paid: number; fee_drag: number;
  benchmark_return: number; alpha: number;
  volatility: number; sharpe: number; sortino: number; calmar: number;
  max_drawdown: number; max_drawdown_amount: number; avg_drawdown: number; daily_var: number;
  trades: number; fills: number; win_rate: number; avg_win: number; avg_loss: number; payoff_ratio: number; profit_factor: number;
  expectancy: number; best_trade: number; worst_trade: number; avg_holding_days: number;
  max_win_streak: number; max_loss_streak: number; exposure: number;
  best_day: number; worst_day: number; positive_days: number; best_month: number; worst_month: number; positive_months: number;
  longest_drawdown: DateWindow; longest_in_profit: DateWindow; longest_in_loss: DateWindow;
  best_window: DateWindow; worst_window: DateWindow;
}

export interface Trade {
  side: "long" | "short"; qty: number; entry_date: string; exit_date: string; entry_price: number; exit_price: number;
  bars: number; days: number; return_pct: number; pnl: number; is_open: boolean;
}
export interface WindowStat {
  bars: number; pct_profitable: number; avg_return: number; median_return: number;
  best_return: number; worst_return: number; samples: number;
}
export interface WindowAnalysis {
  stats: WindowStat[]; always_profitable_bars: number; majority_profitable_bars: number;
  best_hold_bars: number; total_windows_tested: number; majority_threshold: number;
}
export interface FeeSensitivity { points: { fee_pct: number; total_return: number; trades: number }[]; breakeven_fee_pct: number | null }
export interface Series {
  dates: string[]; close: number[]; equity: number[]; equity_no_fee: number[]; benchmark: number[]; cash: number[];
  position: number[]; order: number[]; drawdown: number[]; daily_return: number[];
}

export interface BacktestResult {
  symbol: string; strategy_id: string; strategy_name: string; params: ParamValues;
  start: string; end: string; bars: number; metrics: Metrics; series: Series; trades: Trade[];
  monthly: { year: number; month: number; value: number }[];
  windows: WindowAnalysis; fees: FeeSensitivity; return_histogram: { edges: number[]; counts: number[] };
}

export interface OperandSpec { kind: string; period?: number; value?: number; field?: string }
export interface Condition { left: OperandSpec; op: string; right: OperandSpec }
export interface TradeRule { action: "buy" | "sell"; lots: number; match: "all" | "any"; conditions: Condition[] }
export interface RuleSet { name: string; rules: TradeRule[] }

export interface OperandInfo { kind: string; label: string; uses_period: boolean; default_period: number | null; uses_field: boolean; uses_value: boolean }
export interface BuilderCatalog {
  operands: OperandInfo[]; price_fields: { value: string; label: string }[]; operators: { value: string; label: string }[];
  limits: { period: Range; lots: Range; rules: number; conditions_per_rule: number };
}
export interface Range { min: number; max: number; step?: number }

export interface Thresholds {
  good_sharpe: number; good_win_rate: number; deep_drawdown: number; few_fills: number; low_breakeven_fee_pct: number; max_trade_log_rows: number;
}
export interface UiConfig {
  currency: { symbol: string; locale: string };
  defaults: Omit<BacktestRequest, "symbol" | "params" | "rules" | "start" | "end">;
  limits: Record<"initial_capital" | "fee_pct" | "lots" | "max_position", Range>;
  thresholds: Thresholds;
  new_rule: TradeRule;
  new_condition: { buy: Condition; sell: Condition };
  initial_rule_set: string;
  rule_templates: RuleSet[];
}

export interface AuthConfig { country_code: string; mode: "dev" | "prod"; otp_length: number }
export interface UserInfo { mobile: string; role: "admin" | "trader" }
export interface LoginResult extends UserInfo { token: string; expires_at: string }
export interface UploadSpec { columns: string[]; min_rows: number; max_upload_mb: number }
