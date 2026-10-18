#!/usr/bin/env bash
# Stop Last Mile Home's agent processes (ports 8200, 8201 and 8202).
for port in 8200 8201 8202; do
  pid=$(lsof -nP -iTCP:$port -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $2}')
  if [ -n "$pid" ]; then
    kill -INT "$pid" 2>/dev/null
    for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$pid" 2>/dev/null || true
    echo "Stopped port $port (pid $pid)."
  fi
done
