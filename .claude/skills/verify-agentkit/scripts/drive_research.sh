#!/usr/bin/env bash
# Drive one REAL research turn (costs tokens) on fireworks-glm as tenant verify-<RUN_ID>.
#
#   drive_research.sh <RUN_ID> <LABEL> "<question>" [research args...]
#
# Default: persisted + traced through the stamped tenant, i.e.
#   scripts/tenant_env.sh verify-<RUN_ID> uv run research "<question>" --model fireworks-glm \
#     --tenant verify-<RUN_ID> --persist --out evidence/verify/<RUN_ID>/<LABEL>.report.md [args...]
# Extra args pass through (e.g. --thread <uuid> to resume, --user alice, -v).
# --ephemeral (first extra arg) runs without the tenant, --persist or tracing (no Docker needed).
# --model is refused: live runs use fireworks-glm only.
#
# Writes to evidence/verify/<RUN_ID>/: <LABEL>.cmd.txt, <LABEL>.stdout, <LABEL>.stderr.log,
# <LABEL>.exit, <LABEL>.report.md, <LABEL>.summary.txt (thread/resumed/trace/usage lines).
# Exits with the CLI's exit code.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 3 ] || die "usage: $0 <RUN_ID> <LABEL> \"<question>\" [--ephemeral] [research args...]"
set_run "$1"
label=$2
question=$3
shift 3
[[ $label =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "LABEL must be lowercase letters, digits, _ or -"
for a in "$@"; do
  case $a in --model | --model=*) die "--model is fixed to $MODEL for live runs" ;; esac
done
cd "$REPO"
mkdir -p "$EV"
[ ! -e "$EV/$label.stdout" ] || die "$EV/$label.stdout exists; pick a new LABEL (evidence is never overwritten)"

ephemeral=0
if [ "${1:-}" = "--ephemeral" ]; then
  ephemeral=1
  shift
fi
out=$EV/$label.report.md
if [ $ephemeral -eq 1 ]; then
  cmd=(uv run --no-sync research "$question" --model "$MODEL" --out "$out" "$@")
else
  [ -f "$ENV_FILE" ] || die "tenant $TENANT not stamped: run stamp.sh $RUN_ID first"
  cmd=(scripts/tenant_env.sh "$TENANT" uv run --no-sync research "$question" --model "$MODEL"
    --tenant "$TENANT" --persist --out "$out" "$@")
fi

printf '%q ' "${cmd[@]}" >"$EV/$label.cmd.txt"
echo >>"$EV/$label.cmd.txt"
echo "verify: running $label (real model call, $MODEL)" >&2
set +e
"${cmd[@]}" 2> >(tee "$EV/$label.stderr.log" >&2) | tee "$EV/$label.stdout"
rc=${PIPESTATUS[0]}
set -e
sleep 1 # let the stderr tee drain
echo "$rc" >"$EV/$label.exit"

{
  echo "label: $label  exit: $rc  mode: $([ $ephemeral -eq 1 ] && echo ephemeral || echo "persisted tenant=$TENANT")"
  grep -E '^(thread: |resumed thread |trace: |usage: |wrote )' "$EV/$label.stdout" || true
  grep -E 'Decisions|selection|TenantMismatch|ConfigError|agent finished' "$EV/$label.stderr.log" | sed 's/^/stderr: /' | tail -n 8 || true
  [ -s "$out" ] && echo "report: $out ($(wc -c <"$out" | tr -d ' ') bytes, $(grep -cE '^\[[0-9]+\] *https?://' "$out" || true) source lines)"
} >"$EV/$label.summary.txt"
cat "$EV/$label.summary.txt"
exit "$rc"
