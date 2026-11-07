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
from .data.feedback import FeedbackStore
from .data.saved import SavedLibrary
from .data.sql_repository import SqlPriceRepository
from .db import init_schema, make_engine
from .domain.strategies import build_strategies
from .observability import install_metrics, setup_logging
from .ratelimit import IpRateLimiter
from .services.service import BacktestService

log = logging.getLogger("backtest")

API_DESCRIPTION = """
Backtest trading rules on real price history and get results anyone can check by hand.

**Sign in:** `POST /api/auth/request-otp`, then `POST /api/auth/verify-otp` returns a token.
Click **Authorize** and paste the token to call the other endpoints from this page.

Full reference with curl examples: `docs/api.md` in the repository.
"""

API_TAGS = [
    {"name": "Sign-in", "description": "Mobile number + one-time code. Returns a session token."},
    {"name": "Catalog", "description": "Instruments, built-in strategies, rule-builder options and dashboard settings."},
    {"name": "Test a rule", "description": "See every day one rule would place its order, with the values compared. No money."},
    {"name": "Strategy", "description": "Run a strategy with money: orders, weekly rows, trades, metrics and checks."},
    {"name": "Saved rules", "description": "Rules saved under your login. Strategies refer to them, so a change applies everywhere."},
    {"name": "Saved strategies", "description": "Strategies saved under your login: a name plus the saved buy and sell rules they use."},
    {"name": "Feedback", "description": "Send feedback: optional message, category and screenshot."},
    {"name": "Admin", "description": "Price data and all feedback. Admin role only."},
    {"name": "Operations", "description": "Health and readiness for monitoring and deploys."},
]


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
    app = FastAPI(title="Strategic Trader", version="2.0.0", description=API_DESCRIPTION, openapi_tags=API_TAGS, **docs)
    repo = SqlPriceRepository(engine, config.data.symbol_pattern)
    strategies = build_strategies(config.strategies)
    app.state.settings, app.state.config, app.state.repo, app.state.strategies = settings, config, repo, strategies
    app.state.engine = engine
    app.state.saved = SavedLibrary(engine)
    app.state.feedback = FeedbackStore(engine)
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
