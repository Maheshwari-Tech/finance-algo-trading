from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import List

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine

from ..db import instruments, price_bars
from .repository import PriceRepository, SymbolInfo

CHUNK = 2000  # rows per INSERT statement (driver parameter limits)


class SymbolNotFound(KeyError):
    pass


def _insert(engine: Engine):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


class SqlPriceRepository(PriceRepository):
    def __init__(self, engine: Engine, symbol_pattern: str):
        self._engine = engine
        self._symbol_re = re.compile(symbol_pattern)
        self._insert = _insert(engine)

    def clean_symbol(self, symbol: str) -> str:
        symbol = (symbol or "").strip().upper()
        if not self._symbol_re.match(symbol):
            raise ValueError("Invalid symbol: use letters, digits and . _ & - only")
        return symbol

    def list_symbols(self) -> List[SymbolInfo]:
        q = (select(price_bars.c.symbol, func.count(), func.min(price_bars.c.date), func.max(price_bars.c.date))
             .group_by(price_bars.c.symbol).order_by(price_bars.c.symbol))
        with self._engine.connect() as conn:
            return [SymbolInfo(sym, n, str(lo)[:10], str(hi)[:10]) for sym, n, lo, hi in conn.execute(q)]

    def load(self, symbol: str) -> pd.DataFrame:
        symbol = self.clean_symbol(symbol)
        q = (select(price_bars.c.date, price_bars.c.open, price_bars.c.high, price_bars.c.low, price_bars.c.close)
             .where(price_bars.c.symbol == symbol).order_by(price_bars.c.date))
        with self._engine.connect() as conn:
            rows = conn.execute(q).all()
        if not rows:
            raise SymbolNotFound(symbol)
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    def save(self, symbol: str, bars: pd.DataFrame, merge: bool, updated_by: str) -> SymbolInfo:
        symbol = self.clean_symbol(symbol)
        now = datetime.now(UTC)
        records = [
            {"symbol": symbol, "date": d.date(), "open": float(o), "high": float(h), "low": float(lo), "close": float(c)}
            for d, o, h, lo, c in zip(bars.index, bars["open"], bars["high"], bars["low"], bars["close"], strict=True)
        ]
        with self._engine.begin() as conn:
            inst = self._insert(instruments).values(symbol=symbol, updated_at=now, updated_by=updated_by)
            conn.execute(inst.on_conflict_do_update(index_elements=["symbol"], set_={"updated_at": now, "updated_by": updated_by}))
            if not merge:
                conn.execute(delete(price_bars).where(price_bars.c.symbol == symbol))
            for i in range(0, len(records), CHUNK):
                stmt = self._insert(price_bars).values(records[i:i + CHUNK])
                conn.execute(stmt.on_conflict_do_update(
                    index_elements=["symbol", "date"],
                    set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close")}))
        return next(s for s in self.list_symbols() if s.symbol == symbol)

    def delete(self, symbol: str) -> None:
        symbol = self.clean_symbol(symbol)
        with self._engine.begin() as conn:
            conn.execute(delete(price_bars).where(price_bars.c.symbol == symbol))
            if conn.execute(delete(instruments).where(instruments.c.symbol == symbol)).rowcount == 0:
                raise SymbolNotFound(symbol)
