from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine

from ..appconfig import AuthConfig
from ..config import Settings
from ..db import otp_challenges, sessions, users
from .mobile import normalize_mobile
from .otp import OtpSender


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass(frozen=True)
class User:
    mobile: str
    role: str  # "admin" | "trader"


@dataclass(frozen=True)
class Login:
    token: str
    user: User
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(self, engine: Engine, settings: Settings, auth: AuthConfig, sender: OtpSender):
        self._engine, self._env, self._cfg, self._sender = engine, settings, auth, sender

    def normalize(self, raw: str) -> str:
        try:
            return normalize_mobile(raw, self._env.default_country_code)
        except ValueError as exc:
            raise AuthError(422, str(exc))

    def role_for(self, mobile: str) -> str:
        return "admin" if mobile in self._env.admin_mobiles else "trader"

    def is_allowed(self, mobile: str) -> bool:
        allowed = self._env.allowed_mobiles
        return not allowed or mobile in allowed or mobile in self._env.admin_mobiles

    def _hash_code(self, mobile: str, code: str) -> str:
        return hmac.new(self._env.secret_key.encode(), f"{mobile}:{code}".encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def request_otp(self, raw_mobile: str) -> int:
        """Creates and sends a code. Returns the resend cooldown in seconds."""
        mobile, now, cfg = self.normalize(raw_mobile), _now(), self._cfg
        if not self.is_allowed(mobile):
            # Same answer as success so the allowlist can't be enumerated; verify will simply fail.
            return cfg.otp_cooldown_seconds
        with self._engine.begin() as conn:
            conn.execute(delete(otp_challenges).where(otp_challenges.c.expires_at < now - timedelta(hours=1)))
            recent = conn.execute(select(func.count()).where(
                otp_challenges.c.mobile == mobile, otp_challenges.c.created_at > now - timedelta(seconds=cfg.otp_cooldown_seconds))).scalar_one()
            if recent:
                raise AuthError(429, f"Please wait {cfg.otp_cooldown_seconds} seconds before requesting another code")
            hourly = conn.execute(select(func.count()).where(
                otp_challenges.c.mobile == mobile, otp_challenges.c.created_at > now - timedelta(hours=1))).scalar_one()
            if hourly >= cfg.otp_hourly_limit:
                raise AuthError(429, "Too many codes requested. Try again later")
            code = self._sender.generate()
            conn.execute(update(otp_challenges).where(otp_challenges.c.mobile == mobile).values(consumed=True))
            conn.execute(otp_challenges.insert().values(
                mobile=mobile, code_hash=self._hash_code(mobile, code), created_at=now,
                expires_at=now + timedelta(seconds=cfg.otp_ttl_seconds), attempts=0, consumed=False))
        self._sender.send(mobile, code)
        return cfg.otp_cooldown_seconds

    def verify_otp(self, raw_mobile: str, code: str) -> Login:
        mobile, now, cfg = self.normalize(raw_mobile), _now(), self._cfg
        code = (code or "").strip()
        if not (code.isdigit() and len(code) == cfg.otp_length):
            raise AuthError(400, "Invalid or expired code")
        failure: Optional[AuthError] = None  # raised after commit so attempt counts persist
        expires, token = now, ""
        with self._engine.begin() as conn:
            failed_last_hour = conn.execute(select(func.coalesce(func.sum(otp_challenges.c.attempts), 0)).where(
                otp_challenges.c.created_at > now - timedelta(hours=1))).scalar_one()
            if failed_last_hour >= cfg.otp_global_failed_per_hour:
                raise AuthError(429, "Sign-in is temporarily paused after too many wrong codes. Try again later")
            row = conn.execute(select(otp_challenges).where(
                otp_challenges.c.mobile == mobile, otp_challenges.c.consumed.is_(False), otp_challenges.c.expires_at > now,
            ).order_by(otp_challenges.c.id.desc()).limit(1)).first()
            if row is None:
                failure = AuthError(400, "Invalid or expired code")
            else:
                ok = hmac.compare_digest(row.code_hash, self._hash_code(mobile, code))
                attempts = row.attempts + (0 if ok else 1)
                conn.execute(update(otp_challenges).where(otp_challenges.c.id == row.id).values(
                    attempts=attempts, consumed=ok or attempts >= cfg.otp_max_attempts))
                if not ok:
                    failure = (AuthError(429, "Too many wrong attempts. Request a new code")
                               if attempts >= cfg.otp_max_attempts else AuthError(400, "Invalid or expired code"))
                else:
                    if conn.execute(select(users.c.id).where(users.c.mobile == mobile)).first() is None:
                        conn.execute(users.insert().values(mobile=mobile, created_at=now, last_login_at=now))
                    else:
                        conn.execute(update(users).where(users.c.mobile == mobile).values(last_login_at=now))
                    conn.execute(delete(sessions).where(sessions.c.expires_at < now))
                    token = secrets.token_urlsafe(32)
                    expires = now + timedelta(hours=cfg.session_ttl_hours)
                    conn.execute(sessions.insert().values(token_hash=self._hash_token(token), mobile=mobile, created_at=now, expires_at=expires))
        if failure:
            raise failure
        return Login(token, User(mobile, self.role_for(mobile)), expires)

    def user_for_token(self, token: Optional[str]) -> Optional[User]:
        if not token:
            return None
        with self._engine.connect() as conn:
            mobile = conn.execute(select(sessions.c.mobile).where(
                sessions.c.token_hash == self._hash_token(token), sessions.c.expires_at > _now())).scalar()
        return User(mobile, self.role_for(mobile)) if mobile else None

    def logout(self, token: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_hash == self._hash_token(token)))
