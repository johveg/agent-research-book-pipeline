#!/usr/bin/env bash
set -euo pipefail
export HOME=/root
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=/home/hermoine/terefohealreboa/scripts:/home/hermoine/terefohealreboa
cd /home/hermoine/terefohealreboa
mkdir -p logs/runs reports/ops/outbox
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
log="logs/runs/ops-delivery-controller-${stamp}.log"
lock="/tmp/terefo_ops_delivery_controller.lock"
(
  flock -n 9 || { echo '{"ok":false,"status":"ops_delivery_controller_overlap","fallback_channel_used":false}'; exit 0; }
  python3 scripts/ops_delivery_controller.py --run-id run54 --target-channel AL-Hermoine-OPS --outbox reports/ops/outbox/ops_delivery_outbox.jsonl --state reports/ops/outbox/ops_delivery_outbox_state.json --output-json reports/editorial/run54-ops-delivery-controller.json --output-md reports/editorial/run54-ops-delivery-controller.md
) 9>"$lock" >"$log" 2>&1
