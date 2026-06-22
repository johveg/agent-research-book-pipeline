#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

export HOME="${HOME:-/root}"
export PATH="/home/hermoine/terefohealreboa/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export PYTHONPATH="/home/hermoine/terefohealreboa:/home/hermoine/terefohealreboa/scripts:${PYTHONPATH:-}"
export TZ=Europe/Oslo
export TEREFO_STATUS_OPS_CHANNEL="AL-Hermoine-OPS"

cd /home/hermoine/terefohealreboa
RUN_ID="production-daily-$(TZ=Europe/Oslo date +%Y%m%d)"
if [[ -n "${TEREFO_PRODUCTION_RUN_ID:-}" ]]; then
  RUN_ID="${TEREFO_PRODUCTION_RUN_ID}"
fi
WRAPPER_INVOCATION_ID="${WRAPPER_INVOCATION_ID:-wrapper-${RUN_ID}-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
LOG_DIR="logs/runs"
CANONICAL_LOG="${LOG_DIR}/${RUN_ID}.log"
OUT_LOG="${LOG_DIR}/${RUN_ID}.cron.out"
ERR_LOG="${LOG_DIR}/${RUN_ID}.cron.err"
LOCK_FILE="/tmp/terefo-heal-reboa-production-daily.lock"
mkdir -p "${LOG_DIR}" reports/editorial reports/telegram reports/ops/outbox
: >"${CANONICAL_LOG}"
: >"${OUT_LOG}"
: >"${ERR_LOG}"
RUN_STARTED_AT_UNIX_S="$(date -u +%s)"

PYTHON=".venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

log_event() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${CANONICAL_LOG}"
}

emit_failed_closed() {
  local rc="$1"
  local reason="$2"
  local finished duration commit branch now_ms utc oslo
  finished="$(date -u +%s)"
  duration="$(( finished - RUN_STARTED_AT_UNIX_S ))"
  now_ms="$(( finished * 1000 ))"
  utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  oslo="$(TZ=Europe/Oslo date +%Y-%m-%dT%H:%M:%S%z)"
  commit="$(git rev-parse --short HEAD 2>/dev/null || true)"
  branch="$(git branch --show-current 2>/dev/null || true)"
  "${PYTHON}" - "$RUN_ID" "$RUN_STARTED_AT_UNIX_S" "$finished" "$duration" "$now_ms" "$utc" "$oslo" "$WRAPPER_INVOCATION_ID" "$branch" "$commit" "$reason" <<'PY'
import json, sys
run_id,start,finish,duration,ms,utc,oslo,wrapper,branch,commit,reason=sys.argv[1:]
payload={
 "mode":"production_daily","run_id":run_id,"status":"production_daily_failed_closed","severity":"failed_closed","disposition":"production_daily_failed_closed","final_disposition":"production_daily_failed_closed",
 "run_started_at_unix_s":int(start),"run_finished_at_unix_s":int(finish),"duration_seconds":int(duration),"emitted_at_unix_s":int(finish),"emitted_at_unix_ms":int(ms),"emitted_at_utc_iso":utc,"emitted_at_oslo_iso":oslo,"timezone":"Europe/Oslo",
 "target_channel":"AL-Hermoine-OPS","fallback_channel_used":False,"production_execution_attempted":True,"production_execution_completed":False,"production_daily_completed":False,"production_daily_failed_closed":True,"failed_closed_reason":reason,"wrapper_invocation_id":wrapper,"git_branch":branch,"git_commit":commit,"log_path":f"logs/runs/{run_id}.log","cron_out_path":f"logs/runs/{run_id}.cron.out","cron_err_path":f"logs/runs/{run_id}.cron.err","blockers":[reason]}
payload["status_metadata"]={k:payload[k] for k in ["emitted_at_unix_s","emitted_at_unix_ms","emitted_at_utc_iso","emitted_at_oslo_iso","timezone","run_id","status","severity","disposition","target_channel","fallback_channel_used","run_started_at_unix_s","run_finished_at_unix_s","duration_seconds"]}
for path in [f"reports/editorial/{run_id}-production-execute-once.json", "reports/telegram/production-daily-latest.json"]:
    open(path,"w",encoding="utf-8").write(json.dumps(payload,indent=2,sort_keys=True)+"\n")
open(f"reports/editorial/{run_id}-production-execute-once.md","w",encoding="utf-8").write("# Production daily failed closed\n\n```json\n"+json.dumps(payload,indent=2,sort_keys=True)+"\n```\n")
open("reports/telegram/production-daily-latest.md","w",encoding="utf-8").write("# Production daily failed closed\n\n```json\n"+json.dumps(payload,indent=2,sort_keys=True)+"\n```\n")
PY
  log_event "failed_closed rc=${rc} reason=${reason} finished_at=${finished}"
}

CMD=("${PYTHON}" scripts/closed_loop_production_scheduler.py
  --run-id "${RUN_ID}"
  --runtime-config config/closed_loop_runtime.json
  --mode production_daily
  --execute-once
  --allow-raw-collection
  --allow-extraction
  --allow-evidence-promotion
  --allow-author-editor-redteam
  --allow-guarded-book-publication
  --allow-daily-status-fallback
  --allow-commit-push-after-gates
  --send-telegram-status
  --wrapper-invocation-id "${WRAPPER_INVOCATION_ID}"
  --run-started-at-unix-s "${RUN_STARTED_AT_UNIX_S}"
  --output-json "reports/editorial/${RUN_ID}-production-execute-once.json"
  --output-md "reports/editorial/${RUN_ID}-production-execute-once.md"
  --telegram-status reports/telegram/production-daily-latest.md)

if [[ "${DRY_RUN}" == "1" ]]; then
  printf '{"dry_run":true,"run_id":"%s","wrapper_invocation_id":"%s","run_started_at_unix_s":%s,"ops_channel":"AL-Hermoine-OPS","canonical_log":"%s","stdout_log":"%s","stderr_log":"%s","command":' "${RUN_ID}" "${WRAPPER_INVOCATION_ID}" "${RUN_STARTED_AT_UNIX_S}" "${CANONICAL_LOG}" "${OUT_LOG}" "${ERR_LOG}"
  python3 - "${CMD[@]}" <<'PY'
import json, sys
print(json.dumps(sys.argv[1:]))
PY
  printf '}\n'
  exit 0
fi

run_scheduler() {
  log_event "wrapper_invocation_id=${WRAPPER_INVOCATION_ID} run_id=${RUN_ID} run_started_at_unix_s=${RUN_STARTED_AT_UNIX_S} target_channel=AL-Hermoine-OPS fallback_channel_used=false"
  log_event "scheduler_command=${CMD[*]}"
  "${CMD[@]}"
}

rc=0
if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    printf 'another production daily run is already active\n' >"${ERR_LOG}"
    log_event "lock_prevented_overlap"
    emit_failed_closed 75 "wrapper_lock_prevented_overlap"
    exit 75
  fi
  if ! run_scheduler > >(tee -a "${OUT_LOG}" "${CANONICAL_LOG}") 2> >(tee -a "${ERR_LOG}" "${CANONICAL_LOG}" >&2); then
    rc=$?
    emit_failed_closed "$rc" "scheduler_failed_closed"
    exit "${rc}"
  fi
else
  if ! run_scheduler > >(tee -a "${OUT_LOG}" "${CANONICAL_LOG}") 2> >(tee -a "${ERR_LOG}" "${CANONICAL_LOG}" >&2); then
    rc=$?
    emit_failed_closed "$rc" "scheduler_failed_closed"
    exit "${rc}"
  fi
fi
RUN_FINISHED_AT_UNIX_S="$(date -u +%s)"
log_event "run_finished_at_unix_s=${RUN_FINISHED_AT_UNIX_S} duration_seconds=$((RUN_FINISHED_AT_UNIX_S - RUN_STARTED_AT_UNIX_S))"
exit 0
