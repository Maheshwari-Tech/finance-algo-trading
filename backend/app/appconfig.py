"""Loads tunable, non-secret configuration from JSON files in /config. Secrets and infrastructure come from the environment (config.py)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .config import ROOT, ConfigError


@dataclass(frozen=True)
class AnalysisConfig:
    trading_days_per_year: int
    var_percentile: float
    fee_grid_pct: List[float]
    window_lengths: List[int]
    min_window_samples: int
    majority_threshold: float
    histogram_bins: int
    histogram_clip_percentile: float
    periods: List[Dict[str, Any]]
    max_window_scan: int = 1260  # longest holding window scanned; bounds CPU on very long histories

    @property
    def period_ids(self) -> List[str]:
        return [p["id"] for p in self.periods]


@dataclass(frozen=True)
class CsvConfig:
    required_columns: List[str]
    min_rows: int
    max_rows: int
    max_upload_mb: int


@dataclass(frozen=True)
class DataConfig:
    csv: CsvConfig
    symbol_pattern: str
    template_file: str


@dataclass(frozen=True)
class AuthConfig:
    session_ttl_hours: int
    otp_length: int
    otp_ttl_seconds: int
    otp_max_attempts: int
    otp_cooldown_seconds: int
    otp_hourly_limit: int
    otp_global_failed_per_hour: int = 100  # all numbers combined; stops guessing a shared fixed code across many numbers
    ip_requests_per_minute: int = 10  # per client IP, for request-otp and verify-otp


@dataclass(frozen=True)
class AppConfig:
    analysis: AnalysisConfig
    data: DataConfig
    auth: AuthConfig
    strategies: Dict[str, Dict[str, Any]]
    rule_builder: Dict[str, Any]
    ui: Dict[str, Any]
    rule_templates: List[Dict[str, Any]]
    examples_dir: Path


def _read(directory: Path, name: str) -> Any:
    path = directory / name
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise ConfigError(f"Missing config file {path}")
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}")


def load_app_config() -> AppConfig:
    directory = Path(os.getenv("CONFIG_DIR", ROOT / "config"))
    try:
        data = _read(directory, "data.json")
        return AppConfig(
            analysis=AnalysisConfig(**_read(directory, "analysis.json")),
            data=DataConfig(csv=CsvConfig(**data["csv"]), symbol_pattern=data["symbol_pattern"], template_file=data["template_file"]),
            auth=AuthConfig(**_read(directory, "auth.json")),
            strategies=_read(directory, "strategies.json"),
            rule_builder=_read(directory, "rule_builder.json"),
            ui=_read(directory, "ui.json"),
            rule_templates=_read(directory, "rule_templates.json"),
            examples_dir=Path(os.getenv("EXAMPLES_DIR", ROOT / "examples")),
        )
    except (TypeError, KeyError) as exc:
        raise ConfigError(f"Config files in {directory} are incomplete or malformed: {exc}")
