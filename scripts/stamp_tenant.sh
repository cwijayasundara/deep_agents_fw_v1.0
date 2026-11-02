#!/usr/bin/env bash
# Stamp one isolated deployment for a tenant: compose project agentkit-<tenant> (own Postgres
# volume, own collector, own ports), then run its persistence setup.
#
#   scripts/stamp_tenant.sh <tenant>          # or: make stamp TENANT=<tenant>
#
# The first run writes deploy/tenants/<tenant>.env (git-ignored) with a fresh 32-character AES
# key, a fresh database password and two free host ports. Later runs reuse that file unchanged,
# so stamping twice changes nothing. STAMP_PG_PORT / STAMP_OTLP_PORT pick the ports of a new file.
set -euo pipefail

usage() { echo "usage: $0 <tenant>   (tenant: lowercase letters, digits, _ or -)" >&2; exit 2; }
[ $# -eq 1 ] || usage
tenant=$1
[[ $tenant =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]] || usage
[ "$tenant" != example ] || { echo "stamp: 'example' is the template, not a tenant" >&2; exit 2; }

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
env_file=deploy/tenants/$tenant.env
# Ports never handed out: other local stacks on this machine use them.
reserved=" 15432 16379 "

# shellcheck source=scripts/tenant_env.sh
. scripts/tenant_env.sh   # env_get, tenant_exports

port_taken() {
  local p=$1
  case $reserved in *" $p "*) return 0 ;; esac
  # Listening on this machine?
  if (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null; then return 0; fi
  # Already given to another tenant (stamped or not running right now)?
  grep -qsE "^AGENTKIT_(PG|OTLP)_PORT=$p\$" deploy/tenants/*.env && return 0
  return 1
}

free_port() { # free_port START [EXCLUDE]: first free port at or above START
  local p=$1
  while [ "$p" -lt 65535 ]; do
    if [ "$p" != "${2:-}" ] && ! port_taken "$p"; then echo "$p"; return 0; fi
    p=$((p + 1))
  done
  echo "stamp: no free port above $1" >&2
  return 1
}

if [ -f "$env_file" ]; then
  echo "stamp: using $env_file (AES key unchanged)"
else
  pg_port=${STAMP_PG_PORT:-$(free_port 55500)}
  otlp_port=${STAMP_OTLP_PORT:-$(free_port 55500 "$pg_port")}
  [ "$pg_port" != "$otlp_port" ] || { echo "stamp: Postgres and OTLP ports must differ" >&2; exit 2; }
  aes_key=$(openssl rand -base64 24 | tr -d '\n')   # 24 random bytes -> 32 characters
  password=$(openssl rand -hex 16)
  [ ${#aes_key} -eq 32 ] || { echo "stamp: AES key generation failed" >&2; exit 1; }
  (
    umask 077
    cat >"$env_file" <<EOF
# Tenant $tenant, written by scripts/stamp_tenant.sh. Never commit (holds the AES key).
AGENTKIT_TENANT=$tenant
AGENTKIT_PG_PORT=$pg_port
AGENTKIT_OTLP_PORT=$otlp_port
AGENTKIT_PG_PASSWORD=$password
DATABASE_URL=postgresql://agentkit:$password@127.0.0.1:$pg_port/agentkit
LANGGRAPH_AES_KEY=$aes_key
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:$otlp_port
# Optional: set all three to forward this tenant's spans to its Langfuse project, then re-stamp.
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
EOF
  )
  echo "stamp: wrote $env_file (new AES key, Postgres 127.0.0.1:$pg_port, OTLP 127.0.0.1:$otlp_port)"
fi

[ "$(env_get AGENTKIT_TENANT "$env_file")" = "$tenant" ] ||
  { echo "stamp: $env_file is not for tenant $tenant" >&2; exit 2; }

# Values from the tenant file win over anything exported in this shell (e.g. the dev stack's
# AGENTKIT_PG_PORT), because compose prefers the shell over --env-file.
export AGENTKIT_TENANT=$tenant
AGENTKIT_PG_PORT=$(env_get AGENTKIT_PG_PORT "$env_file")
AGENTKIT_OTLP_PORT=$(env_get AGENTKIT_OTLP_PORT "$env_file")
AGENTKIT_PG_PASSWORD=$(env_get AGENTKIT_PG_PASSWORD "$env_file")
export AGENTKIT_PG_PORT AGENTKIT_OTLP_PORT AGENTKIT_PG_PASSWORD
AGENTKIT_UID=$(id -u)
AGENTKIT_GID=$(id -g)
export AGENTKIT_UID AGENTKIT_GID

lf_public=$(env_get LANGFUSE_PUBLIC_KEY "$env_file")
lf_secret=$(env_get LANGFUSE_SECRET_KEY "$env_file")
lf_host=$(env_get LANGFUSE_HOST "$env_file")
if [ -n "$lf_public" ] && [ -n "$lf_secret" ]; then
  export AGENTKIT_OTEL_EXPORTERS="[file, otlp_http/langfuse]"
  export LANGFUSE_OTLP_ENDPOINT="${lf_host:-https://cloud.langfuse.com}/api/public/otel"
  LANGFUSE_OTLP_AUTH=$(printf '%s:%s' "$lf_public" "$lf_secret" | base64 | tr -d '\n')
  export LANGFUSE_OTLP_AUTH
  forward="JSONL file and Langfuse at $LANGFUSE_OTLP_ENDPOINT"
else
  export AGENTKIT_OTEL_EXPORTERS="[file]"
  unset LANGFUSE_OTLP_ENDPOINT LANGFUSE_OTLP_AUTH
  forward="JSONL file only, no Langfuse keys"
fi

mkdir -p "deploy/otel-out/$tenant"
docker compose -p "agentkit-$tenant" --env-file "$env_file" -f deploy/compose.yaml \
  up -d --wait --quiet-pull

tenant_exports "$tenant"
uv run --no-sync python scripts/tenant_setup.py

echo "stamp: tenant $tenant ready: project agentkit-$tenant," \
  "Postgres 127.0.0.1:$AGENTKIT_PG_PORT, OTLP 127.0.0.1:$AGENTKIT_OTLP_PORT," \
  "traces -> deploy/otel-out/$tenant/spans.jsonl ($forward)"
