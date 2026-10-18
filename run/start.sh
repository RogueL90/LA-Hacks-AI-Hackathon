#!/usr/bin/env bash
# Start Last Mile Home: the specialist team (port 8201) and the coordinator (port 8200).
# Logs: logs/team.log and logs/bureau.log. Stop with run/stop.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
for port in 8200 8201; do
  if lsof -nP -iTCP:$port -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is busy; run run/stop.sh first." >&2
    exit 1
  fi
done
PYTHONUNBUFFERED=1 nohup .venv/bin/python -m run.bureau team >> logs/team.log 2>&1 &
PYTHONUNBUFFERED=1 nohup .venv/bin/python -m run.bureau front >> logs/bureau.log 2>&1 &
echo "Started: team on 8201, Last Mile Home on 8200."
