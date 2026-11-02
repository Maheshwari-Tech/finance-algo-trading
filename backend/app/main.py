from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import admin, auth, public, secured
from .appconfig import AppConfig, load_app_config
from .auth.otp import build_sender
from .auth.service import AuthService
from .config import ConfigError, Settings
from .data.sql_repository import SqlPriceRepository
from .db import init_schema, make_engine
from .domain.strategies import build_strategies
from .observability import install_metrics, setup_logging
from .ratelimit import IpRateLimiter
from .services.service import BacktestService

log = logging.getLogger("backtest")


def create_app(settings: Optional[Settings] = None, config: Optional[AppConfig] = None) -> FastAPI:
    """Run with: uvicorn app.main:create_app --factory"""
    settings = settings or Settings.from_env()
    config = config or load_app_config()
    setup_logging(settings.log_level, settings.log_json)
    if settings.otp_dev_code and len(settings.otp_dev_code) != config.auth.otp_length:
        raise ConfigError(f"OTP_DEV_CODE must be {config.auth.otp_length} digits")
    engine = make_engine(settings.database_url)
    if settings.auto_create_schema:
        init_schema(engine)
    if settings.auth_mode == "dev":
        if settings.is_production:
            log.warning("AUTH_MODE=dev in production: one shared access code. Keep OTP_DEV_CODE private; "
                        "per-IP and global wrong-code limits are active. allowlist=%s", bool(settings.allowed_mobiles))
        else:
            log.warning("AUTH_MODE=dev: a fixed OTP is accepted for every mobile number, including admins.")

    docs = {} if not settings.is_production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Backtest Lab", version="2.0.0", **docs)
    repo = SqlPriceRepository(engine, config.data.symbol_pattern)
    strategies = build_strategies(config.strategies)
    app.state.settings, app.state.config, app.state.repo, app.state.strategies = settings, config, repo, strategies
    app.state.engine = engine
    app.state.backtests = BacktestService(repo, strategies, config.analysis)
    app.state.auth = AuthService(engine, settings, config.auth, build_sender(settings))
    app.state.ip_limiter = IpRateLimiter(config.auth.ip_requests_per_minute, settings.redis_url)

    install_metrics(app)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])
    for router in (public, auth, secured, admin):
        app.include_router(router)

    dist = settings.frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = (dist / path).resolve()
            return FileResponse(file if file.is_file() and dist in file.parents else dist / "index.html")
    else:
        log.info("No frontend build at %s; serving the API only", dist)

    log.info("Backtest Lab started env=%s db=%s", settings.app_env, engine.dialect.name)
    return app
