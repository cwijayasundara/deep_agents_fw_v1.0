#!/usr/bin/env bash
# Phase 0 exit criterion: two tenants, each on its own stamped deployment, fully separated.
#
#   scripts/phase0_exit.sh          # or: make phase0-exit
#
# Stamps tenant-a and tenant-b (distinct ports, volumes, keys and collectors), then for each:
# runs the contract suite against its database, runs one scripted research turn (scripts/smoke.py:
# persisted, traced, no live model), and asserts that its collector file and its database hold
# only its own tenant. Leaves both stamps running; tear down with make unstamp TENANT=<t>.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
# shellcheck source=scripts/tenant_env.sh
. scripts/tenant_env.sh   # env_get, tenant_exports

tenants="tenant-a tenant-b"
fail() { echo "phase0 exit: FAIL: $*" >&2; exit 1; }

for t in $tenants; do
  scripts/stamp_tenant.sh "$t" | grep -E '^(stamp|setup):'
done

ports=$(for t in $tenants; do
  env_get AGENTKIT_PG_PORT "deploy/tenants/$t.env"
  env_get AGENTKIT_OTLP_PORT "deploy/tenants/$t.env"
done)
[ "$(echo "$ports" | sort -u | wc -l | tr -d ' ')" -eq 4 ] || fail "tenants share a port: $ports"
key_a=$(env_get LANGGRAPH_AES_KEY deploy/tenants/tenant-a.env)
[ "$key_a" != "$(env_get LANGGRAPH_AES_KEY deploy/tenants/tenant-b.env)" ] ||
  fail "tenants share an AES key"

for t in $tenants; do
  echo "== $t: contract suite"
  out=$( (tenant_exports "$t" && AGENTKIT_TEST_DATABASE_URL=$DATABASE_URL \
    uv run --no-sync pytest contracts -q -p no:cacheprovider) 2>&1) ||
    { echo "$out"; fail "$t: contract suite failed"; }
  summary=$(echo "$out" | tail -n 1)
  echo "$summary"
  case $summary in *skipped*) fail "$t: contracts skipped (the pg contracts must run)" ;; esac

  echo "== $t: scripted research run"
  out=$( (tenant_exports "$t" && uv run --no-sync python scripts/smoke.py --persist --trace \
    --tenant "$t" --user exit-check --say "phase0 exit check for $t") 2>&1) ||
    { echo "$out"; fail "$t: scripted run failed"; }
  echo "$out"
  trace=$(echo "$out" | sed -n 's/^ *trace: //p')
  [[ $trace =~ ^[0-9a-f]{32}$ ]] || fail "$t: the run printed no trace id (is tracing on?)"
  eval "trace_${t//-/_}=$trace"
done

for t in $tenants; do
  var="trace_${t//-/_}"
  file="deploy/otel-out/$t/spans.jsonl"
  for _ in $(seq 1 30); do   # the collector batches for 1 s before it writes
    grep -qs "${!var}" "$file" && break
    sleep 0.5
  done
  grep -qs "${!var}" "$file" || fail "$t: trace ${!var} never reached $file"
  uv run --no-sync python - "$t" "$file" "$tenants" <<'PY' || fail "$t: collector file check"
import json
import sys

tenant, path, everyone = sys.argv[1], sys.argv[2], sys.argv[3].split()
text = open(path).read()
seen: dict[str, int] = {}
for line in filter(None, text.splitlines()):
    for rs in json.loads(line).get("resourceSpans", []):
        attrs = {a["key"]: a["value"].get("stringValue") for a in rs["resource"]["attributes"]}
        owner = attrs.get("agentkit.tenant") or "<none>"
        seen[owner] = seen.get(owner, 0) + sum(len(s.get("spans", [])) for s in rs["scopeSpans"])
others = [o for o in everyone if o != tenant and o in text]
print(f"{tenant}: collector spans by tenant {seen}; other tenants named in file: {others}")
sys.exit(0 if set(seen) == {tenant} and not others else 1)
PY
  rows=$(docker compose -p "agentkit-$t" --env-file "deploy/tenants/$t.env" -f deploy/compose.yaml \
    exec -T postgres psql -U agentkit -d agentkit -tAc \
    "select coalesce(string_agg(distinct metadata->>'tenant', ','), '') from checkpoints
     union all select coalesce(string_agg(distinct tenant, ','), '') from agentkit_usage")
  echo "$t: database tenants (checkpoints, agentkit_usage): $(echo "$rows" | paste -sd ' ' -)"
  [ "$(echo "$rows" | sort -u)" = "$t" ] || fail "$t: database holds rows of another tenant"
done

echo "phase0 exit: tenant-a OK, tenant-b OK, traces separated"
