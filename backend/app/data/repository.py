"""Storage abstraction. Swap the CSV implementation for a DB without touching the domain."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    rows: int
    start: str
    end: str


class PriceRepository(ABC):
    @abstractmethod
    def list_symbols(self) -> List[SymbolInfo]: ...

    @abstractmethod
    def load(self, symbol: str) -> pd.DataFrame:
        """DataFrame indexed by DatetimeIndex with open/high/low/close columns, sorted ascending."""

    @abstractmethod
    def save(self, symbol: str, bars: pd.DataFrame, merge: bool, updated_by: str) -> SymbolInfo: ...

    @abstractmethod
    def delete(self, symbol: str) -> None: ...
