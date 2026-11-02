#!/usr/bin/env bash
# Launch: stamp the dedicated verification tenant verify-<RUN_ID> (own compose project, Postgres
# volume, collector, ports, AES key) and wait until it is usable, then run the tenant doctor.
#
#   RUN_ID=$(date +%Y%m%d-%H%M%S)
#   .claude/skills/verify-agentkit/scripts/stamp.sh "$RUN_ID"
#
# Ready = the line `stamp: tenant verify-<RUN_ID> ready: ...` (migrations applied, agentkit_usage
# created) followed by `doctor: OK`. Transcript: evidence/verify/<RUN_ID>/stamp.log.
# Tear down with cleanup.sh <RUN_ID> (collects evidence first, then make unstamp).
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -eq 1 ] || die "usage: $0 <RUN_ID>"
set_run "$1"
cd "$REPO"
mkdir -p "$EV"
[ ! -f "$ENV_FILE" ] || echo "verify: $ENV_FILE exists; stamp reuses it (leftover from an earlier attempt?)" >&2

echo "\$ make stamp TENANT=$TENANT" >"$EV/stamp.log"
make stamp TENANT="$TENANT" 2>&1 | tee -a "$EV/stamp.log"
grep -q "^stamp: tenant $TENANT ready" "$EV/stamp.log" || die "stamp did not report ready (see $EV/stamp.log)"
"$(dirname "$0")/doctor.sh" "$RUN_ID"
echo "verify: tenant=$TENANT evidence=$EV"
