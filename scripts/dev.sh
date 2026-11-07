#!/usr/bin/env bash
# Start the backend and the frontend for local testing. Ctrl+C stops both.
#
#   ./scripts/dev.sh
#
#   Browser (hot reload):   http://localhost:5173
#   API + Swagger:          http://localhost:8123/docs
#
# If a port is already taken, whatever is listening on it is stopped first.
# Uses the settings in .env (database, Redis, admin numbers, access code). Run ./scripts/verify.sh once first
# to create .venv and install the frontend packages.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
API_PORT="${API_PORT:-8123}"
WEB_PORT="${WEB_PORT:-5173}"

env_value() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' || true; }

[ -f .env ] || { echo "No .env found. Copy .env.example to .env and fill it in."; exit 1; }
mkdir -p var
[ -x .venv/bin/uvicorn ] || { echo "Python packages missing. Run ./scripts/verify.sh once (or: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt)."; exit 1; }
if [ ! -d frontend/node_modules ]; then echo "Installing frontend packages..."; (cd frontend && npm ci --no-audit --no-fund); fi
if [ "$(env_value APP_ENV)" = "production" ]; then
  echo "Note: APP_ENV=production in .env hides Swagger (/docs). Use APP_ENV=development for local testing."
fi

# Free a port: stop whatever listens on it (ask politely, then force after 5 s) and say what was stopped.
free_port() {
  local port="$1" pids
  command -v lsof >/dev/null || return 0
  pids=$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true)
  [ -z "$pids" ] && return 0
  for p in $pids; do
    echo "Port $port is in use by $(ps -p "$p" -o comm= 2>/dev/null | xargs basename 2>/dev/null || echo '?') (PID $p) - stopping it."
    kill "$p" 2>/dev/null || true
  done
  for _ in $(seq 1 10); do
    lsof -nP -t -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || return 0
    sleep 0.5
  done
  for p in $(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null); do
    echo "PID $p did not stop - forcing it."
    kill -9 "$p" 2>/dev/null || true
  done
  sleep 0.5
  if lsof -nP -t -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Could not free port $port (maybe owned by another user). Try: API_PORT=8124 WEB_PORT=5174 ./scripts/dev.sh"
    exit 1
  fi
}
free_port "$API_PORT"
free_port "$WEB_PORT"

pids=()
cleanup() {
  echo; echo "Stopping..."
  for p in ${pids[@]+"${pids[@]}"}; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd backend && exec ../.venv/bin/uvicorn app.main:create_app --factory --reload --port "$API_PORT" --reload-dir app --reload-dir ../config) &
pids+=($!)
(cd frontend && API_PORT="$API_PORT" exec npm run dev -- --port "$WEB_PORT" --strictPort) &
pids+=($!)

printf "Waiting for the API"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then break; fi
  printf "."; sleep 1
done
echo

ADMIN="$(env_value ADMIN_MOBILES | cut -d, -f1)"
CODE="$(env_value OTP_DEV_CODE)"
cat <<MSG

  Strategic Trader is running
  ----------------------------------------------------------------
  Browser (hot reload)   http://localhost:$WEB_PORT
  API                    http://localhost:$API_PORT/api
  Swagger (try the API)  http://localhost:$API_PORT/docs
  Readiness              http://localhost:$API_PORT/api/ready

  Sign in with           mobile ${ADMIN:-<set ADMIN_MOBILES in .env>} (admin)
                         code   $( [ "$(env_value APP_ENV)" = "production" ] && echo "OTP_DEV_CODE in .env" || echo "${CODE:-<set OTP_DEV_CODE in .env>}")
  Token for curl/Swagger ./scripts/api-login.sh
  Database               $(env_value DATABASE_URL | sed -E 's#://[^@]*@#://***@#; s#\?.*##')

  Ctrl+C stops both.
MSG
wait
