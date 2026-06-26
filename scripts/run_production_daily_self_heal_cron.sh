#!/usr/bin/env bash
set -euo pipefail
export HOME=/root
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=/home/hermoine/agent-research-book-pipeline/scripts:/home/hermoine/agent-research-book-pipeline
cd /home/hermoine/agent-research-book-pipeline
mkdir -p logs/runs
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
log="logs/runs/production-daily-self-heal-${stamp}.log"
python3 scripts/production_daily_self_heal.py --repo /home/hermoine/agent-research-book-pipeline --timezone Europe/Oslo --expect-schedule-time 05:30 --target-channel AL-Hermoine-OPS --output-json reports/editorial/run54-production-self-heal.json --output-md reports/editorial/run54-production-self-heal.md --telegram-status reports/telegram/run54-production-self-heal-status.md >"$log" 2>&1
