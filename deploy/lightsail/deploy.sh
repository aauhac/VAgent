#!/usr/bin/env bash
# Lightsail deploy: Postgres → alembic upgrade head → backend.
# Does not print secret values. Does not run destructive downgrades.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/vocalfb/app}"
ENV_FILE="${ENV_FILE:-/etc/vocalfb/vocalfb.env}"
SECRETS_DIR="${SECRETS_DIR:-/etc/vocalfb/secrets}"
RUNTIME_HOST="${RUNTIME_HOST:-/var/lib/vocalfb/runtime}"
POSTGRES_HOST_DIR="${POSTGRES_HOST_DIR:-/var/lib/vocalfb/postgres}"
COMPOSE_FILE="${APP_DIR}/deploy/lightsail/docker-compose.production.yml"
COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")

PASS_ITEMS=()
FAIL_ITEMS=()

note_pass() { PASS_ITEMS+=("$1"); echo "PASS: $1"; }
note_fail() { FAIL_ITEMS+=("$1"); echo "FAIL: $1" >&2; }

require_dir() {
  local p="$1"
  if [[ ! -d "$p" ]]; then
    note_fail "missing directory ${p}"
    return 1
  fi
  note_pass "directory ${p}"
}

require_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    note_fail "missing file ${p}"
    return 1
  fi
  note_pass "file ${p}"
}

env_has_name() {
  local name="$1"
  grep -E "^${name}=" "${ENV_FILE}" >/dev/null 2>&1
}

env_nonempty() {
  local name="$1"
  # Value is never printed.
  local line
  line="$(grep -E "^${name}=" "${ENV_FILE}" | tail -n 1 || true)"
  local val="${line#*=}"
  val="${val%$'\r'}"
  [[ -n "$val" ]]
}

truthy_env() {
  local name="$1"
  local line val
  line="$(grep -E "^${name}=" "${ENV_FILE}" | tail -n 1 || true)"
  val="$(echo "${line#*=}" | tr '[:upper:]' '[:lower:]' | tr -d '\r')"
  [[ "$val" == "1" || "$val" == "true" || "$val" == "yes" || "$val" == "on" ]]
}

wait_http() {
  local url="$1"
  local attempts="${2:-30}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS "$url" >/dev/null 2>&1; then
        return 0
      fi
    elif command -v wget >/dev/null 2>&1; then
      if wget -q -O /dev/null "$url"; then
        return 0
      fi
    elif command -v python3 >/dev/null 2>&1; then
      if python3 -c "import urllib.request,sys; urllib.request.urlopen(sys.argv[1], timeout=4)" "$url" >/dev/null 2>&1; then
        return 0
      fi
    else
      echo "FAIL: no curl/wget/python3 to probe HTTP" >&2
      return 1
    fi
    sleep 2
  done
  return 1
}

echo "=== VocalFB Lightsail deploy ==="

require_dir "${APP_DIR}"
require_dir "${RUNTIME_HOST}"
require_dir "${POSTGRES_HOST_DIR}"
require_dir "${SECRETS_DIR}"
require_file "${ENV_FILE}"
require_file "${COMPOSE_FILE}"
require_file "${APP_DIR}/alembic.ini"
require_file "${APP_DIR}/deploy/lightsail/Dockerfile.backend"

REQUIRED_NAMES=(
  VAGENT_ENV
  DATABASE_URL
  RUNTIME_DIR
  PUBLIC_BACKEND_BASE_URL
  PAYMENTS_ENABLED
  TOSS_LOGIN_ENABLED
  TOSS_API_BASE_URL
  TOSS_MTLS_CERT_PATH
  TOSS_MTLS_KEY_PATH
  IAP_SONG_DETAIL_SKU
  IAP_DIAGNOSTIC_FULL_SKU
  IAP_DIAGNOSTIC_UPGRADE_SKU
  VAGENT_SESSION_SECRET
  CORS_ORIGINS
  TOSS_DISCONNECT_BASIC_USER
  TOSS_DISCONNECT_BASIC_PASSWORD
  POSTGRES_USER
  POSTGRES_PASSWORD
  POSTGRES_DB
  ARTIFACT_STORAGE_MODE
  BACKEND_REPLICAS
)

for name in "${REQUIRED_NAMES[@]}"; do
  if env_has_name "$name"; then
    note_pass "env name ${name}"
  else
    note_fail "env name ${name} missing"
  fi
done

if env_nonempty POSTGRES_USER; then
  note_pass "POSTGRES_USER set"
else
  note_fail "POSTGRES_USER empty"
fi
if env_nonempty POSTGRES_DB; then
  note_pass "POSTGRES_DB set"
else
  note_fail "POSTGRES_DB empty"
fi
if env_nonempty DATABASE_URL; then
  note_pass "DATABASE_URL set"
else
  note_fail "DATABASE_URL empty"
fi
if env_nonempty POSTGRES_PASSWORD; then
  note_pass "POSTGRES_PASSWORD set"
else
  note_fail "POSTGRES_PASSWORD empty"
fi
if env_nonempty VAGENT_SESSION_SECRET; then
  note_pass "VAGENT_SESSION_SECRET set"
else
  # Allowed only when payments/login are off; still warn as fail if login/payments on.
  if truthy_env PAYMENTS_ENABLED || truthy_env TOSS_LOGIN_ENABLED; then
    note_fail "VAGENT_SESSION_SECRET empty while login/payments enabled"
  else
    note_pass "VAGENT_SESSION_SECRET optional while login/payments off"
  fi
fi

if truthy_env PAYMENTS_ENABLED || truthy_env TOSS_LOGIN_ENABLED; then
  cert_line="$(grep -E '^TOSS_MTLS_CERT_PATH=' "${ENV_FILE}" | tail -n 1 || true)"
  key_line="$(grep -E '^TOSS_MTLS_KEY_PATH=' "${ENV_FILE}" | tail -n 1 || true)"
  cert_path="${cert_line#*=}"
  key_path="${key_line#*=}"
  cert_path="${cert_path%$'\r'}"
  key_path="${key_path%$'\r'}"
  if [[ -n "$cert_path" && -f "$cert_path" ]]; then
    note_pass "mTLS cert present"
  else
    note_fail "mTLS cert missing"
  fi
  if [[ -n "$key_path" && -f "$key_path" ]]; then
    note_pass "mTLS key present"
  else
    note_fail "mTLS key missing"
  fi
  if env_nonempty TOSS_DISCONNECT_BASIC_USER && env_nonempty TOSS_DISCONNECT_BASIC_PASSWORD; then
    note_pass "disconnect Basic Auth names set"
  else
    note_fail "disconnect Basic Auth incomplete"
  fi
else
  note_pass "Toss mTLS not required (login/payments off)"
fi

if ((${#FAIL_ITEMS[@]} > 0)); then
  echo
  echo "DEPLOY SUMMARY: FAIL (preflight)"
  printf '  failed: %s\n' "${FAIL_ITEMS[@]}"
  exit 1
fi

# Runtime dir must be writable by container uid 1000.
if chown -R 1000:1000 "${RUNTIME_HOST}"; then
  note_pass "runtime ownership uid 1000"
else
  note_fail "runtime chown"
  echo "DEPLOY SUMMARY: FAIL"
  exit 1
fi
chmod 750 "${SECRETS_DIR}" || true

cd "${APP_DIR}"

echo "=== docker compose pull ==="
"${COMPOSE[@]}" pull postgres || true

echo "=== docker compose build backend ==="
"${COMPOSE[@]}" build backend

echo "=== start postgres ==="
"${COMPOSE[@]}" up -d postgres

echo "=== wait postgres healthy ==="
healthy=0
for _ in $(seq 1 40); do
  status="$("${COMPOSE[@]}" ps --format json postgres 2>/dev/null | tr -d '\r' || true)"
  if echo "$status" | grep -qi healthy; then
    healthy=1
    break
  fi
  # Fallback: pg_isready inside the container once it exists
  if "${COMPOSE[@]}" exec -T postgres pg_isready >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 3
done
if [[ "$healthy" -ne 1 ]]; then
  note_fail "postgres health"
  echo "DEPLOY SUMMARY: FAIL"
  exit 1
fi
note_pass "postgres health"

echo "=== alembic upgrade head ==="
# Temporary backend container shares env + postgres network, does not publish the API yet.
if ! "${COMPOSE[@]}" run --rm --no-deps --entrypoint alembic backend upgrade head; then
  note_fail "alembic upgrade head"
  echo "DEPLOY SUMMARY: FAIL (migration). Backend was not started."
  exit 1
fi
note_pass "alembic upgrade head"

echo "=== start backend ==="
"${COMPOSE[@]}" up -d backend

echo "=== wait /health ==="
if wait_http "http://127.0.0.1:8000/health" 40; then
  note_pass "backend /health"
else
  note_fail "backend /health"
  echo "DEPLOY SUMMARY: FAIL"
  exit 1
fi

echo "=== verify /ready ==="
ready_body="$(curl -fsS http://127.0.0.1:8000/ready || true)"
if echo "$ready_body" | grep -q '"ready": true\|"ready":true'; then
  note_pass "backend /ready"
else
  note_fail "backend /ready"
  echo "DEPLOY SUMMARY: FAIL"
  echo "ready body omitted (may include operational fields; secrets are not expected)"
  exit 1
fi

echo
echo "DEPLOY SUMMARY: PASS"
printf '  pass: %s\n' "${PASS_ITEMS[@]}"
exit 0
