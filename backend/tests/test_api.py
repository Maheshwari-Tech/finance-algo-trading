from __future__ import annotations

from dataclasses import replace

import pytest

from app.config import ConfigError, Settings

from .conftest import ADMIN, OTP, TRADER, login


def test_health_ready_and_metrics(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"
    body = client.get("/metrics").text
    assert "http_requests_total" in body and 'route="/api/health"' in body


def test_protected_routes_need_login(client):
    assert client.get("/api/symbols").status_code == 401


def test_login_roles_and_admin_guard(client):
    trader = login(client, TRADER)
    assert client.get("/api/auth/me", headers=trader).json()["role"] == "trader"
    assert client.get("/api/admin/upload-spec", headers=trader).status_code == 403
    admin = login(client, ADMIN)
    assert client.get("/api/admin/upload-spec", headers=admin).status_code == 200
    assert client.post("/api/auth/logout", headers=admin).status_code == 200
    assert client.get("/api/auth/me", headers=admin).status_code == 401


def test_wrong_code_is_rejected(client):
    client.post("/api/auth/request-otp", json={"mobile": TRADER})
    assert client.post("/api/auth/verify-otp", json={"mobile": TRADER, "otp": "000001"}).status_code == 400


def test_global_wrong_code_limit_pauses_sign_in(make_client, config):
    client = make_client()
    client.app.state.config = config  # same object; limit patched below
    client.app.state.auth._cfg = replace(config.auth, otp_global_failed_per_hour=2, otp_cooldown_seconds=0)
    client.app.state.ip_limiter.per_minute = 1000
    for i in range(2):
        m = f"+91900000010{i}"
        client.post("/api/auth/request-otp", json={"mobile": m})
        client.post("/api/auth/verify-otp", json={"mobile": m, "otp": "000001"})
    client.post("/api/auth/request-otp", json={"mobile": ADMIN})
    r = client.post("/api/auth/verify-otp", json={"mobile": ADMIN, "otp": OTP})
    assert r.status_code == 429


def test_ip_rate_limit(client):
    client.app.state.ip_limiter.per_minute = 3
    codes = [client.post("/api/auth/verify-otp", json={"mobile": TRADER, "otp": "000001"}).status_code for _ in range(5)]
    assert codes[-1] == 429


def test_allowlist_blocks_unknown_numbers_without_revealing_it(make_client):
    client = make_client(allowed_mobiles=frozenset({TRADER}))
    stranger = "+919000000099"
    assert client.post("/api/auth/request-otp", json={"mobile": stranger}).status_code == 200
    assert client.post("/api/auth/verify-otp", json={"mobile": stranger, "otp": OTP}).status_code == 400
    login(client, TRADER)
    login(client, ADMIN)


def test_catalogs_match_config(loaded, admin_headers):
    rb = loaded.get("/api/rule-builder", headers=admin_headers)
    assert rb.status_code == 200 and {o["kind"] for o in rb.json()["operands"]} >= {"sma", "rsi", "value"}
    ui = loaded.get("/api/ui-config", headers=admin_headers).json()
    assert any(t["name"] == ui["initial_rule_set"] for t in ui["rule_templates"])
    assert loaded.get("/api/admin/template.csv", headers=admin_headers).text.startswith("date,open")


def test_every_rule_template_backtests(loaded, admin_headers):
    ui = loaded.get("/api/ui-config", headers=admin_headers).json()
    for tpl in ui["rule_templates"]:
        r = loaded.post("/api/backtest", headers=admin_headers, json={"symbol": "NIFTY", "rules": tpl, "period": "MAX"})
        assert r.status_code == 200, (tpl["name"], r.text)


@pytest.mark.parametrize("sid", ["price_move", "sma_cross", "rsi", "breakout", "momentum", "buy_hold"])
def test_every_builtin_strategy_backtests(loaded, admin_headers, sid):
    r = loaded.post("/api/backtest", headers=admin_headers,
                    json={"symbol": "NIFTY", "strategy_id": sid, "period": "1Y", "charges_enabled": True, "fee_pct": 0.1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bars"] > 200 and len(body["series"]["equity"]) == body["bars"]


def test_backtest_errors(loaded, admin_headers):
    assert loaded.post("/api/backtest", headers=admin_headers, json={"symbol": "NOPE", "strategy_id": "buy_hold"}).status_code == 404
    assert loaded.post("/api/backtest", headers=admin_headers, json={"symbol": "NIFTY", "strategy_id": "zzz"}).status_code == 422


def test_production_settings_refuse_weak_secrets(monkeypatch):
    env = {"APP_ENV": "production", "DEFAULT_COUNTRY_CODE": "91", "AUTH_MODE": "dev", "SECRET_KEY": "s" * 40,
           "ADMIN_MOBILES": "9000000001", "DATABASE_URL": "sqlite://", "OTP_DEV_CODE": "123456"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ConfigError, match="too easy"):
        Settings.from_env()
    monkeypatch.setenv("OTP_DEV_CODE", "482915")
    s = Settings.from_env()
    assert s.is_production and s.log_json
