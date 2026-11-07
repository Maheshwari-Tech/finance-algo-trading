from __future__ import annotations

import logging

from ..appconfig import AppConfig
from .sql_repository import SqlPriceRepository
from .validation import DataValidationError, parse_ohlc_csv

log = logging.getLogger("backtest.seed")


def seed_default_dataset(repo: SqlPriceRepository, config: AppConfig) -> None:
    """Load the bundled default dataset (config/data.json "default_dataset") when the database holds no prices.

    Never overwrites existing data, and never raises: a missing file or a database hiccup must not stop the app.
    """
    spec = config.data.default_dataset
    if not spec:
        return
    path = config.examples_dir / spec["file"]
    try:
        if repo.list_symbols():
            return
        info = repo.save(spec["symbol"], parse_ohlc_csv(path.read_bytes(), config.data.csv), merge=False, updated_by="system")
    except (OSError, ValueError, DataValidationError):
        log.exception("Could not load default dataset %s from %s", spec.get("symbol"), path)
        return
    except Exception:  # noqa: BLE001 - e.g. tables not created yet; the app can still start
        log.exception("Default dataset not loaded")
        return
    log.info("Loaded default dataset %s: %s rows (%s to %s)", info.symbol, info.rows, info.start, info.end)
