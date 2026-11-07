from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional

from dotenv import load_dotenv

from .auth.mobile import normalize_mobile

ROOT = Path(__file__).resolve().parents[2]

# Codes nobody should be able to guess. Checked only when APP_ENV=production.
_WEAK_CODES = {"123456", "654321", "000000", "111111", "123123", "112233", "121212", "12345678", "00000000"}


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable {name} (see .env.example)")
    return value


def _mobiles(raw: str, country: str) -> FrozenSet[str]:
    return frozenset(normalize_mobile(m, country) for m in raw.split(",") if m.strip())


def _database_url(raw: str) -> str:
    """Accept Supabase/Heroku style URLs and select the psycopg3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix):]
    return raw


def _is_weak(code: str) -> bool:
    return code in _WEAK_CODES or len(set(code)) <= 2 or code in "0123456789012345" or code in "9876543210987654"


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    admin_mobiles: FrozenSet[str]
    auth_mode: str  # "dev": fixed OTP, nothing is sent.  "prod": real SMS provider required
    otp_dev_code: Optional[str]
    default_country_code: str
    cors_origins: tuple
    frontend_dist: Path
    auto_create_schema: bool
    app_env: str = "development"  # "development" | "production"
    allowed_mobiles: FrozenSet[str] = frozenset()  # empty = anyone may sign in; otherwise only these + admins
    log_level: str = "INFO"
    log_json: bool = False
    redis_url: Optional[str] = None  # optional; shared rate-limit counters across app replicas
    seed_default_dataset: bool = True  # load the bundled dataset at startup; off for replicas, a one-shot job does it (app.dbinit)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @staticmethod
    def from_env() -> Settings:
        load_dotenv(ROOT / ".env")
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env not in ("development", "production"):
            raise ConfigError("APP_ENV must be 'development' or 'production'")
        country = _required("DEFAULT_COUNTRY_CODE").lstrip("+")
        mode = _required("AUTH_MODE").lower()
        if mode not in ("dev", "prod"):
            raise ConfigError("AUTH_MODE must be 'dev' or 'prod'")
        secret = _required("SECRET_KEY")
        if len(secret) < (32 if app_env == "production" else 16):
            raise ConfigError("SECRET_KEY is too short (production needs 32+ characters)")
        otp_code = _required("OTP_DEV_CODE") if mode == "dev" else None
        if otp_code and app_env == "production" and _is_weak(otp_code):
            raise ConfigError("OTP_DEV_CODE is too easy to guess for production. Pick a random code.")
        return Settings(
            database_url=_database_url(_required("DATABASE_URL")),
            secret_key=secret,
            admin_mobiles=_mobiles(_required("ADMIN_MOBILES"), country),
            auth_mode=mode,
            otp_dev_code=otp_code,
            default_country_code=country,
            cors_origins=tuple(o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()),
            frontend_dist=Path(os.getenv("FRONTEND_DIST", ROOT / "frontend" / "dist")).resolve(),
            auto_create_schema=os.getenv("AUTO_CREATE_SCHEMA", "").lower() == "true",
            app_env=app_env,
            allowed_mobiles=_mobiles(os.getenv("ALLOWED_MOBILES", ""), country),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            redis_url=os.getenv("REDIS_URL", "").strip() or None,
            seed_default_dataset=os.getenv("SEED_DEFAULT_DATASET", "true").lower() != "false",
            log_json=os.getenv("LOG_JSON", "true" if app_env == "production" else "false").lower() == "true",
        )
