#!/usr/bin/env bash
# Reload the app after an update without closing the public link opened by run-live.sh.
set -euo pipefail
PID="$(pgrep -f '[u]vicorn app.main:app --host 127.0.0.1' || true)"
if [ -z "$PID" ]; then
  echo "The app is not running. Start the site with ./run-live.sh"
  exit 1
fi
kill $PID
echo "App restarting (the link stays the same)..."
