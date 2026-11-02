from __future__ import annotations

from typing import Any, Dict, Type

from ...config import ConfigError
from .base import Strategy

_CLASSES: Dict[str, Type[Strategy]] = {}


def register(cls: Type[Strategy]) -> Type[Strategy]:
    """Class decorator: add the class here and its metadata to config/strategies.json."""
    _CLASSES[cls.id] = cls
    return cls


def build_strategies(meta: Dict[str, Dict[str, Any]]) -> Dict[str, Strategy]:
    missing = set(_CLASSES) - set(meta)
    unknown = set(meta) - set(_CLASSES)
    if missing or unknown:
        raise ConfigError(f"config/strategies.json mismatch. No metadata for: {sorted(missing)}; no implementation for: {sorted(unknown)}")
    return {sid: cls(meta[sid]) for sid, cls in _CLASSES.items()}
