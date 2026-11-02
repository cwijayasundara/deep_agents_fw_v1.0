# Shared helpers for the verify-agentkit scripts. Sourced, never run directly.
# One verification run = one RUN_ID = tenant verify-<RUN_ID> = evidence/verify/<RUN_ID>/.
# Works on macOS /bin/bash 3.2 (no associative arrays, no mapfile).

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
export UV_CONSTRAINT=constraints.txt
# Live runs use this registry entry only (project ruling); never fan out across providers.
MODEL=fireworks-glm

die() { echo "verify: $*" >&2; exit 1; }

new_run_id() { date +%Y%m%d-%H%M%S; }

# set_run RUN_ID: defines RUN_ID, TENANT, PROJECT, EV (evidence dir), ENV_FILE, OTEL_OUT.
set_run() {
  [ -n "${1:-}" ] || die "missing RUN_ID (e.g. $(new_run_id))"
  [[ $1 =~ ^[a-z0-9][a-z0-9-]{0,40}$ ]] || die "RUN_ID must be lowercase letters, digits or -, max 41 chars: $1"
  RUN_ID=$1
  TENANT=verify-$RUN_ID # PlatformContext Label: ^[a-z0-9][a-z0-9_-]{0,62}$
  PROJECT=agentkit-$TENANT
  EV=$REPO/evidence/verify/$RUN_ID
  ENV_FILE=$REPO/deploy/tenants/$TENANT.env
  OTEL_OUT=$REPO/deploy/otel-out/$TENANT
}

env_value() { # env_value KEY: value from the tenant env file (never printed by callers for secrets)
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
}

compose() {
  docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f "$REPO/deploy/compose.yaml" "$@"
}

psql_tenant() { # psql_tenant ARGS...: psql inside the tenant's own Postgres container
  compose exec -T postgres psql -U agentkit -d agentkit -v ON_ERROR_STOP=1 "$@"
}

stack_up() { [ -f "$ENV_FILE" ] && [ -n "$(compose ps -q postgres 2>/dev/null)" ]; }
