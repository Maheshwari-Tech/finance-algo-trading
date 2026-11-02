from __future__ import annotations

import secrets
from typing import Protocol

from ..config import ConfigError, Settings


class OtpSender(Protocol):
    """Delivers a one-time code. Implement `send` for your SMS provider and return it from `build_sender`."""

    def generate(self) -> str: ...

    def send(self, mobile: str, code: str) -> None: ...


class DevOtpSender:
    """Development only: every login uses the fixed OTP_DEV_CODE and nothing is sent."""

    def __init__(self, code: str):
        self._code = code

    def generate(self) -> str:
        return self._code

    def send(self, mobile: str, code: str) -> None:
        return None


def random_code(length: int) -> str:
    return f"{secrets.randbelow(10 ** length):0{length}d}"


def build_sender(settings: Settings) -> OtpSender:
    if settings.auth_mode == "dev":
        return DevOtpSender(settings.otp_dev_code or "")
    raise ConfigError("AUTH_MODE=prod needs an SMS provider: implement OtpSender in app/auth/otp.py and return it from build_sender()")
