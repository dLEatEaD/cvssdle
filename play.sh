#!/usr/bin/env bash
# Serve CVSSdle locally and open it in your browser.
# Usage: ./play.sh [port]
set -euo pipefail

PORT="${1:-8777}"
cd "$(dirname "$0")"

if [ ! -f index.html ]; then
  echo "index.html missing - building it first..."
  python3 build_site.py
fi

echo "CVSSdle running at http://localhost:$PORT"
echo "Press Ctrl+C to stop."

python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT INT TERM

sleep 1
open "http://localhost:$PORT"
wait $SERVER_PID
