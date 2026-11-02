from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.appconfig import load_app_config
from app.config import Settings
from app.main import create_app

OTP = "482915"
ADMIN = "+919000000001"
TRADER = "+919000000002"


def make_bars(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    idx = pd.bdate_range("2022-01-03", periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def bars_csv(bars: pd.DataFrame) -> bytes:
    out = bars.copy()
    out.index.name = "date"
    buf = io.StringIO()
    out.reset_index().assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d")).to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", secret_key="x" * 40, admin_mobiles=frozenset({ADMIN}),
        auth_mode="dev", otp_dev_code=OTP, default_country_code="91", cors_origins=(),
        frontend_dist=tmp_path / "no-dist", auto_create_schema=True,
    )


@pytest.fixture
def config():
    return load_app_config()


@pytest.fixture
def make_client(settings, config):
    def _make(**overrides) -> TestClient:
        return TestClient(create_app(replace(settings, **overrides), config))
    return _make


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def login(client: TestClient, mobile: str) -> dict:
    assert client.post("/api/auth/request-otp", json={"mobile": mobile}).status_code == 200
    r = client.post("/api/auth/verify-otp", json={"mobile": mobile, "otp": OTP})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def admin_headers(client) -> dict:
    return login(client, ADMIN)


@pytest.fixture
def loaded(client, admin_headers) -> TestClient:
    r = client.post("/api/admin/datasets", headers=admin_headers, data={"symbol": "nifty", "mode": "replace"},
                    files={"file": ("p.csv", bars_csv(make_bars()), "text/csv")})
    assert r.status_code == 200, r.text
    return client
