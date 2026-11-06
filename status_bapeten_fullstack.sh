#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$ROOT/run/bapeten-fullstack.pid"
if [[ -f "$ROOT/backend/.env" ]]; then
  set -a; source "$ROOT/backend/.env"; set +a
fi
PORT="${BAPETEN_PORT:-8010}"
if [ ! -f "$PIDFILE" ]; then echo 'Status: STOPPED (PID file tidak ditemukan)'; exit 0; fi
PID="$(cat "$PIDFILE")"
if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
  if [[ "$(readlink -f "/proc/$PID/cwd" 2>/dev/null || true)" != "$ROOT/backend" ]]; then
    echo 'ERROR: PID bukan milik backend industri pada folder ini.' >&2; exit 1
  fi
  CMD="$(ps -p "$PID" -o args= 2>/dev/null || true)"
  if [[ "$CMD" != *'uvicorn app.main:app'* ]]; then
    echo 'ERROR: PID bukan proses Uvicorn aplikasi.' >&2; exit 1
  fi
  if [[ "$CMD" =~ --port[[:space:]]+([0-9]+) ]]; then
    PORT="${BASH_REMATCH[1]}"
  fi
  echo "Status: RUNNING (PID $PID)"
  echo "Aplikasi: Industri | Folder: $ROOT"
  echo "URL HPC: http://127.0.0.1:$PORT"
  echo "Buka di laptop: http://localhost:$PORT/"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/v1/health" || true
    echo
  fi
else echo 'Status: STOPPED (PID file kedaluwarsa)'; fi
