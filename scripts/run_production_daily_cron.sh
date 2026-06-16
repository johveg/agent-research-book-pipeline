#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

export HOME="${HOME:-/root}"
export PATH="/home/hermoine/terefohealreboa/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export TZ=Europe/Oslo
export TEREFO_STATUS_OPS_CHANNEL="AL-Hermoine-OPS"

cd /home/hermoine/terefohealreboa
RUN_ID="production-daily-$(TZ=Europe/Oslo date +%Y%m%d)"
LOG_DIR="logs/runs"
OUT_LOG="${LOG_DIR}/${RUN_ID}.cron.out"
ERR_LOG="${LOG_DIR}/${RUN_ID}.cron.err"
LOCK_FILE="/tmp/terefo-heal-reboa-production-daily.lock"
mkdir -p "${LOG_DIR}" reports/editorial reports/telegram

PYTHON=".venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

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
  --install-schedule-after-success
  --send-telegram-status
  --output-json "reports/editorial/${RUN_ID}-production-execute-once.json"
  --output-md "reports/editorial/${RUN_ID}-production-execute-once.md"
  --telegram-status reports/telegram/production-daily-latest.md)

if [[ "${DRY_RUN}" == "1" ]]; then
  printf '{"dry_run":true,"run_id":"%s","ops_channel":"AL-Hermoine-OPS","stdout_log":"%s","stderr_log":"%s","command":' "${RUN_ID}" "${OUT_LOG}" "${ERR_LOG}"
  python3 - "${CMD[@]}" <<'PY'
import json, sys
print(json.dumps(sys.argv[1:]))
PY
  printf '}\n'
  exit 0
fi

run_scheduler() {
  printf 'run_id=%s\nops_channel=AL-Hermoine-OPS\nstarted_at=%s\n' "${RUN_ID}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "${CMD[@]}"
}

if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    printf 'another production daily run is already active\n' >"${ERR_LOG}"
    exit 75
  fi
  if ! run_scheduler >"${OUT_LOG}" 2>"${ERR_LOG}"; then
    rc=$?
    {
      printf '{"component":"production_daily_scheduler","run_id":"%s","status":"production_daily_failed_closed","severity":"failed_closed","disposition":"production_daily_scheduler_repaired","target_channel":"AL-Hermoine-OPS","summary":"cron wrapper failed closed; see stderr log","log_path":"%s"}\n' "${RUN_ID}" "${ERR_LOG}"
    } > "reports/telegram/production-daily-latest.json"
    "${PYTHON}" scripts/status_message_contract.py --input-json reports/telegram/production-daily-latest.json --output-md reports/telegram/production-daily-latest.md >/dev/null || true
    exit "${rc}"
  fi
else
  run_scheduler >"${OUT_LOG}" 2>"${ERR_LOG}"
fi
