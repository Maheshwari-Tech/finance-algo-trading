#!/usr/bin/env bash
# Verifies the project end to end on your machine. Nothing is pushed or deployed.
#
#   ./scripts/verify.sh            all steps
#   ./scripts/verify.sh --no-aiven skip the check against the Postgres/Valkey in .env
#   ./scripts/verify.sh --no-docker skip the Docker image build
#
# Full output goes to verify.log; a pass/fail summary is printed at the end.
# Secrets from .env are never printed.

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LOG="$ROOT/verify.log"
PORT=8199
RUN_AIVEN=1
RUN_DOCKER=1
for arg in "$@"; do
  case "$arg" in
    --no-aiven) RUN_AIVEN=0 ;;
    --no-docker) RUN_DOCKER=0 ;;
    *) echo "unknown option $arg"; exit 2 ;;
  esac
done

: > "$LOG"
RESULTS=()
FAILED=0
APP_PID=""

cleanup() { [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null; rm -rf "$ROOT/var/verify"; }
trap cleanup EXIT

step() {  # step "name" command...
  local name="$1"; shift
  printf '\n==> %s\n' "$name" | tee -a "$LOG"
  local start=$SECONDS
  if "$@" >>"$LOG" 2>&1; then
    RESULTS+=("PASS  $name ($((SECONDS - start))s)")
    echo "    PASS" | tee -a "$LOG"
  else
    RESULTS+=("FAIL  $name ($((SECONDS - start))s)")
    FAILED=1
    echo "    FAIL - last lines:" | tee -a "$LOG"
    tail -n 25 "$LOG" | sed 's/^/    | /'
  fi
}

skip() { RESULTS+=("SKIP  $1 - $2"); printf '\n==> %s\n    SKIP: %s\n' "$1" "$2" | tee -a "$LOG"; }

# ---------- 1. Tools ----------
find_python() {
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}
PY="$(find_python || true)"
echo "Algo trading Lab verification  $(date)" | tee -a "$LOG"
if [ -z "$PY" ]; then
  echo "Python 3.11+ not found (macOS's built-in python3 is 3.9). Install one with Homebrew: brew install python" | tee -a "$LOG"
  exit 1
fi
echo "python: $PY ($("$PY" --version 2>&1))   node: $(node --version 2>/dev/null || echo missing)" | tee -a "$LOG"
command -v node >/dev/null || { echo "Node 20+ not found. Install it:  brew install node@22"; exit 1; }

# ---------- 2. Python environment ----------
make_venv() {
  if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    echo "Existing .venv uses $(.venv/bin/python --version 2>&1); recreating with $PY"
    rm -rf .venv
  fi
  [ -x .venv/bin/python ] || "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  # Output goes to the terminal as well as verify.log so you can see each package as it installs.
  # --prefer-binary uses ready-made wheels whenever one exists; anything without one is built from source (visible below).
  .venv/bin/pip install --prefer-binary --progress-bar off -r backend/requirements-dev.txt 2>&1 | tee /dev/tty
  return "${PIPESTATUS[0]}"
}
step "Install Python dependencies" make_venv

# ---------- 3. Lint + tests ----------
step "Lint (ruff)" bash -c "cd backend && ../.venv/bin/ruff check app tests"
step "Backend tests (pytest)" bash -c "cd backend && ../.venv/bin/pytest -v -p no:cacheprovider"

# ---------- 4. Frontend ----------
step "Frontend install (npm ci)" bash -c "cd frontend && npm ci --no-audit --no-fund"
step "Frontend typecheck + build" bash -c "cd frontend && npm run build"

# ---------- 5. Boot the real app and click through it over HTTP (local SQLite, not Aiven) ----------
smoke() {
  mkdir -p var/verify
  local code=739214
  (cd backend && exec env -i PATH="$PATH" HOME="$HOME" \
      APP_ENV=development DATABASE_URL="sqlite:///$ROOT/var/verify/smoke.db" AUTO_CREATE_SCHEMA=true \
      SECRET_KEY=verify-script-secret-key-0123456789 ADMIN_MOBILES=9000000001 DEFAULT_COUNTRY_CODE=91 \
      AUTH_MODE=dev OTP_DEV_CODE=$code \
      ../.venv/bin/uvicorn app.main:create_app --factory --port $PORT >"$ROOT/var/verify/app.log" 2>&1) &
  APP_PID=$!
  ROOT="$ROOT" PORT=$PORT CODE=$code .venv/bin/python - <<'PY'
import io, json, os, sys, time, urllib.error, urllib.request, uuid
import numpy as np, pandas as pd

base = f"http://127.0.0.1:{os.environ['PORT']}"

def call(method, path, body=None, token=None, raw=None, ctype=None):
    data, headers = None, {}
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    if raw is not None:
        data, headers["Content-Type"] = raw, ctype
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def check(label, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + label + (f"  ({detail})" if detail else ""))
    if not ok:
        print("\n--- app log ---\n" + open(os.environ["ROOT"] + "/var/verify/app.log").read()[-4000:])
        sys.exit(1)

for _ in range(60):
    try:
        if call("GET", "/api/health")[0] == 200: break
    except Exception: pass
    time.sleep(0.5)
else:
    check("app started", False)

s, b = call("GET", "/api/ready");            check("GET /api/ready", s == 200, b.decode())
s, b = call("GET", "/");                     check("GET / serves the frontend", s == 200 and b"Backtest Lab" in b)
s, _ = call("GET", "/api/symbols");          check("protected route without login -> 401", s == 401)
s, _ = call("POST", "/api/auth/request-otp", {"mobile": "9000000001"}); check("request OTP", s == 200)
s, _ = call("POST", "/api/auth/verify-otp", {"mobile": "9000000001", "otp": "000000"}); check("wrong code rejected", s == 400)
s, b = call("POST", "/api/auth/verify-otp", {"mobile": "9000000001", "otp": os.environ["CODE"]})
check("admin login", s == 200, b.decode()[:120])
tok = json.loads(b)["token"]

rng = np.random.default_rng(1)
n = 600
close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, n)))
df = pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=n).strftime("%Y-%m-%d"), "open": close, "high": close * 1.005,
                   "low": close * 0.995, "close": close})
boundary = uuid.uuid4().hex
form = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"symbol\"\r\n\r\nSMOKE\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"mode\"\r\n\r\nreplace\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"p.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() \
       + df.to_csv(index=False).encode() + f"\r\n--{boundary}--\r\n".encode()
s, b = call("POST", "/api/admin/datasets", raw=form, ctype=f"multipart/form-data; boundary={boundary}", token=tok)
check("admin CSV upload (600 rows)", s == 200, b.decode()[:120])

s, b = call("GET", "/api/ui-config", token=tok); check("ui-config", s == 200)
templates = json.loads(b)["rule_templates"]
for t in templates:
    s, b = call("POST", "/api/backtest", {"symbol": "SMOKE", "rules": t, "period": "MAX"}, token=tok)
    check(f"backtest rule template: {t['name']}", s == 200, b.decode()[:120] if s != 200 else "")
s, b = call("GET", "/api/strategies", token=tok)
for st in json.loads(b)["strategies"]:
    s, b = call("POST", "/api/backtest", {"symbol": "SMOKE", "strategy_id": st["id"], "period": "1Y", "charges_enabled": True, "fee_pct": 0.1}, token=tok)
    m = json.loads(b)["metrics"] if s == 200 else {}
    check(f"backtest strategy: {st['id']}", s == 200, f"return {m.get('total_return', 0):.2%}, trades {m.get('trades')}" if s == 200 else b.decode()[:120])
s, b = call("GET", "/metrics"); check("GET /metrics has app counters", s == 200 and b"backtests_total" in b and b"logins_total" in b)
s, _ = call("POST", "/api/auth/logout", token=tok); check("logout", s == 200)
print("smoke test passed")
PY
}
step "Boot app + HTTP smoke test (local SQLite)" smoke
[ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null; APP_PID=""

# ---------- 6. Your Aiven Postgres + Valkey from .env ----------
aiven() {
  [ -f .env ] || { echo "no .env"; return 1; }
  (cd backend && ../.venv/bin/python - <<'PY'
from app.config import Settings
from app.db import init_schema, make_engine
from sqlalchemy import text
s = Settings.from_env()
print("database driver:", s.database_url.split("://")[0], "| redis configured:", bool(s.redis_url))
eng = make_engine(s.database_url)
with eng.connect() as c:
    print("postgres:", c.execute(text("select version()")).scalar().split(",")[0])
init_schema(eng)
print("schema created/verified")
if s.redis_url:
    import redis
    print("valkey ping:", redis.Redis.from_url(s.redis_url, socket_timeout=5).ping())
PY
  )
}
if [ "$RUN_AIVEN" = 1 ]; then step "Connect to Aiven Postgres + Valkey (.env)" aiven; else skip "Aiven connection" "--no-aiven"; fi

# ---------- 7. Docker image ----------
docker_build() {
  local port=$((PORT + 1)) ok=1
  docker build -t algo-trading:verify . || return 1
  docker rm -f algo-verify >/dev/null 2>&1
  docker run -d --name algo-verify -p "$port:8123" -e APP_ENV=development -e DATABASE_URL=sqlite:////tmp/v.db \
    -e AUTO_CREATE_SCHEMA=true -e SECRET_KEY=verify-script-secret-key-0123456789 -e ADMIN_MOBILES=9000000001 \
    -e DEFAULT_COUNTRY_CODE=91 -e AUTH_MODE=dev -e OTP_DEV_CODE=739214 algo-trading:verify || return 1
  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$port/api/ready"; then ok=0; break; fi
    sleep 1
  done
  [ $ok = 0 ] && { curl -fsS "http://127.0.0.1:$port/" | grep -q "Backtest Lab" || ok=1; }
  docker logs algo-verify 2>&1 | tail -20
  docker rm -f algo-verify >/dev/null
  return $ok
}
if [ "$RUN_DOCKER" = 0 ]; then skip "Docker image build" "--no-docker"
elif ! command -v docker >/dev/null || ! docker info >/dev/null 2>&1; then skip "Docker image build" "Docker not installed or not running"
else step "Docker image build + run" docker_build; fi

# ---------- Summary ----------
echo; echo "================ SUMMARY ================"
printf '%s\n' "${RESULTS[@]}"
echo "========================================="
echo "Full log: $LOG"
[ "$FAILED" = 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED - send me verify.log"
exit $FAILED
