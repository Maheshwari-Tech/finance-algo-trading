"""One-shot database preparation: create tables, then load the bundled default dataset if the database has no prices.

Run once per deploy, before the API pods roll out:  python -m app.dbinit
(Kubernetes: the Helm pre-install/pre-upgrade Job.) Safe to repeat.
"""
from __future__ import annotations

import logging
import sys

from .appconfig import load_app_config
from .config import ConfigError, Settings
from .data.seed import seed_default_dataset
from .data.sql_repository import SqlPriceRepository
from .db import init_schema, make_engine
from .observability import setup_logging

log = logging.getLogger("backtest.dbinit")


def main() -> int:
    try:
        settings, config = Settings.from_env(), load_app_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.log_level, settings.log_json)
    engine = make_engine(settings.database_url)
    init_schema(engine)
    log.info("Schema ready")
    seed_default_dataset(SqlPriceRepository(engine, config.data.symbol_pattern), config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
