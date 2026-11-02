-- Same schema as backend/app/db.py. Run once in your Postgres (or set AUTO_CREATE_SCHEMA=true on first start).
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    mobile VARCHAR(20) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS otp_challenges (
    id BIGSERIAL PRIMARY KEY,
    mobile VARCHAR(20) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    consumed BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_otp_challenges_mobile ON otp_challenges (mobile);
CREATE INDEX IF NOT EXISTS ix_otp_challenges_created_at ON otp_challenges (created_at);

CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    mobile VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_mobile ON sessions (mobile);

CREATE TABLE IF NOT EXISTS instruments (
    symbol VARCHAR(20) PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL,
    updated_by VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS price_bars (
    symbol VARCHAR(20) NOT NULL REFERENCES instruments (symbol) ON DELETE CASCADE,
    date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (symbol, date)
);
