#!/usr/bin/env bash
# Drive research-eval (REAL: one agent run + judge calls per case) on fireworks-glm, judged by
# fireworks-glm, persisted and traced as tenant verify-<RUN_ID>.
#
#   drive_eval.sh <RUN_ID> [CASE_ID]       # default CASE_ID: mcp (from evals/smoke.jsonl)
#
# Writes a ONE-case dataset to evidence/verify/<RUN_ID>/eval-dataset.jsonl (never the 10-case set),
# then runs
#   scripts/tenant_env.sh verify-<RUN_ID> uv run research-eval --model fireworks-glm \
#     --judge fireworks-glm --tenant verify-<RUN_ID> --persist \
#     --dataset <that file> --out evidence/verify/<RUN_ID>/eval_results.md
# Outputs: eval_results.md, eval_results.json, eval.stdout, eval.stderr.log, eval.exit, eval.summary.txt.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 1 ] && [ $# -le 2 ] || die "usage: $0 <RUN_ID> [CASE_ID]"
set_run "$1"
case_id=${2:-mcp}
cd "$REPO"
[ -f "$ENV_FILE" ] || die "tenant $TENANT not stamped: run stamp.sh $RUN_ID first"
mkdir -p "$EV"
[ ! -e "$EV/eval_results.json" ] || die "$EV/eval_results.json exists (evidence is never overwritten)"

dataset=$EV/eval-dataset.jsonl
jq -c --arg id "$case_id" 'select(.id == $id)' apps/research_agent/evals/smoke.jsonl >"$dataset"
[ "$(wc -l <"$dataset" | tr -d ' ')" = 1 ] || die "case '$case_id' not found exactly once in evals/smoke.jsonl"

cmd=(scripts/tenant_env.sh "$TENANT" uv run --no-sync research-eval --model "$MODEL" --judge "$MODEL"
  --tenant "$TENANT" --persist --dataset "$dataset" --out "$EV/eval_results.md")
printf '%q ' "${cmd[@]}" >"$EV/eval.cmd.txt"
echo >>"$EV/eval.cmd.txt"
echo "verify: running 1-case eval '$case_id' (real model + judge calls, $MODEL)" >&2
set +e
"${cmd[@]}" 2> >(tee "$EV/eval.stderr.log" >&2) | tee "$EV/eval.stdout"
rc=${PIPESTATUS[0]}
set -e
sleep 1
echo "$rc" >"$EV/eval.exit"
{
  echo "eval exit: $rc  case: $case_id  judge: $MODEL"
  grep -E '^(eval user: |usage: )' "$EV/eval.stdout" || true
  if [ -s "$EV/eval_results.json" ]; then
    jq -c '{aggregate, cases: [.cases[] | {case_id, scores, error, trace_id, usage}]}' "$EV/eval_results.json"
  fi
} >"$EV/eval.summary.txt"
cat "$EV/eval.summary.txt"
exit "$rc"
