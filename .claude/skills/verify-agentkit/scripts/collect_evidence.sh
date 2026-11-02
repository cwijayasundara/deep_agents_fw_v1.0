#!/usr/bin/env bash
# Copy the run's trace and ledger out of the tenant stack into the evidence dir, then check them.
# Must run BEFORE make unstamp (Ruling P12: `down -v` destroys the DB; cleanup.sh calls this first).
#
#   collect_evidence.sh <RUN_ID>
#
# Writes to evidence/verify/<RUN_ID>/:
#   spans.jsonl            copy of deploy/otel-out/verify-<RUN_ID>/spans.jsonl (after the printed
#                          trace ids land; the collector batches for 1 s)
#   spans-summary.txt      span count per agentkit.tenant, trace ids found, masking flag count
#   agentkit_usage.csv     every agentkit_usage row (header + rows)
#   checkpoints.csv        threads and max step per metadata tenant (identifiers only)
#   compose-ps.txt         the tenant's containers at collection time
#   checks.txt             PASS/FAIL per assertion; exit 1 on any FAIL
#   MANIFEST.txt           file listing
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -eq 1 ] || die "usage: $0 <RUN_ID>"
set_run "$1"
cd "$REPO"
[ -d "$EV" ] || die "no evidence dir $EV"
stack_up || die "tenant $TENANT stack is not up (already unstamped?); nothing to collect"

# Trace ids the CLIs printed (research `trace: <id>`, eval JSON cases[].trace_id).
traces=$( (cat "$EV"/*.stdout 2>/dev/null | sed -n 's/^trace: //p'
  [ -s "$EV/eval_results.json" ] && jq -r '.cases[].trace_id // empty' "$EV/eval_results.json") | sort -u || true)
src=$OTEL_OUT/spans.jsonl
for t in $traces; do
  for _ in $(seq 1 40); do grep -qs "$t" "$src" && break; sleep 0.5; done
done
[ -f "$src" ] && cp "$src" "$EV/spans.jsonl" || : >"$EV/spans.jsonl"

uv run --no-sync python - "$EV/spans.jsonl" "$TENANT" >"$EV/spans-summary.txt" <<'PY'
import json
import sys

path, tenant = sys.argv[1], sys.argv[2]
per_tenant: dict[str, int] = {}
traces: set[str] = set()
masked = 0
for line in filter(None, open(path).read().splitlines()):
    for rs in json.loads(line).get("resourceSpans", []):
        attrs = {a["key"]: a["value"].get("stringValue") for a in rs["resource"]["attributes"]}
        owner = attrs.get("agentkit.tenant") or "<none>"
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                per_tenant[owner] = per_tenant.get(owner, 0) + 1
                traces.add(span.get("traceId", ""))
                if any(a["key"] == "agentkit.payload.masked" for a in span.get("attributes", [])):
                    masked += 1
print(f"spans by agentkit.tenant: {per_tenant}")
print(f"masked spans: {masked}")
for t in sorted(traces):
    print(f"trace: {t}")
PY

psql_tenant -c "\copy (select * from agentkit_usage order by created_at) to stdout with csv header" \
  >"$EV/agentkit_usage.csv"
psql_tenant -c "\copy (select metadata->>'tenant' as tenant, count(distinct thread_id) as threads, max((metadata->>'step')::int) as max_step from checkpoints group by 1) to stdout with csv header" \
  >"$EV/checkpoints.csv"
compose ps >"$EV/compose-ps.txt" 2>&1 || true

only_tenant() { # only_tenant CSV COLUMN: true when every data row's COLUMN equals $TENANT
  awk -F, -v t="$TENANT" -v c="$2" 'NR > 1 && $c != t { bad = 1 } END { exit bad }' "$1"
}
: >"$EV/checks.txt"
check() { # check NAME COMMAND...: PASS/FAIL line from the command's exit status
  local name=$1
  shift
  if "$@"; then echo "PASS $name"; else echo "FAIL $name"; fi >>"$EV/checks.txt"
}
check "spans.jsonl non-empty" test -s "$EV/spans.jsonl"
check "every span carries agentkit.tenant=$TENANT only" \
  grep -qxE "spans by agentkit.tenant: \{'$TENANT': [0-9]+\}" "$EV/spans-summary.txt"
for t in $traces; do
  check "printed trace $t present in spans" grep -qx "trace: $t" "$EV/spans-summary.txt"
done
rows=$(($(wc -l <"$EV/agentkit_usage.csv") - 1))
check "agentkit_usage has rows ($rows)" test "$rows" -ge 1
check "every agentkit_usage row is tenant $TENANT" only_tenant "$EV/agentkit_usage.csv" 2
for f in "$EV"/*.stdout; do
  [ -e "$f" ] || continue
  th=$(sed -n 's/^thread: //p' "$f" | head -n 1)
  if [ -n "$th" ] && grep -q '^usage: ' "$f" && grep -q -- '--persist' "${f%.stdout}.cmd.txt" 2>/dev/null; then
    check "thread $th ($(basename "$f" .stdout)) has a usage row" grep -q ",$th," "$EV/agentkit_usage.csv"
  elif [ -n "$th" ] && [ "$(cat "${f%.stdout}.exit" 2>/dev/null)" = 1 ] && ! grep -q '^usage: ' "$f"; then
    check "refused thread $th ($(basename "$f" .stdout)) wrote no usage row" \
      sh -c '! grep -q ",$1," "$2"' _ "$th" "$EV/agentkit_usage.csv"
  fi
done
check "checkpoints belong to $TENANT only" only_tenant "$EV/checkpoints.csv" 1

(cd "$EV" && ls -la) >"$EV/MANIFEST.txt"
cat "$EV/spans-summary.txt" | head -n 2
cat "$EV/checks.txt"
! grep -q '^FAIL' "$EV/checks.txt" || die "evidence checks failed (see $EV/checks.txt)"
echo "verify: evidence collected in $EV"
