#!/usr/bin/env bash
# Tear down what verification run <RUN_ID> created; never the evidence.
#
#   cleanup.sh <RUN_ID>
#
# 1. If the stack is up and evidence/verify/<RUN_ID>/ lacks spans.jsonl or agentkit_usage.csv,
#    runs collect_evidence.sh first (best effort; a failed check does not stop cleanup), so
#    `down -v` can never destroy an uncollected trace or ledger (Ruling P12).
# 2. make unstamp TENANT=verify-<RUN_ID>  (compose project agentkit-verify-<RUN_ID> only)
# 3. Deletes deploy/tenants/verify-<RUN_ID>.env (throwaway AES key) and the tenant's collector
#    output dir deploy/otel-out/verify-<RUN_ID>/ (its spans were copied in step 1).
# 4. Asserts no container or volume of that project remains, lists any other agentkit-* containers
#    (never touched), and lists the evidence dir to show it survived.
# Safe to run after a failed or partial attempt, and twice.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -eq 1 ] || die "usage: $0 <RUN_ID>"
set_run "$1"
cd "$REPO"
case $TENANT in verify-*) ;; *) die "refusing to clean non-verification tenant $TENANT" ;; esac
mkdir -p "$EV"
log=$EV/cleanup.log
echo "cleanup: $(date -u +%Y-%m-%dT%H:%M:%SZ) tenant=$TENANT" >>"$log"

if stack_up && { [ ! -s "$EV/spans.jsonl" ] || [ ! -s "$EV/agentkit_usage.csv" ]; }; then
  echo "cleanup: collecting evidence before unstamp" | tee -a "$log"
  "$(dirname "$0")/collect_evidence.sh" "$RUN_ID" 2>&1 | tee -a "$log" || true
fi
# Even with the stack down, never drop a spans file that was not copied.
if [ -s "$OTEL_OUT/spans.jsonl" ] && [ ! -s "$EV/spans.jsonl" ]; then
  cp "$OTEL_OUT/spans.jsonl" "$EV/spans.jsonl"
fi

make unstamp TENANT="$TENANT" 2>&1 | tee -a "$log"
rm -f "$ENV_FILE"
rm -rf "$OTEL_OUT"

left=$(docker ps -a -q --filter "label=com.docker.compose.project=$PROJECT")
vols=$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT")
[ -z "$left$vols" ] || die "project $PROJECT still has containers/volumes: $left $vols"
[ ! -e "$ENV_FILE" ] || die "$ENV_FILE still exists"
echo "cleanup: $PROJECT removed (containers, network, volume), env file and collector dir deleted" | tee -a "$log"
others=$(docker ps -a --format '{{.Names}}' | grep '^agentkit-' || true)
echo "cleanup: other agentkit-* containers (not touched): ${others:-none}" | tee -a "$log"
echo "cleanup: evidence kept at $EV:"
ls -la "$EV"
