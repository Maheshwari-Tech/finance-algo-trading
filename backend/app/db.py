"""Database schema (SQLAlchemy Core). Works on Supabase Postgres and on SQLite for local runs/tests."""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    false,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("mobile", String(20), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True)),
)

otp_challenges = Table(
    "otp_challenges", metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("mobile", String(20), nullable=False, index=True),
    Column("code_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("consumed", Boolean, nullable=False, server_default=false()),
)

sessions = Table(
    "sessions", metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("mobile", String(20), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

instruments = Table(
    "instruments", metadata,
    Column("symbol", String(20), primary_key=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(20)),
)

price_bars = Table(
    "price_bars", metadata,
    Column("symbol", String(20), ForeignKey("instruments.symbol", ondelete="CASCADE"), primary_key=True),
    Column("date", Date, primary_key=True),
    Column("open", Float, nullable=False),
    Column("high", Float, nullable=False),
    Column("low", Float, nullable=False),
    Column("close", Float, nullable=False),
)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # pool_pre_ping survives Supabase pooler restarts. Transaction-mode pooler (port 6543) needs client-side pooling off.
    return create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None},
                         **({"poolclass": NullPool} if ":6543" in url else {}))


def init_schema(engine: Engine) -> None:
    metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        # Supabase exposes `public` tables through its REST API; with RLS on and no policies, only our direct connection can read them.
        with engine.begin() as conn:
            for table in metadata.tables:
                conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
