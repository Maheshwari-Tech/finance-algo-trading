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
        body = r.json()
        assert len(body["daily"]) == body["bars"] and len(body["rule_legend"]) == len(tpl["rules"])
        assert body["weeks"] and body["months"] and body["period_total"]["days"] == body["bars"]
        assert all(c["ok"] for c in body["checks"]), [c for c in body["checks"] if not c["ok"]]


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


DIP = {"name": "Dip buyer", "action": "buy", "lots": 1, "conditions": [
    {"left": {"kind": "change_pct", "period": 1}, "op": "lt", "right": {"kind": "value", "value": -2}}]}
RIP = {"name": "Rip seller", "action": "sell", "lots": 1, "conditions": [
    {"left": {"kind": "change_pct", "period": 1}, "op": "gt", "right": {"kind": "value", "value": 2}}]}


def test_saved_rules_and_strategies_reference_rules(client):
    a, b = login(client, ADMIN), login(client, TRADER)
    assert client.get("/api/rules", headers=a).json() == []
    client.post("/api/rules", json=DIP, headers=a)
    rules = client.post("/api/rules", json=RIP, headers=a).json()
    ids = {r["name"]: r["id"] for r in rules}
    assert client.post("/api/rules", json=DIP, headers=a).status_code == 422  # duplicate name
    assert client.post("/api/rules", json={**DIP, "name": " "}, headers=a).status_code == 422
    assert client.get("/api/rules", headers=b).json() == []  # other users don't see them

    saved = client.post("/api/saved", json={"name": "Dip & rip", "rule_ids": [ids["Dip buyer"], ids["Rip seller"]]}, headers=a).json()
    assert [r["name"] for r in saved[0]["rules"]] == ["Dip buyer", "Rip seller"]
    assert client.post("/api/saved", json={"name": "x", "rule_ids": [999999]}, headers=a).status_code == 422
    assert client.post("/api/saved", json={"name": "x", "rule_ids": [ids["Dip buyer"]]}, headers=b).status_code == 422  # not b's rule

    # editing a saved rule changes the strategy that refers to it
    client.put(f"/api/rules/{ids['Dip buyer']}", json={**DIP, "lots": 3}, headers=a)
    assert client.get("/api/saved", headers=a).json()[0]["rules"][0]["lots"] == 3
    used = {r["name"]: r["used_by"] for r in client.get("/api/rules", headers=a).json()}
    assert used["Dip buyer"] == ["Dip & rip"]

    assert client.delete(f"/api/rules/{ids['Dip buyer']}", headers=a).status_code == 422  # still used
    assert client.delete("/api/saved/Dip & rip", headers=b).status_code == 404
    assert client.delete("/api/saved/Dip & rip", headers=a).json() == []
    assert [r["name"] for r in client.delete(f"/api/rules/{ids['Dip buyer']}", headers=a).json()] == ["Rip seller"]


def test_rule_test_lists_each_day_for_one_rule(loaded, admin_headers):
    rule = {"name": "Up day", "action": "buy", "lots": 2, "conditions": [
        {"left": {"kind": "change_pct", "period": 1}, "op": "gt", "right": {"kind": "value", "value": 1}}]}
    r = loaded.post("/api/rule-test", headers=admin_headers, json={"symbol": "NIFTY", "rule": rule, "period": "1Y"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rules"] == [{"rule": 1, "sentence": "Buy 2 lots when 1-day change % > 1", "days": len(body["events"])}]
    assert body["events"] and all(e["action"] == "buy" and e["lots"] == 2 and e["date"] in body["dates"] for e in body["events"])



PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_feedback_everything_optional_and_admin_sees_all(client):
    trader, admin = login(client, TRADER), login(client, ADMIN)
    send = lambda data=None, files=None, h=trader: client.post("/api/feedback", data=data or {}, files=files, headers=h)  # noqa: E731
    assert send({"message": "Love the order log"}).json()["saved"] is True
    assert send({"category": "Bug"}, {"screenshot": ("s.png", PNG, "image/png")}).status_code == 200  # screenshot only
    assert send({"message": "x", "category": "Idea"}).status_code == 200
    assert send().status_code == 422  # nothing at all
    assert send({"category": "Rant", "message": "x"}).status_code == 422
    assert send({}, {"screenshot": ("s.svg", b"<svg onload=alert(1)>", "image/svg+xml")}).status_code == 422
    assert client.get("/api/admin/feedback", headers=trader).status_code == 403
    items = client.get("/api/admin/feedback", headers=admin).json()
    assert [i["category"] for i in items] == ["Idea", "Bug", None]  # newest first
    assert all(i["mobile"] == TRADER and i["created_at"] for i in items)
    with_shot = next(i for i in items if i["has_screenshot"])
    r = client.get(f"/api/admin/feedback/{with_shot['id']}/screenshot", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == PNG
    assert client.get(f"/api/admin/feedback/{items[0]['id']}/screenshot", headers=admin).status_code == 404


def test_admin_can_browse_uploaded_prices(loaded, admin_headers):
    url = "/api/admin/datasets/NIFTY/rows"
    first = loaded.get(url, params={"size": 10}, headers=admin_headers).json()
    assert first["total"] == 400 and first["pages"] == 40 and len(first["rows"]) == 10
    assert first["rows"][0]["date"] > first["rows"][-1]["date"]  # newest first by default
    oldest = loaded.get(url, params={"size": 20, "order": "oldest", "page": 2}, headers=admin_headers).json()
    assert len(oldest["rows"]) == 20 and oldest["rows"][0]["date"] < oldest["rows"][-1]["date"]
    d0, d1 = first["rows"][-1]["date"], first["rows"][0]["date"]
    ranged = loaded.get(url, params={"start": d0, "end": d1, "size": 50}, headers=admin_headers).json()
    assert ranged["total"] == 10
    c = sorted(r["close"] for r in first["rows"])
    within = loaded.get(url, params={"min_close": c[2], "max_close": c[7], "size": 100}, headers=admin_headers).json()
    assert all(c[2] <= r["close"] <= c[7] for r in within["rows"])
    assert loaded.get(url, params={"size": 7}, headers=admin_headers).status_code == 422
    assert loaded.get("/api/admin/datasets/NOPE/rows", headers=admin_headers).status_code == 404
    trader = login(loaded, TRADER)
    assert loaded.get(url, headers=trader).status_code == 403
