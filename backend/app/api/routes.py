from __future__ import annotations

import logging
import time
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from ..auth.deps import bearer_token, current_user, require_admin
from ..auth.service import AuthError, User
from ..data.sql_repository import SymbolNotFound
from ..data.validation import DataValidationError, parse_ohlc_csv
from ..domain.results import BacktestResult
from ..domain.rules import builder_catalog
from ..observability import BACKTEST_BARS, BACKTEST_SECONDS, BACKTESTS, DB_UP, LOGINS, OTP_REQUESTS, UPLOADS
from ..ratelimit import limit_by_ip
from .schemas import BacktestRequest, LoginOut, OtpRequest, OtpVerify, SymbolOut, UserOut

public = APIRouter(prefix="/api")
auth = APIRouter(prefix="/api/auth")
secured = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])
log = logging.getLogger("backtest.api")


def _repo(request: Request):
    return request.app.state.repo


def _auth(request: Request):
    return request.app.state.auth


@public.get("/health")
def health():
    """Liveness: the process is up. Does not touch the database."""
    return {"status": "ok"}


@public.get("/ready")
def ready(request: Request):
    """Readiness: the database (and Redis, if configured) answer. Used by Docker and the deploy smoke test."""
    checks = {}
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
        DB_UP.set(1)
    except Exception:  # noqa: BLE001
        log.exception("Readiness: database check failed")
        checks["database"] = "error"
        DB_UP.set(0)
    redis = request.app.state.ip_limiter.redis
    if redis is not None:
        try:
            redis.ping()
            checks["redis"] = "ok"
        except Exception:  # noqa: BLE001 - limiter fails open, so Redis being down is degraded, not fatal
            checks["redis"] = "degraded"
    healthy = checks["database"] == "ok"
    return JSONResponse({"status": "ok" if healthy else "error", "checks": checks}, status_code=200 if healthy else 503)


# ---- auth ----

@auth.get("/config")
def auth_config(request: Request):
    return {"country_code": request.app.state.settings.default_country_code, "mode": request.app.state.settings.auth_mode,
            "otp_length": request.app.state.config.auth.otp_length}


@auth.post("/request-otp", dependencies=[Depends(limit_by_ip)])
def request_otp(body: OtpRequest, request: Request):
    try:
        cooldown = _auth(request).request_otp(body.mobile)
    except AuthError as exc:
        OTP_REQUESTS.labels("refused").inc()
        raise HTTPException(exc.status, exc.message)
    OTP_REQUESTS.labels("sent").inc()
    return {"sent": True, "cooldown_seconds": cooldown}


@auth.post("/verify-otp", response_model=LoginOut, dependencies=[Depends(limit_by_ip)])
def verify_otp(body: OtpVerify, request: Request):
    try:
        login = _auth(request).verify_otp(body.mobile, body.otp)
    except AuthError as exc:
        LOGINS.labels("locked" if exc.status == 429 else "failed").inc()
        raise HTTPException(exc.status, exc.message)
    LOGINS.labels("success").inc()
    log.info("login role=%s", login.user.role)
    return LoginOut(token=login.token, mobile=login.user.mobile, role=login.user.role, expires_at=login.expires_at.isoformat())


@auth.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(mobile=user.mobile, role=user.role)


@auth.post("/logout")
def logout(request: Request, token: str = Depends(bearer_token), _: User = Depends(current_user)):
    _auth(request).logout(token)
    return {"ok": True}


# ---- trader ----

@secured.get("/symbols", response_model=List[SymbolOut])
def symbols(request: Request):
    return [s.__dict__ for s in _repo(request).list_symbols()]


@secured.get("/strategies")
def strategies(request: Request):
    cfg = request.app.state.config
    return {"strategies": [s.describe() for s in request.app.state.strategies.values()], "periods": cfg.analysis.period_ids}


@secured.get("/rule-builder")
def rule_builder(request: Request):
    return builder_catalog(request.app.state.config.rule_builder)


@secured.get("/ui-config")
def ui_config(request: Request):
    cfg = request.app.state.config
    return {**cfg.ui, "rule_templates": cfg.rule_templates}


@secured.post("/backtest", response_model=BacktestResult)
def backtest(req: BacktestRequest, request: Request):
    strategy = "custom" if req.rules else req.strategy_id
    if strategy not in request.app.state.strategies and strategy != "custom":
        strategy = "unknown"  # keep metric labels bounded
    start = time.perf_counter()
    try:
        result = request.app.state.backtests.run(req.to_spec())
    except SymbolNotFound:
        BACKTESTS.labels(strategy, "not_found").inc()
        raise HTTPException(404, f"Unknown symbol '{req.symbol}'")
    except ValueError as exc:
        BACKTESTS.labels(strategy, "invalid").inc()
        raise HTTPException(422, str(exc))
    BACKTEST_SECONDS.observe(time.perf_counter() - start)
    BACKTEST_BARS.observe(result.bars)
    BACKTESTS.labels(strategy, "ok").inc()
    return result


# ---- admin ----

@admin.post("/datasets", response_model=SymbolOut)
def upload(request: Request, symbol: str = Form(...), mode: str = Form("replace"), file: UploadFile = File(...),
                 user: User = Depends(require_admin)):
    if mode not in ("replace", "merge"):
        raise HTTPException(422, "mode must be 'replace' or 'merge'")
    csv_cfg = request.app.state.config.data.csv
    limit = csv_cfg.max_upload_mb * 1024 * 1024
    # Sync handler on purpose: parsing and the DB write are blocking, so FastAPI runs this in a worker thread
    # instead of stalling the event loop for every other request.
    raw = file.file.read(limit + 1)
    if len(raw) > limit:
        UPLOADS.labels("too_large").inc()
        raise HTTPException(413, f"File too large (max {csv_cfg.max_upload_mb} MB)")
    try:
        info = _repo(request).save(symbol, parse_ohlc_csv(raw, csv_cfg), merge=(mode == "merge"), updated_by=user.mobile)
    except DataValidationError as exc:
        UPLOADS.labels("invalid").inc()
        raise HTTPException(422, {"message": "Invalid data", "problems": exc.problems})
    except ValueError as exc:
        UPLOADS.labels("invalid").inc()
        raise HTTPException(422, str(exc))
    UPLOADS.labels("ok").inc()
    log.info("dataset upload symbol=%s rows=%s mode=%s", info.symbol, info.rows, mode)
    return info.__dict__


@admin.delete("/datasets/{symbol}")
def delete_dataset(symbol: str, request: Request):
    try:
        _repo(request).delete(symbol)
    except SymbolNotFound:
        raise HTTPException(404, "Unknown symbol")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"deleted": symbol.upper()}


@admin.get("/upload-spec")
def upload_spec(request: Request):
    csv_cfg = request.app.state.config.data.csv
    return {"columns": csv_cfg.required_columns, "min_rows": csv_cfg.min_rows, "max_upload_mb": csv_cfg.max_upload_mb}


@admin.get("/template.csv")
def template_csv(request: Request):
    data = request.app.state.config.data
    return FileResponse(request.app.state.config.examples_dir / data.template_file, media_type="text/csv", filename=data.template_file)
