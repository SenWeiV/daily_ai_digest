#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/data/runtime"
mkdir -p "$RUNTIME_DIR"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG_FILE="$RUNTIME_DIR/backend.log"
FRONTEND_LOG_FILE="$RUNTIME_DIR/frontend.log"
is_running() {
  local pid="$1"
  if [[ -z "${pid:-}" ]]; then
    return 1
  fi
  kill -0 "$pid" >/dev/null 2>&1
}

read_pid() {
  local file="$1"
  if [[ -f "$file" ]]; then
    cat "$file"
  fi
}

find_port_pid() {
  local port="$1"
  lsof -n -P -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1
}

is_backend_process() {
  local pid="$1"
  if ! is_running "$pid"; then
    return 1
  fi
  local cmd
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$cmd" == *"run.py"* ]]
}

is_frontend_process() {
  local pid="$1"
  if ! is_running "$pid"; then
    return 1
  fi
  local cmd
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$cmd" == *"vite"* && "$cmd" == *"--port 3000"* ]]
}

start_backend() {
  local existing_pid
  existing_pid="$(read_pid "$BACKEND_PID_FILE" || true)"
  if is_running "$existing_pid"; then
    echo "Backend already running (PID: $existing_pid)"
    return
  fi

  local port_pid
  port_pid="$(find_port_pid 8000 || true)"
  if is_running "$port_pid"; then
    if is_backend_process "$port_pid"; then
      echo "$port_pid" >"$BACKEND_PID_FILE"
      echo "Backend already running on port 8000 (PID: $port_pid)"
      return
    fi
    echo "Port 8000 is already in use by another process (PID: $port_pid)."
    exit 1
  fi

  echo "Starting backend..."
  (
    cd "$ROOT_DIR/backend"
    nohup ./venv/bin/python run.py >"$BACKEND_LOG_FILE" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
  sleep 1
  local new_pid
  new_pid="$(read_pid "$BACKEND_PID_FILE" || true)"
  if is_running "$new_pid"; then
    echo "Backend started (PID: $new_pid, http://localhost:8000)"
  else
    echo "Failed to start backend. Check log: $BACKEND_LOG_FILE"
    exit 1
  fi
}

start_frontend() {
  local existing_pid
  existing_pid="$(read_pid "$FRONTEND_PID_FILE" || true)"
  if is_running "$existing_pid"; then
    echo "Frontend already running (PID: $existing_pid)"
    return
  fi

  local port_pid
  port_pid="$(find_port_pid 3000 || true)"
  if is_running "$port_pid"; then
    if is_frontend_process "$port_pid"; then
      echo "$port_pid" >"$FRONTEND_PID_FILE"
      echo "Frontend already running on port 3000 (PID: $port_pid)"
      return
    fi
    echo "Port 3000 is already in use by another process (PID: $port_pid)."
    exit 1
  fi

  echo "Starting frontend..."
  (
    cd "$ROOT_DIR/frontend"
    nohup npm run dev -- --host 0.0.0.0 --port 3000 >"$FRONTEND_LOG_FILE" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )
  sleep 1
  local new_pid
  new_pid="$(read_pid "$FRONTEND_PID_FILE" || true)"
  if is_running "$new_pid"; then
    echo "Frontend started (PID: $new_pid, http://localhost:3000)"
  else
    echo "Failed to start frontend. Check log: $FRONTEND_LOG_FILE"
    exit 1
  fi
}

start_backend
start_frontend

echo "Done."
