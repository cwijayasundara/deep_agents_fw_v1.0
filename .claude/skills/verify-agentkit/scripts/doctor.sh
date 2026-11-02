#!/usr/bin/env bash
# Is this checkout and (optionally) this verification tenant worth driving? Read-only.
#
#   .claude/skills/verify-agentkit/scripts/doctor.sh              # host checks only
#   .claude/skills/verify-agentkit/scripts/doctor.sh <RUN_ID>     # + tenant verify-<RUN_ID> checks
#
# Prints one PASS/WARN/FAIL line per check (key NAMES only, never values) and exits 1 on any FAIL.
# With a RUN_ID it also appends the output to evidence/verify/<RUN_ID>/doctor.txt.
# The Decisions probe is one tiny real POST /v1/decisions call (a fraction of a cent).
set -euo pipefail
. "$(dirname "$0")/common.sh"
cd "$REPO"

pass() { echo "PASS $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; }

checks() {
  echo "doctor: $(date -u +%Y-%m-%dT%H:%M:%SZ) repo=$REPO branch=$(git branch --show-current) head=$(git rev-parse --short HEAD)"

  command -v uv >/dev/null && pass "uv $(uv --version | cut -d' ' -f2)" || fail "uv not on PATH"
  command -v jq >/dev/null && pass "jq present" || fail "jq not on PATH"

  # Keys: names only. Settings reads the repo .env and prefers it over the shell.
  if [ -f .env ]; then
    local set_keys
    set_keys=$(grep -oE '^[A-Z_]+=.' .env | cut -d= -f1 | tr '\n' ' ')
    for k in FIREWORKS_API_KEY OPENAI_API_KEY; do
      case " $set_keys " in *" $k "*) pass "key $k set in .env" ;; *) fail "key $k missing from .env" ;; esac
    done
    case " $set_keys " in
      *" TAVILY_API_KEY "*) pass "key TAVILY_API_KEY set (optional; web search still defaults to DuckDuckGo)" ;;
      *) warn "TAVILY_API_KEY not set (optional; DuckDuckGo is the default backend)" ;;
    esac
    if grep -qE '^AGENTKIT_TENANT=' .env; then
      fail ".env sets AGENTKIT_TENANT: it would override every stamp (comment it out)"
    else
      pass ".env does not set AGENTKIT_TENANT"
    fi
    for k in DATABASE_URL LANGGRAPH_AES_KEY; do
      grep -qE "^$k=" .env && warn ".env sets $k (tenant_env.sh exports win, but keep it commented)"
    done
  else
    fail "no .env at repo root (cp .env.example .env and fill keys)"
  fi

  # Offline: the shipped agent and the fireworks-glm entry resolve.
  if uv run --no-sync agentkit validate apps/research_agent/agent.yaml >/dev/null 2>&1; then
    pass "agentkit validate apps/research_agent/agent.yaml (0 errors)"
  else
    fail "agentkit validate apps/research_agent/agent.yaml reports errors (or the venv is missing: make sync)"
  fi

  # Network probes through the product's own Settings and DecisionsClient; values never printed.
  local probe
  probe=$(uv run --no-sync python - <<'PY' 2>&1 || true
import asyncio

import httpx
from agentkit_core import Provider, Settings
from agentkit_middleware import DecisionsClient, DecisionsError


async def main() -> None:
    s = Settings()
    try:
        client = DecisionsClient(s.require_key(Provider.OPENAI), attempts=1)
        resp = await client.decide(
            "ping",
            [{"type": "predicate", "name": "probe", "instructions": "Is the input the word ping?"}],
        )
        print(f"PASS decisions API reachable (gpt-6-luna, {len(resp.get('answers', []))} answer)")
    except DecisionsError as e:
        print(f"FAIL decisions API refused the probe ({e})")  # "HTTP <code>" only
    except Exception as e:  # noqa: BLE001
        print(f"FAIL decisions API unreachable ({type(e).__name__})")
    try:
        key = s.require_key(Provider.FIREWORKS)
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(
                "https://api.fireworks.ai/inference/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        verdict = "PASS" if r.status_code == 200 else "FAIL" if r.status_code in (401, 403) else "WARN"
        print(f"{verdict} fireworks API answered HTTP {r.status_code} to a model listing")
    except Exception as e:  # noqa: BLE001
        print(f"WARN fireworks API probe failed ({type(e).__name__})")


asyncio.run(main())
PY
)
  while IFS= read -r line; do
    case $line in
      PASS*) pass "${line#PASS }" ;;
      FAIL*) fail "${line#FAIL }" ;;
      WARN*) warn "${line#WARN }" ;;
      *) [ -n "$line" ] && echo "     $line" ;;
    esac
  done <<<"$probe"

  if docker info >/dev/null 2>&1; then
    pass "docker daemon up ($(docker info --format '{{.ServerVersion}}'))"
  else
    fail "docker daemon not reachable (start Docker Desktop)"
  fi

  local stale
  stale=$(cd deploy/tenants && ls verify-*.env 2>/dev/null | grep -vx "${TENANT:-none}.env" | tr '\n' ' ' || true)
  [ -z "$stale" ] || warn "verify tenant env files present: $stale(leftover runs? run cleanup.sh <RUN_ID> for each)"

  [ -n "${RUN_ID:-}" ] || return 0
  echo "tenant: $TENANT (compose project $PROJECT)"
  if [ ! -f "$ENV_FILE" ]; then
    warn "tenant $TENANT not stamped yet (no $ENV_FILE): run stamp.sh $RUN_ID"
    return 0
  fi
  pass "env file deploy/tenants/$TENANT.env (mode $(stat -f %Lp "$ENV_FILE" 2>/dev/null || stat -c %a "$ENV_FILE"))"
  local pg_port otlp_port
  pg_port=$(env_value AGENTKIT_PG_PORT)
  otlp_port=$(env_value AGENTKIT_OTLP_PORT)
  local states
  states=$(compose ps --format '{{.Service}}={{.State}}/{{.Health}}' 2>/dev/null | tr '\n' ' ' || true)
  case " $states " in *" postgres=running/healthy "*) pass "postgres running/healthy" ;; *) fail "postgres not healthy: $states" ;; esac
  case " $states " in *" otel-collector=running/"*) pass "otel-collector running" ;; *) fail "otel-collector not running: $states" ;; esac
  local got
  got=$(compose port postgres 5432 2>/dev/null || true)
  [ "$got" = "127.0.0.1:$pg_port" ] && pass "port $pg_port owned by $PROJECT postgres" || fail "postgres port: want 127.0.0.1:$pg_port got '$got'"
  got=$(compose port otel-collector 4318 2>/dev/null || true)
  [ "$got" = "127.0.0.1:$otlp_port" ] && pass "port $otlp_port owned by $PROJECT otel-collector" || fail "collector port: want 127.0.0.1:$otlp_port got '$got'"
  if (exec 3<>"/dev/tcp/127.0.0.1/$otlp_port") 2>/dev/null; then pass "collector accepts TCP on $otlp_port"; else fail "collector not accepting on $otlp_port"; fi
  got=$(psql_tenant -tAc "select to_regclass('agentkit_usage') is not null and to_regclass('checkpoint_migrations') is not null" 2>/dev/null || true)
  [ "$got" = "t" ] && pass "tenant DB set up (agentkit_usage, checkpoint migrations)" || fail "tenant DB not set up (got '$got'): re-run make stamp TENANT=$TENANT"
}

[ $# -eq 0 ] || set_run "$1"
out=$(checks 2>&1) || true
printf '%s\n' "$out"
if [ -n "${RUN_ID:-}" ]; then
  mkdir -p "$EV"
  printf '%s\n' "$out" >>"$EV/doctor.txt"
fi
fails=$(printf '%s\n' "$out" | grep -c '^FAIL' || true)
[ "$fails" -eq 0 ] || { echo "doctor: $fails check(s) failed" >&2; exit 1; }
echo "doctor: OK"
