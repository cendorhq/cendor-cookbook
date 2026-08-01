#!/usr/bin/env bash
# Start the Chat Playground in the background and DO NOT RETURN UNTIL IT ANSWERS.
#
# ⚠️ The waiting is the whole point, and it is a fix, not politeness. `postStartCommand` used to be
# a bare one-liner:
#
#     nohup uv run --group apps python recipes/apps/chat-playground/app.py > /tmp/playground.log 2>&1 &
#
# which returns instantly — while the app is still importing gradio and building its 424-policy
# knowledge base, which takes ~37 s in this image. The lifecycle shell then exits and takes the
# half-started child with it. Measured 2026-08-01 in the real devcontainer: port 7860 refused the
# connection and `/tmp/playground.log` was **0 bytes**, so the README's "watch /tmp/playground.log
# for boot progress" showed an empty file and there was nothing at all to diagnose. `setsid` alone
# did not save it either. A process that is fully established before its parent exits does survive:
# with the wait loop below, a separate session gets HTTP 200 long afterwards.
#
# The second reason to wait: a failure is now VISIBLE. This script exits non-zero and prints the
# log, so a broken app shows up as a failed postStart instead of a port that silently never opens.
set -uo pipefail

PORT="${PORT:-7860}"
LOG="${PLAYGROUND_LOG:-/tmp/playground.log}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
  echo "Chat Playground already listening on ${PORT}."
  exit 0
fi

cd "$HERE"
# PYTHONUNBUFFERED so the log is useful while it boots — without it gradio's startup lines sit in
# a buffer and the file the README points readers at stays empty for the whole 37 s.
setsid env PYTHONUNBUFFERED=1 GRADIO_ANALYTICS_ENABLED=False \
  uv run --group apps python recipes/apps/chat-playground/app.py > "$LOG" 2>&1 < /dev/null &

for i in $(seq 1 120); do
  if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
    echo "Chat Playground is up on ${PORT} (took ${i}s). Log: ${LOG}"
    exit 0
  fi
  sleep 1
done

echo "Chat Playground did not come up on ${PORT} within 120s. Last 30 log lines:" >&2
tail -30 "$LOG" >&2 || true
exit 1
