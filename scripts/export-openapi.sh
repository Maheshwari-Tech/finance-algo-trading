#!/usr/bin/env bash
# Write the API spec (the same one Swagger shows) to docs/openapi.json. No database or .env needed.
set -euo pipefail
cd "$(dirname "$0")/../backend"
../.venv/bin/python - <<'PY'
import json, os, pathlib
os.environ.update(APP_ENV="development", DATABASE_URL="sqlite://", SECRET_KEY="export-openapi-only-0123456789",
                  ADMIN_MOBILES="9000000001", DEFAULT_COUNTRY_CODE="91", AUTH_MODE="dev", OTP_DEV_CODE="000000")
os.environ.pop("REDIS_URL", None)
from app.config import Settings
from app.main import create_app
s = Settings.from_env()
spec = create_app(s).openapi()
out = pathlib.Path("../docs/openapi.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(spec, indent=2) + "\n")
print(f"wrote {out.resolve()} ({len(spec['paths'])} paths)")
PY
