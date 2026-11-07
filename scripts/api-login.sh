#!/usr/bin/env bash
# Sign in to a running API and print a session token for curl or Swagger's "Authorize" button.
#
#   ./scripts/api-login.sh                    # first ADMIN_MOBILES number and OTP_DEV_CODE from .env
#   ./scripts/api-login.sh 9876543210 482915  # any number and code
#   BASE=https://your-domain ./scripts/api-login.sh 9876543210 <code>
#
#   TOKEN=$(./scripts/api-login.sh --quiet)
#   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8123/api/symbols
set -euo pipefail
cd "$(dirname "$0")/.."
QUIET=0
[ "${1:-}" = "--quiet" ] && { QUIET=1; shift; }
BASE="${BASE:-http://localhost:8123}"
env_value() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' || true; }
MOBILE="${1:-$(env_value ADMIN_MOBILES | cut -d, -f1)}"
CODE="${2:-$(env_value OTP_DEV_CODE)}"
[ -n "$MOBILE" ] && [ -n "$CODE" ] || { echo "Usage: $0 [mobile] [code]" >&2; exit 2; }

json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1', d))"; }
r=$(curl -sS -X POST "$BASE/api/auth/request-otp" -H 'Content-Type: application/json' -d "{\"mobile\":\"$MOBILE\"}")
case "$r" in *'"sent":true'*) ;; *) echo "request-otp failed: $r" >&2; exit 1 ;; esac
r=$(curl -sS -X POST "$BASE/api/auth/verify-otp" -H 'Content-Type: application/json' -d "{\"mobile\":\"$MOBILE\",\"otp\":\"$CODE\"}")
TOKEN=$(echo "$r" | json token)
case "$TOKEN" in *"{"*|"") echo "verify-otp failed: $r" >&2; exit 1 ;; esac

if [ "$QUIET" = 1 ]; then echo "$TOKEN"; exit 0; fi
cat <<MSG
Signed in as $(echo "$r" | json mobile) ($(echo "$r" | json role)). Token expires $(echo "$r" | json expires_at).

  export TOKEN=$TOKEN

Try:
  curl -s -H "Authorization: Bearer \$TOKEN" $BASE/api/symbols
  curl -s -H "Authorization: Bearer \$TOKEN" -H 'Content-Type: application/json' \\
       -d '{"symbol":"<SYMBOL>","strategy_id":"sma_cross","period":"1Y"}' $BASE/api/backtest

Swagger: open $BASE/docs, click Authorize, paste the token.
MSG
