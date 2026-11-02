"""Rolling holding-window analysis: "if I'd run this strategy for L bars, how often would I profit?"."""
from __future__ import annotations

import numpy as np

from ..appconfig import AnalysisConfig
from .results import WindowAnalysis, WindowStat


def analyze_windows(equity: np.ndarray, base: float, cfg: AnalysisConfig) -> WindowAnalysis:
    """Windows are measured as the change in net worth, as a fraction of `base`."""
    n = len(equity)
    max_len = min(max(n - cfg.min_window_samples, 1), cfg.max_window_scan)
    always = majority = best_len = 0
    best_per_bar = -np.inf
    total, per_len = 0, {}
    for length in range(1, max_len + 1):
        r = (equity[length:] - equity[:-length]) / base
        pct = float((r > 0).mean())
        total += len(r)
        per_len[length] = r
        if pct >= 1.0:
            always = length
        if pct >= cfg.majority_threshold:
            majority = length
        score = float(r.mean()) / length
        if score > best_per_bar:
            best_per_bar, best_len = score, length
    stats = [
        WindowStat(
            bars=L, pct_profitable=float((per_len[L] > 0).mean()), avg_return=float(per_len[L].mean()),
            median_return=float(np.median(per_len[L])), best_return=float(per_len[L].max()),
            worst_return=float(per_len[L].min()), samples=len(per_len[L]),
        )
        for L in cfg.window_lengths if L <= max_len
    ]
    return WindowAnalysis(stats=stats, always_profitable_bars=always, majority_profitable_bars=majority,
                          best_hold_bars=best_len, total_windows_tested=total,
                          majority_threshold=cfg.majority_threshold)
