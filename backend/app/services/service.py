from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Dict, Optional

import numpy as np

from ..appconfig import AnalysisConfig
from ..data.repository import PriceRepository
from ..domain import metrics as M
from ..domain.engine import EngineConfig, Plan, Simulation, invert, simulate
from ..domain.ledger import TOL, build_days, build_orders, build_periods, build_trades, build_weeks, run_checks
from ..domain.periods import resolve_period
from ..domain.results import (
    BacktestResult,
    FeePoint,
    FeeSensitivity,
    MirrorCheck,
    RuleEvent,
    RuleLegend,
    RuleSummary,
    RuleTestResult,
    Series,
)
from ..domain.rules import CustomRulesStrategy, RuleSet, TradeRule, rule_sentence
from ..domain.spec import BacktestSpec
from ..domain.strategies.base import OrderContext, Strategy
from ..domain.windows import analyze_windows


class BacktestService:
    def __init__(self, repo: PriceRepository, strategies: Dict[str, Strategy], cfg: AnalysisConfig):
        self._repo, self._strategies, self._cfg = repo, strategies, cfg

    def _strategy(self, strategy_id: str) -> Strategy:
        try:
            return self._strategies[strategy_id]
        except KeyError:
            raise ValueError(f"Unknown strategy '{strategy_id}'") from None

    def run(self, spec: BacktestSpec) -> BacktestResult:
        strategy = CustomRulesStrategy(spec.rules) if spec.rules else self._strategy(spec.strategy_id)
        params = strategy.resolve_params(spec.params)
        bars = self._repo.load(spec.symbol)

        # Indicators use the full history so they are warmed up before the selected window.
        s, e = resolve_period(bars.index, spec.period, spec.start, spec.end, self._cfg.periods)
        window = bars.loc[s:e]
        base_plan = strategy.plan(bars, params, OrderContext(spec.lots, spec.allow_short), s)
        base_plan = Plan(base_plan.kind, base_plan.values.loc[:e], base_plan.reasons.loc[:e])
        plan, mirror_plan = (invert(base_plan), base_plan) if spec.invert else (base_plan, invert(base_plan))

        cfg = EngineConfig(spec.initial_capital, spec.fee_pct, spec.allow_short, spec.max_position, spec.limit_to_cash)
        sim = simulate(window, plan, cfg)
        trades, owner = build_trades(sim)
        orders = build_orders(sim, owner)
        weekly = build_weeks(sim, orders)
        fired: dict = {}
        legend = []
        if isinstance(strategy, CustomRulesStrategy):
            for d, n, _rule, _why in strategy.events(bars, s, e):
                fired.setdefault(d.strftime("%Y-%m-%d"), []).append(n)
            legend = [RuleLegend(rule=n, sentence=rule_sentence(r)) for n, r in enumerate(strategy.rules.rules, 1)]
        before = bars.loc[:s]["close"]
        prev_close = float(before.iloc[-2]) if len(before) > 1 and before.index[-1] == window.index[0] else None
        daily = build_days(sim, orders, fired, prev_close)
        weeks, months, total = build_periods(sim, daily, orders, trades)
        monthly = M.monthly_returns(sim.frame["ret"])
        f = sim.frame
        name = f"Inverse of {strategy.name}" if spec.invert else strategy.name
        return BacktestResult(
            symbol=spec.symbol.upper(), strategy_id=strategy.id, strategy_name=name, params=params,
            start=f.index[0].strftime("%Y-%m-%d"), end=f.index[-1].strftime("%Y-%m-%d"), bars=len(f),
            metrics=M.compute_metrics(sim, trades, monthly, self._cfg),
            series=Series(
                dates=[d.strftime("%Y-%m-%d") for d in f.index], close=f["close"].round(4).tolist(),
                equity=f["equity"].round(2).tolist(), equity_no_fee=f["equity_no_fee"].round(2).tolist(),
                benchmark=f["benchmark"].round(2).tolist(), cash=f["cash"].round(2).tolist(),
                position=f["position"].tolist(), order=f["order"].tolist(),
                drawdown=f["drawdown"].round(5).tolist(), daily_return=f["ret"].round(6).tolist(),
            ),
            trades=trades, monthly=monthly,
            windows=analyze_windows(f["equity"].to_numpy(), sim.return_base, self._cfg),
            fees=self._fee_sensitivity(sim, window, plan),
            return_histogram=self._histogram(f["ret"].to_numpy()),
            orders=orders, weekly=weekly, daily=daily, weeks=weeks, months=months, period_total=total, rule_legend=legend,
            checks=run_checks(sim, orders, trades, weekly, daily, {"Weekly overview": weeks, "Monthly overview": months}),
            mirror=self._mirror(sim, window, mirror_plan), inverted=spec.invert,
            settings={"initial_capital": cfg.initial_capital, "fee_pct": cfg.fee_pct, "allow_short": cfg.allow_short,
                      "max_position": cfg.max_position, "limit_to_cash": cfg.limit_to_cash, "lots": spec.lots,
                      "fill_price": "close of the signal day", "pnl_method": "average cost", "week": "Monday to Sunday"},
        )

    def test_rule(self, symbol: str, rule: TradeRule, period: Optional[str], start: Optional[date], end: Optional[date]) -> RuleTestResult:
        """Every day one rule's conditions are met in the period, with the values compared. No money involved."""
        bars = self._repo.load(symbol)
        s, e = resolve_period(bars.index, period, start, end, self._cfg.periods)
        window = bars.loc[s:e]
        close = window["close"]
        fmt = lambda d: d.strftime("%Y-%m-%d")  # noqa: E731
        strategy = CustomRulesStrategy(RuleSet(name=rule.name or "Rule", rules=[rule]))
        events = [RuleEvent(date=fmt(d), close=round(float(close.loc[d]), 4), action=r.action, lots=r.lots, rule=n, reason=why)
                  for d, n, r, why in strategy.events(bars, s, e)]
        return RuleTestResult(
            symbol=symbol.upper(), strategy_name=rule.name or "Unsaved rule", start=fmt(window.index[0]), end=fmt(window.index[-1]),
            bars=len(window), dates=[fmt(d) for d in window.index], close=close.round(4).tolist(), events=events,
            rules=[RuleSummary(rule=1, sentence=rule_sentence(rule), days=len(events))],
            note="Only this rule, exactly as written: every day its conditions are met it places its order. "
                 "No money, holdings, charges, limits or other rules are applied.")

    def _mirror(self, sim: Simulation, window, mirror_plan: Plan) -> MirrorCheck:
        other = simulate(window, mirror_plan, sim.cfg)
        cap = sim.cfg.initial_capital
        p1 = float(sim.frame["equity"].iloc[-1] - cap)
        p2 = float(other.frame["equity"].iloc[-1] - cap)
        charges = float(sim.frame["fees_cum"].iloc[-1] + other.frame["fees_cum"].iloc[-1])
        total = p1 + p2
        limits = [n for n, on in (("short selling is off", not sim.cfg.allow_short), ("a max lots limit is set", bool(sim.cfg.max_position)),
                                  ("cash can't go below 0", sim.cfg.limit_to_cash)) if on]
        exact = not limits
        if exact:
            ok = abs(total + charges) <= TOL * max(1, len(sim.fills))
            note = "Both runs trade the exact mirror image, so strategy + inverse must equal minus the charges of both."
        else:
            ok = True
            note = f"Not an exact mirror because {', '.join(limits)}: one side can be blocked when the other isn't, so the sum can differ."
        return MirrorCheck(exact=exact, strategy_profit=round(p1, 2), inverse_profit=round(p2, 2), total=round(total, 2),
                           charges=round(charges, 2), ok=ok, note=note)

    def _fee_sensitivity(self, sim: Simulation, window, plan: Plan) -> FeeSensitivity:
        f = sim.frame
        fills = int((f["order"] != 0).sum())
        if sim.cfg.limit_to_cash:
            # Charges change what cash can pay for, so fills differ per fee level: rerun each one.
            points = []
            for fee in self._cfg.fee_grid_pct:
                other = simulate(window, plan, replace(sim.cfg, fee_pct=fee))
                points.append(FeePoint(fee_pct=fee, total_return=float(other.frame["equity"].iloc[-1] - sim.cfg.initial_capital) / sim.return_base,
                                       trades=int((other.frame["order"] != 0).sum())))
            return FeeSensitivity(points=points, breakeven_fee_pct=None)
        # Fills do not depend on charges here, so profit is exactly linear in the fee rate: P(fee) = P0 - fee * turnover.
        p0 = float(f["equity_no_fee"].iloc[-1] - sim.cfg.initial_capital)
        points = [FeePoint(fee_pct=fee, total_return=(p0 - fee / 100 * sim.turnover) / sim.return_base, trades=fills) for fee in self._cfg.fee_grid_pct]
        breakeven = round(p0 / sim.turnover * 100, 4) if p0 > 0 and sim.turnover > 0 else None
        return FeeSensitivity(points=points, breakeven_fee_pct=breakeven)

    def _histogram(self, returns: np.ndarray) -> Dict[str, list]:
        lim = float(np.percentile(np.abs(returns), self._cfg.histogram_clip_percentile)) or 1e-9
        counts, edges = np.histogram(np.clip(returns, -lim, lim), bins=self._cfg.histogram_bins, range=(-lim, lim))
        return {"edges": edges.round(5).tolist(), "counts": counts.tolist()}
