#!/usr/bin/env bash
# Runs ON the server (CircleCI calls it over SSH). Usage: deploy.sh <image>
# Switches the app to <image>, waits until /api/ready answers through Caddy, and rolls back if it doesn't.
set -euo pipefail
cd "$(dirname "$0")"

NEW_IMAGE="$1"
COMPOSE="docker compose -f docker-compose.prod.yml"
test -f .env || { echo "Missing /opt/algo-trading/.env (copy deploy/.env.example and fill it in)"; exit 1; }
DOMAIN="$(grep -E '^DOMAIN=' .env | cut -d= -f2-)"
OLD_IMAGE="$(grep -E '^APP_IMAGE=' .env | cut -d= -f2- || true)"

set_image() {
  if grep -qE '^APP_IMAGE=' .env; then sed -i "s#^APP_IMAGE=.*#APP_IMAGE=$1#" .env; else echo "APP_IMAGE=$1" >> .env; fi
}

healthy() {
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 5 "https://${DOMAIN}/api/ready" >/dev/null; then return 0; fi
    sleep 4
  done
  return 1
}

echo "Deploying ${NEW_IMAGE} (previous: ${OLD_IMAGE:-none})"
set_image "$NEW_IMAGE"
$COMPOSE pull
$COMPOSE up -d --remove-orphans
# Reload Prometheus rules/targets in case they changed.
$COMPOSE exec -T prometheus wget -qO- --post-data='' http://localhost:9090/-/reload >/dev/null 2>&1 || true

if healthy; then
  echo "Deploy OK: https://${DOMAIN}"
  docker image prune -f >/dev/null
  exit 0
fi

echo "Readiness check failed. Recent app logs:"
$COMPOSE logs --tail=80 app || true
if [ -n "${OLD_IMAGE}" ] && [ "${OLD_IMAGE}" != "${NEW_IMAGE}" ]; then
  echo "Rolling back to ${OLD_IMAGE}"
  set_image "$OLD_IMAGE"
  $COMPOSE up -d app
fi
exit 1
