from __future__ import annotations

import logging
import time
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import text

from ..auth.deps import bearer_token, current_user, require_admin
from ..auth.service import AuthError, User
from ..data.feedback import MAX_SCREENSHOT_BYTES
from ..data.saved import NotFound, SavedRuleOut, StrategyIn, StrategyOut
from ..data.sql_repository import SymbolNotFound
from ..data.validation import DataValidationError, parse_ohlc_csv
from ..domain.results import BacktestResult, RuleTestResult
from ..domain.rules import TradeRule, builder_catalog
from ..observability import BACKTEST_BARS, BACKTEST_SECONDS, BACKTESTS, DB_UP, LOGINS, OTP_REQUESTS, UPLOADS
from ..ratelimit import limit_by_ip
from .schemas import BacktestRequest, LoginOut, OtpRequest, OtpVerify, RuleTestRequest, SymbolOut, UserOut

public = APIRouter(prefix="/api", tags=["Operations"])
auth = APIRouter(prefix="/api/auth", tags=["Sign-in"])
secured = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)], tags=["Admin"])
log = logging.getLogger("backtest.api")


def _repo(request: Request):
    return request.app.state.repo


def _auth(request: Request):
    return request.app.state.auth


@public.get("/health", summary="Liveness check")
def health():
    """Liveness: the process is up. Does not touch the database."""
    return {"status": "ok"}


@public.get("/ready", summary="Readiness check")
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

@auth.get("/config", summary="Sign-in settings", description="Country code, OTP length and auth mode, so the login page can render. No sign-in needed.")
def auth_config(request: Request):
    return {"country_code": request.app.state.settings.default_country_code, "mode": request.app.state.settings.auth_mode,
            "otp_length": request.app.state.config.auth.otp_length}


@auth.post("/request-otp", dependencies=[Depends(limit_by_ip)], summary="Request a one-time code", description="Starts sign-in for a mobile number. With AUTH_MODE=dev nothing is sent: the shared access code is used. Rate-limited per IP and per number.")
def request_otp(body: OtpRequest, request: Request):
    try:
        cooldown = _auth(request).request_otp(body.mobile)
    except AuthError as exc:
        OTP_REQUESTS.labels("refused").inc()
        raise HTTPException(exc.status, exc.message)
    OTP_REQUESTS.labels("sent").inc()
    return {"sent": True, "cooldown_seconds": cooldown}


@auth.post("/verify-otp", response_model=LoginOut, dependencies=[Depends(limit_by_ip)], summary="Verify the code and get a token", description="Returns a session token. Use it as `Authorization: Bearer <token>` (or the Authorize button above).")
def verify_otp(body: OtpVerify, request: Request):
    try:
        login = _auth(request).verify_otp(body.mobile, body.otp)
    except AuthError as exc:
        LOGINS.labels("locked" if exc.status == 429 else "failed").inc()
        raise HTTPException(exc.status, exc.message)
    LOGINS.labels("success").inc()
    log.info("login role=%s", login.user.role)
    return LoginOut(token=login.token, mobile=login.user.mobile, role=login.user.role, expires_at=login.expires_at.isoformat())


@auth.get("/me", response_model=UserOut, summary="Who am I", description="The signed-in mobile number and role (admin or trader).")
def me(user: User = Depends(current_user)):
    return UserOut(mobile=user.mobile, role=user.role)


@auth.post("/logout", summary="Sign out", description="Ends the session for this token.")
def logout(request: Request, token: str = Depends(bearer_token), _: User = Depends(current_user)):
    _auth(request).logout(token)
    return {"ok": True}


# ---- trader ----

@secured.get("/symbols", response_model=List[SymbolOut], summary="List instruments", description="Instruments with uploaded prices: rows, first and last date.", tags=["Catalog"])
def symbols(request: Request):
    return [s.__dict__ for s in _repo(request).list_symbols()]


@secured.get("/strategies", summary="List built-in strategies", description="Each strategy's name, description and parameters (with defaults and limits), plus the period presets.", tags=["Catalog"])
def strategies(request: Request):
    cfg = request.app.state.config
    return {"strategies": [s.describe() for s in request.app.state.strategies.values()], "periods": cfg.analysis.period_ids}


@secured.get("/rule-builder", summary="Rule builder catalog", description="Indicators, comparisons, price fields and limits for writing your own rules.", tags=["Catalog"])
def rule_builder(request: Request):
    return builder_catalog(request.app.state.config.rule_builder)


@secured.get("/ui-config", summary="Dashboard settings", description="Currency, defaults, input limits, thresholds and example rule sets (from config/ui.json and config/rule_templates.json).", tags=["Catalog"])
def ui_config(request: Request):
    cfg = request.app.state.config
    return {**cfg.ui, "rule_templates": cfg.rule_templates}


@secured.post("/backtest", response_model=BacktestResult, summary="Run a strategy with money", description="Runs a built-in strategy or your rules on one instrument and period. Returns every order (with reason), weekly rows, trades, metrics, chart series and the checks that prove the numbers add up.", tags=["Strategy"])
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


@secured.post("/rule-test", response_model=RuleTestResult, summary="Test one rule (no money)",
              description="Every day one rule's conditions are met in the period, with the actual values compared. No money, holdings, charges, limits or other rules.",
              tags=["Test a rule"])
def rule_test(req: RuleTestRequest, request: Request):
    try:
        return request.app.state.backtests.test_rule(req.symbol, req.rule, req.period, req.start, req.end)
    except SymbolNotFound:
        raise HTTPException(404, f"Unknown symbol '{req.symbol}'")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


# ---- saved rules ----

@secured.get("/rules", response_model=List[SavedRuleOut], tags=["Saved rules"], summary="List my saved rules",
             description="Each rule with the saved strategies that use it.")
def rules_list(request: Request, user: User = Depends(current_user)):
    return request.app.state.saved.list_rules(user.mobile)


@secured.post("/rules", response_model=List[SavedRuleOut], tags=["Saved rules"], summary="Save a new rule",
              description="The rule needs a name, unique among your rules. Returns the updated list (the new rule has an id).")
def rules_create(rule: TradeRule, request: Request, user: User = Depends(current_user)):
    try:
        request.app.state.saved.create_rule(user.mobile, rule)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return request.app.state.saved.list_rules(user.mobile)


@secured.put("/rules/{rule_id}", response_model=List[SavedRuleOut], tags=["Saved rules"], summary="Change a saved rule",
             description="Every saved strategy that uses this rule uses the new version.")
def rules_update(rule_id: int, rule: TradeRule, request: Request, user: User = Depends(current_user)):
    try:
        request.app.state.saved.update_rule(user.mobile, rule_id, rule)
    except NotFound as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return request.app.state.saved.list_rules(user.mobile)


@secured.delete("/rules/{rule_id}", response_model=List[SavedRuleOut], tags=["Saved rules"], summary="Delete a saved rule",
                description="Refused (422) while a saved strategy still uses it.")
def rules_delete(rule_id: int, request: Request, user: User = Depends(current_user)):
    try:
        request.app.state.saved.delete_rule(user.mobile, rule_id)
    except NotFound as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return request.app.state.saved.list_rules(user.mobile)


# ---- saved strategies ----

@secured.get("/saved", response_model=List[StrategyOut], tags=["Saved strategies"], summary="List my saved strategies",
             description="Each strategy with the ids of the rules it uses and the current version of those rules.")
def saved_list(request: Request, user: User = Depends(current_user)):
    return request.app.state.saved.list_strategies(user.mobile)


@secured.post("/saved", response_model=List[StrategyOut], tags=["Saved strategies"], summary="Save a strategy",
              description="A name and the ids of your saved rules (buy and sell). Same name replaces. Returns the updated list.")
def saved_save(strategy: StrategyIn, request: Request, user: User = Depends(current_user)):
    try:
        request.app.state.saved.save_strategy(user.mobile, strategy)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return request.app.state.saved.list_strategies(user.mobile)


@secured.delete("/saved/{name}", response_model=List[StrategyOut], tags=["Saved strategies"], summary="Delete a saved strategy",
                description="The rules it used stay saved.")
def saved_delete(name: str, request: Request, user: User = Depends(current_user)):
    if not request.app.state.saved.delete_strategy(user.mobile, name):
        raise HTTPException(404, "No saved strategy with that name")
    return request.app.state.saved.list_strategies(user.mobile)


@secured.post("/feedback", tags=["Feedback"], summary="Send feedback",
              description="Multipart form. Everything is optional, but send at least a message or a screenshot. "
                          "category: Bug, Idea or Other. screenshot: PNG, JPEG, GIF or WebP up to 5 MB. Your mobile number and the time are saved with it.")
def send_feedback(request: Request, message: Optional[str] = Form(None), category: Optional[str] = Form(None),
                  screenshot: Optional[UploadFile] = File(None), user: User = Depends(current_user)):
    data = screenshot.file.read(MAX_SCREENSHOT_BYTES + 1) if screenshot is not None else None
    try:
        item_id = request.app.state.feedback.add(user.mobile, message, category, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    log.info("feedback received id=%s", item_id)
    return {"saved": True, "id": item_id}


# ---- admin ----

@admin.post("/datasets", response_model=SymbolOut, summary="Upload prices (CSV)", description="Admin only. CSV with date, open, high, low, close. mode=replace deletes the instrument's existing rows first; mode=merge updates/adds by date.")
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


@admin.get("/datasets/{symbol}/rows", summary="Browse stored prices",
           description="Admin only. One page of an instrument's prices with optional filters: date range, close range, order. "
                       "Page size 10, 20, 50 or 100.")
def dataset_rows(symbol: str, request: Request, page: int = Query(1, ge=1), size: int = Query(20),
                 start: Optional[date] = None, end: Optional[date] = None,
                 min_close: Optional[float] = None, max_close: Optional[float] = None, order: str = Query("newest")):
    if size not in (10, 20, 50, 100):
        raise HTTPException(422, "size must be 10, 20, 50 or 100")
    if order not in ("newest", "oldest"):
        raise HTTPException(422, "order must be 'newest' or 'oldest'")
    try:
        total, rows = _repo(request).rows(symbol, start, end, min_close, max_close, order == "newest", (page - 1) * size, size)
    except SymbolNotFound:
        raise HTTPException(404, "Unknown symbol")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"symbol": symbol.upper(), "total": total, "page": page, "size": size, "pages": max(1, -(-total // size)), "rows": rows}


@admin.delete("/datasets/{symbol}", summary="Delete an instrument", description="Admin only. Removes the instrument and all its prices.")
def delete_dataset(symbol: str, request: Request):
    try:
        _repo(request).delete(symbol)
    except SymbolNotFound:
        raise HTTPException(404, "Unknown symbol")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"deleted": symbol.upper()}


@admin.get("/upload-spec", summary="CSV upload rules", description="Admin only. Required columns, minimum rows and size limit.")
def upload_spec(request: Request):
    csv_cfg = request.app.state.config.data.csv
    return {"columns": csv_cfg.required_columns, "min_rows": csv_cfg.min_rows, "max_upload_mb": csv_cfg.max_upload_mb}


@admin.get("/feedback", summary="All feedback", description="Admin only. Newest first. Screenshots are fetched separately.")
def list_feedback(request: Request):
    return [i.__dict__ for i in request.app.state.feedback.list()]


@admin.get("/feedback/{item_id}/screenshot", summary="Feedback screenshot", description="Admin only. The image as uploaded.")
def feedback_screenshot(item_id: int, request: Request):
    found = request.app.state.feedback.screenshot(item_id)
    if not found:
        raise HTTPException(404, "No screenshot for this feedback")
    data, kind = found
    return Response(data, media_type=kind, headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
                                                    "Cache-Control": "private, max-age=3600"})


@admin.get("/template.csv", summary="Download CSV template", description="Admin only. Header-only CSV to fill in.")
def template_csv(request: Request):
    data = request.app.state.config.data
    return FileResponse(request.app.state.config.examples_dir / data.template_file, media_type="text/csv", filename=data.template_file)
