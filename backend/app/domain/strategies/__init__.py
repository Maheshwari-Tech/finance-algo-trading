from . import builtin  # noqa: F401  (registers the built-in strategies)
from .registry import build_strategies

__all__ = ["build_strategies"]
