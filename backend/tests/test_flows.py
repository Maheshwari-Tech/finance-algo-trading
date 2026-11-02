from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.appconfig import load_app_config
from app.config import Settings
from app.domain.engine import EngineConfig, simulate
from app.domain.windows import analyze_windows
from app.main import create_app


def bars_from_close(close):
    idx = pd.bdate_range("2024-01-01", periods=len(close))
    c = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c})


def run(close, orders, **cfg):
    bars = bars_from_close(close)
    return simulate(bars, pd.Series(orders, index=bars.index, dtype=float), EngineConfig(**cfg))


def test_cash_and_equity_from_zero_capital():
    sim = run([100, 110, 121, 121], [1, 0, -1, 0])
    f = sim.frame
    assert f["cash"].tolist() == [-100, -100, 21, 21]  # most negative cash = money you had to put in
    assert f["equity"].tolist() == [0, 10, 21, 21]
    assert sim.trades[0].pnl == pytest.approx(21)


def test_charges_applied_per_fill():
    sim = run([100, 110, 121, 121], [1, 0, -1, 0], fee_pct=1)
    assert sim.frame["fee"].sum() == pytest.approx(1.0 + 1.21)
    assert sim.frame["equity"].iloc[-1] == pytest.approx(21 - 2.21)
    assert sim.frame["equity_no_fee"].iloc[-1] == pytest.approx(21)
    assert sim.trades[0].pnl == pytest.approx(21 - 2.21)


def test_sell_before_buy_toggle():
    close, orders = [100, 90, 80], [-1, 0, 0]
    blocked = run(close, orders, allow_short=False)
    assert blocked.frame["position"].tolist() == [0, 0, 0]
    short = run(close, orders, allow_short=True)
    assert short.frame["position"].tolist() == [-1, -1, -1] and short.frame["equity"].iloc[-1] == pytest.approx(20)
    assert short.trades[0].side == "short" and short.trades[0].is_open


def test_max_position_and_fifo():
    sim = run([10, 11, 12, 13], [1, 1, 1, -1], max_position=2)
    assert sim.frame["position"].tolist() == [1, 2, 2, 1]
    assert [t.entry_date for t in sim.trades][0] < [t.entry_date for t in sim.trades][1]
    closed = [t for t in sim.trades if not t.is_open]
    assert len(closed) == 1 and closed[0].pnl == pytest.approx(3)  # first lot bought at 10, sold at 13


def test_always_profitable_window_on_uptrend():
    eq = np.cumprod(np.full(200, 1.01))
    wa = analyze_windows(eq, 1.0, load_app_config().analysis)
    assert wa.always_profitable_bars == 190 and wa.stats[0].pct_profitable == 1.0


ADMIN, TRADER = "+918847472124", "+919999900001"


def sample_csv(days=400, seed=3) -> bytes:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=days)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, days)))
    open_ = np.concatenate(([100], close[:-1])) * (1 + rng.normal(0, 0.003, days))
    high = np.maximum(open_, close) * 1.004
    low = np.minimum(open_, close) * 0.996
    return pd.DataFrame({"date": idx, "open": open_, "high": high, "low": low, "close": close}).to_csv(index=False).encode()


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", secret_key="x" * 32, admin_mobiles=frozenset({ADMIN}),
        auth_mode="dev", otp_dev_code="123456", default_country_code="91", cors_origins=(),
        frontend_dist=tmp_path / "nodist", auto_create_schema=True)


@pytest.fixture()
def config():
    cfg = load_app_config()
    return replace(cfg, auth=replace(cfg.auth, otp_cooldown_seconds=0, otp_max_attempts=3, otp_hourly_limit=50))


def login(client, mobile, otp="123456"):
    assert client.post("/api/auth/request-otp", json={"mobile": mobile}).status_code == 200
    r = client.post("/api/auth/verify-otp", json={"mobile": mobile, "otp": otp})
    return r


@pytest.fixture()
def client(settings, config):
    c = TestClient(create_app(settings, config))
    token = login(c, "8847472124").json()["token"]  # local-format admin number
    c.headers["Authorization"] = f"Bearer {token}"
    r = c.post("/api/admin/datasets", data={"symbol": "TEST"}, files={"file": ("t.csv", sample_csv(), "text/csv")})
    assert r.status_code == 200, r.text
    return c


def rule(action, lots, *conds, match="all"):
    return {"action": action, "lots": lots, "match": match, "conditions": list(conds)}


def cond(left, op, right):
    return {"left": left, "op": op, "right": right}


CHANGE = {"kind": "change_pct", "period": 1}
def NUM(v):
    return {"kind": "value", "value": v}


def test_api_presets_all_strategies_and_periods(client):
    catalog = client.get("/api/strategies").json()
    assert {s["id"] for s in catalog["strategies"]} == set(load_app_config().strategies)
    for s in catalog["strategies"]:
        for period in catalog["periods"]:
            r = client.post("/api/backtest", json={"symbol": "TEST", "strategy_id": s["id"], "period": period, "initial_capital": 1000})
            assert r.status_code == 200, (s["id"], period, r.text)


def test_custom_lot_rules_and_capital_extremes(client):
    rules = {"name": "1% mover", "rules": [rule("buy", 1, cond(CHANGE, "gt", NUM(1))), rule("sell", 1, cond(CHANGE, "lt", NUM(-1)))]}
    body = {"symbol": "TEST", "period": "1Y", "rules": rules, "initial_capital": 0, "allow_short": True, "max_position": 5}
    r = client.post("/api/backtest", json=body).json()
    m = r["metrics"]
    assert r["strategy_name"] == "1% mover"
    assert m["min_cash"]["value"] <= m["max_cash"]["value"] and m["fills"] > 0
    assert max(abs(p) for p in r["series"]["position"]) <= 5
    nofee = r["metrics"]["total_profit"]
    charged = client.post("/api/backtest", json={**body, "charges_enabled": True, "fee_pct": 1}).json()
    assert charged["metrics"]["fees_paid"] > 0 and charged["metrics"]["total_profit"] < nofee
    assert charged["series"]["equity_no_fee"][-1] == pytest.approx(r["series"]["equity"][-1], abs=0.05)


def test_no_condition_rule_runs_every_day(client):
    body = {"symbol": "TEST", "period": "1M", "rules": {"name": "daily", "rules": [rule("buy", 1)]}, "max_position": 3}
    r = client.post("/api/backtest", json=body).json()
    assert r["series"]["position"][-1] == 3


def test_custom_rules_validation(client):
    assert client.post("/api/backtest", json={"symbol": "TEST", "rules": {"name": "x", "rules": []}}).status_code == 422
    bad_kind = {"name": "x", "rules": [rule("buy", 1, cond({"kind": "exec"}, "gt", NUM(1)))]}
    assert client.post("/api/backtest", json={"symbol": "TEST", "rules": bad_kind}).status_code == 422
    assert client.post("/api/backtest", json={"symbol": "TEST", "rules": {"name": "x", "rules": [rule("hold", 1)]}}).status_code == 422


def test_requires_login(settings, config):
    c = TestClient(create_app(settings, config))
    assert c.get("/api/symbols").status_code == 401
    assert c.post("/api/backtest", json={"symbol": "TEST"}).status_code == 401
    assert c.get("/api/health").status_code == 200


def test_otp_flow_roles_and_logout(settings, config):
    c = TestClient(create_app(settings, config))
    r = login(c, "8847472124")
    assert r.status_code == 200 and r.json()["role"] == "admin" and r.json()["mobile"] == ADMIN
    t = login(c, TRADER).json()
    assert t["role"] == "trader"
    h = {"Authorization": f"Bearer {t['token']}"}
    assert c.get("/api/auth/me", headers=h).json()["mobile"] == TRADER
    assert c.post("/api/auth/logout", headers=h).status_code == 200
    assert c.get("/api/auth/me", headers=h).status_code == 401


def test_wrong_otp_and_lockout(settings, config):
    c = TestClient(create_app(settings, config))
    assert c.post("/api/auth/request-otp", json={"mobile": TRADER}).status_code == 200
    for _ in range(2):
        assert c.post("/api/auth/verify-otp", json={"mobile": TRADER, "otp": "000000"}).status_code == 400
    assert c.post("/api/auth/verify-otp", json={"mobile": TRADER, "otp": "000000"}).status_code == 429
    assert c.post("/api/auth/verify-otp", json={"mobile": TRADER, "otp": "123456"}).status_code == 400  # code burned
    assert c.post("/api/auth/request-otp", json={"mobile": "12"}).status_code == 422


def test_otp_cooldown(settings, config):
    c = TestClient(create_app(settings, replace(config, auth=replace(config.auth, otp_cooldown_seconds=60))))
    assert c.post("/api/auth/request-otp", json={"mobile": TRADER}).status_code == 200
    assert c.post("/api/auth/request-otp", json={"mobile": TRADER}).status_code == 429


def test_trader_cannot_use_admin_endpoints(settings, config):
    c = TestClient(create_app(settings, config))
    c.headers["Authorization"] = f"Bearer {login(c, TRADER).json()['token']}"
    files = {"file": ("t.csv", sample_csv(), "text/csv")}
    assert c.post("/api/admin/datasets", data={"symbol": "X"}, files=files).status_code == 403
    assert c.delete("/api/admin/datasets/X").status_code == 403


def test_admin_upload_merge_validate_delete(client):
    syms = {s["symbol"]: s for s in client.get("/api/symbols").json()}
    assert syms["TEST"]["rows"] == 400
    more = sample_csv(days=450)  # overlaps the first 400 days, adds 50
    r = client.post("/api/admin/datasets", data={"symbol": "test", "mode": "merge"}, files={"file": ("t.csv", more, "text/csv")})
    assert r.json()["rows"] == 450
    r = client.post("/api/admin/datasets", data={"symbol": "TEST", "mode": "replace"}, files={"file": ("t.csv", sample_csv(60), "text/csv")})
    assert r.json()["rows"] == 60
    bad = client.post("/api/admin/datasets", data={"symbol": "BAD"}, files={"file": ("x.csv", b"date,open\n1,2\n", "text/csv")})
    assert bad.status_code == 422
    thousands = b"Date,Open,High,Low,Close\n" + b"".join(
        f'2024-01-{d:02d},"1,000.0","1,010.0","990.0","1,005.0"\n'.encode() for d in range(1, 29)) + b"2024-02-01,1000,1010,990,1005\n2024-02-02,1000,1010,990,1005\n"
    assert client.post("/api/admin/datasets", data={"symbol": "NSE.X"}, files={"file": ("x.csv", thousands, "text/csv")}).status_code == 200
    assert client.delete("/api/admin/datasets/NSE.X").status_code == 200
    assert client.delete("/api/admin/datasets/NSE.X").status_code == 404
    assert client.get("/api/symbols").json()[0]["symbol"] == "TEST"


def test_ui_config_and_template_come_from_files(client):
    ui = client.get("/api/ui-config").json()
    assert ui["rule_templates"] and ui["defaults"]["strategy_id"] == "custom"
    catalog = client.get("/api/rule-builder").json()
    assert {o["kind"] for o in catalog["operands"]} >= {"price", "sma", "rsi"}
    tpl = client.get("/api/admin/template.csv")
    assert tpl.status_code == 200 and tpl.text.strip() == "date,open,high,low,close"
    for t in ui["rule_templates"]:  # every shipped example must actually run
        r = client.post("/api/backtest", json={"symbol": "TEST", "rules": t, "period": "MAX"})
        assert r.status_code == 200, (t["name"], r.text)
