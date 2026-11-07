from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.appconfig import load_app_config
from app.main import create_app

from .conftest import ADMIN, bars_csv, login, make_bars


def _client(settings, **overrides) -> TestClient:
    cfg = load_app_config()
    cfg = replace(cfg, auth=replace(cfg.auth, otp_cooldown_seconds=0, otp_hourly_limit=50))
    return TestClient(create_app(replace(settings, **overrides), cfg))


def test_bundled_dataset_is_loaded_on_first_start(settings):
    client = _client(settings)
    symbols = client.get("/api/symbols", headers=login(client, ADMIN)).json()
    assert [s["symbol"] for s in symbols] == ["NIFTY50"]
    assert symbols[0]["rows"] > 1000


def test_seed_keeps_existing_data_and_admin_can_upload_another(settings):
    first = _client(settings)
    headers = login(first, ADMIN)
    r = first.post("/api/admin/datasets", headers=headers, data={"symbol": "OTHER", "mode": "replace"},
                   files={"file": ("p.csv", bars_csv(make_bars()), "text/csv")})
    assert r.status_code == 200
    assert first.delete("/api/admin/datasets/NIFTY50", headers=headers).status_code == 200

    restarted = _client(settings)  # database is not empty, so nothing is re-added
    names = [s["symbol"] for s in restarted.get("/api/symbols", headers=login(restarted, ADMIN)).json()]
    assert names == ["OTHER"]


def test_seeding_can_be_switched_off(settings):
    client = _client(settings, seed_default_dataset=False)
    assert client.get("/api/symbols", headers=login(client, ADMIN)).json() == []


def test_dbinit_creates_schema_and_loads_default(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect

    from app import dbinit

    db = tmp_path / "init.db"
    for key, value in {"DATABASE_URL": f"sqlite:///{db}", "SECRET_KEY": "x" * 40, "ADMIN_MOBILES": "9000000001",
                       "DEFAULT_COUNTRY_CODE": "91", "AUTH_MODE": "dev", "OTP_DEV_CODE": "482915"}.items():
        monkeypatch.setenv(key, value)
    assert dbinit.main() == 0
    assert dbinit.main() == 0  # repeatable
    engine = create_engine(f"sqlite:///{db}")
    assert "price_bars" in inspect(engine).get_table_names()
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM instruments").scalar() == 1
