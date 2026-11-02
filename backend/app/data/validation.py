from __future__ import annotations

import io
from typing import List

import pandas as pd

from ..appconfig import CsvConfig


class DataValidationError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def parse_ohlc_csv(raw: bytes, cfg: CsvConfig) -> pd.DataFrame:
    required, numeric = cfg.required_columns, cfg.required_columns[1:]
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        raise DataValidationError(["File is not a readable CSV"])
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataValidationError([f"Missing columns: {', '.join(missing)}. Expected: {', '.join(required)}"])
    df = df[required]
    if len(df) < cfg.min_rows:
        raise DataValidationError([f"At least {cfg.min_rows} rows are required"])
    if len(df) > cfg.max_rows:
        raise DataValidationError([f"Too many rows (max {cfg.max_rows})"])

    problems: List[str] = []
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in numeric:
        if not pd.api.types.is_numeric_dtype(df[c]):  # pandas 3 reads text as 'str', not object
            df[c] = df[c].astype(str).str.replace(",", "", regex=False).str.strip()
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df.isna().any().any():
        problems.append(f"{int(df.isna().any(axis=1).sum())} rows have unparseable or empty values")
    if df["date"].duplicated().any():
        problems.append("Duplicate dates found")
    if (df[numeric] <= 0).any().any():
        problems.append("Prices must be positive")
    bad = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (df["low"] > df[["open", "close", "high"]].min(axis=1))
    if bad.any():
        problems.append(f"{int(bad.sum())} rows violate low <= open/close <= high")
    if problems:
        raise DataValidationError(problems)
    return df.set_index("date").sort_index()
