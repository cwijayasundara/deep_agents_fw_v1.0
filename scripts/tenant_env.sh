#!/usr/bin/env bash
# Run a command with one stamped tenant's runtime settings (from deploy/tenants/<tenant>.env).
#
#   scripts/tenant_env.sh tenant-a uv run research "question" --tenant tenant-a --persist
#
# Exports AGENTKIT_TENANT, DATABASE_URL, LANGGRAPH_AES_KEY and OTEL_EXPORTER_OTLP_ENDPOINT from the
# tenant file, over anything set in this shell. Sourced (by the other scripts) it only defines
# env_get and tenant_exports.

env_get() { # env_get KEY FILE: the value of the last KEY= line in FILE
  grep -E "^$1=" "$2" | tail -n 1 | cut -d= -f2- || true
}

tenant_exports() { # tenant_exports TENANT: export its runtime settings; fails if not stamped
  local file
  file="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy/tenants/$1.env"
  if [ ! -f "$file" ]; then
    echo "tenant $1 is not stamped (no deploy/tenants/$1.env): run make stamp TENANT=$1" >&2
    return 2
  fi
  # Settings prefers .env over the process env, so a tenant there would override every stamp.
  if grep -qsE '^AGENTKIT_TENANT=' "$(dirname "$file")/../../.env"; then
    echo "remove AGENTKIT_TENANT from .env: the tenant comes from $file" >&2
    return 2
  fi
  local var value
  for var in AGENTKIT_TENANT DATABASE_URL LANGGRAPH_AES_KEY OTEL_EXPORTER_OTLP_ENDPOINT; do
    value=$(env_get "$var" "$file")
    export "$var=$value"
  done
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -euo pipefail
  [ $# -ge 2 ] || { echo "usage: $0 <tenant> <command> [args...]" >&2; exit 2; }
  tenant_exports "$1"
  shift
  exec "$@"
fi
