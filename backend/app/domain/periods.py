from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def resolve_period(index: pd.DatetimeIndex, preset: Optional[str], start: Optional[date], end: Optional[date],
                   periods: List[Dict[str, Any]]) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """`periods` comes from config/analysis.json. Presets are measured back from the last available bar."""
    last, first = index[-1], index[0]
    if start or end:
        s = pd.Timestamp(start) if start else first
        e = pd.Timestamp(end) if end else last
    else:
        by_id = {p["id"]: p for p in periods}
        spec = by_id.get((preset or "").upper())
        if spec is None:
            raise ValueError(f"Unknown period '{preset}'")
        kind = spec.get("kind", "offset")
        s = first if kind == "max" else pd.Timestamp(year=last.year, month=1, day=1) if kind == "ytd" else last - pd.DateOffset(**spec["offset"])
        e = last
    s, e = max(s, first), min(e, last)
    if s >= e:
        raise ValueError("Selected period contains no data")
    return s, e
