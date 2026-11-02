from __future__ import annotations

from typing import Dict

import numpy as np

from ..appconfig import AnalysisConfig
from ..data.repository import PriceRepository
from ..domain import metrics as M
from ..domain.engine import EngineConfig, Simulation, simulate
from ..domain.periods import resolve_period
from ..domain.results import BacktestResult, FeePoint, FeeSensitivity, Series
from ..domain.rules import CustomRulesStrategy
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
            raise ValueError(f"Unknown strategy '{strategy_id}'")

    def run(self, spec: BacktestSpec) -> BacktestResult:
        strategy = CustomRulesStrategy(spec.rules) if spec.rules else self._strategy(spec.strategy_id)
        params = strategy.resolve_params(spec.params)
        bars = self._repo.load(spec.symbol)

        # Indicators use the full history so they are warmed up before the selected window.
        s, e = resolve_period(bars.index, spec.period, spec.start, spec.end, self._cfg.periods)
        orders = strategy.orders(bars, params, OrderContext(spec.lots, spec.allow_short), s).loc[:e]
        window = bars.loc[s:e]

        cfg = EngineConfig(spec.initial_capital, spec.fee_pct, spec.allow_short, spec.max_position)
        sim = simulate(window, orders, cfg)
        monthly = M.monthly_returns(sim.frame["ret"])
        f = sim.frame
        return BacktestResult(
            symbol=spec.symbol.upper(), strategy_id=strategy.id, strategy_name=strategy.name, params=params,
            start=f.index[0].strftime("%Y-%m-%d"), end=f.index[-1].strftime("%Y-%m-%d"), bars=len(f),
            metrics=M.compute_metrics(sim, monthly, self._cfg),
            series=Series(
                dates=[d.strftime("%Y-%m-%d") for d in f.index], close=f["close"].round(4).tolist(),
                equity=f["equity"].round(2).tolist(), equity_no_fee=f["equity_no_fee"].round(2).tolist(),
                benchmark=f["benchmark"].round(2).tolist(), cash=f["cash"].round(2).tolist(),
                position=f["position"].tolist(), order=f["order"].tolist(),
                drawdown=f["drawdown"].round(5).tolist(), daily_return=f["ret"].round(6).tolist(),
            ),
            trades=sim.trades, monthly=monthly,
            windows=analyze_windows(f["equity"].to_numpy(), sim.return_base, self._cfg),
            fees=self._fee_sensitivity(sim),
            return_histogram=self._histogram(f["ret"].to_numpy()),
        )

    def _fee_sensitivity(self, sim: Simulation) -> FeeSensitivity:
        """Fills do not depend on fees, so profit is exactly linear in the fee rate: P(fee) = P0 - fee * turnover."""
        f = sim.frame
        p0 = float(f["equity_no_fee"].iloc[-1] - sim.cfg.initial_capital)
        fills = int((f["order"] != 0).sum())
        points = [FeePoint(fee_pct=fee, total_return=(p0 - fee / 100 * sim.turnover) / sim.return_base, trades=fills) for fee in self._cfg.fee_grid_pct]
        breakeven = round(p0 / sim.turnover * 100, 4) if p0 > 0 and sim.turnover > 0 else None
        return FeeSensitivity(points=points, breakeven_fee_pct=breakeven)

    def _histogram(self, returns: np.ndarray) -> Dict[str, list]:
        lim = float(np.percentile(np.abs(returns), self._cfg.histogram_clip_percentile)) or 1e-9
        counts, edges = np.histogram(np.clip(returns, -lim, lim), bins=self._cfg.histogram_bins, range=(-lim, lim))
        return {"edges": edges.round(5).tolist(), "counts": counts.tolist()}
