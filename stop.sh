#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/data/runtime"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
is_running() {
  local pid="$1"
  if [[ -z "${pid:-}" ]]; then
    return 1
  fi
  kill -0 "$pid" >/dev/null 2>&1
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

matches_kind() {
  local kind="$1"
  local pid="$2"
  case "$kind" in
    backend) is_backend_process "$pid" ;;
    frontend) is_frontend_process "$pid" ;;
    *) return 1 ;;
  esac
}

stop_one() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local kind="$4"

  local pid=""
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
  fi

  if ! is_running "$pid"; then
    local port_pid
    port_pid="$(find_port_pid "$port" || true)"
    if is_running "$port_pid" && matches_kind "$kind" "$port_pid"; then
      pid="$port_pid"
    else
      echo "$name not running."
      rm -f "$pid_file"
      return
    fi
  fi

  if ! matches_kind "$kind" "$pid"; then
    echo "$name PID $pid is not recognized as this project process, skip."
    return
  fi

  if ! is_running "$pid"; then
    echo "$name not running."
  else
    echo "Stopping $name (PID: $pid)..."
    kill "$pid" >/dev/null 2>&1 || true

    for _ in {1..20}; do
      if ! is_running "$pid"; then
        rm -f "$pid_file"
        echo "$name stopped."
        return
      fi
      sleep 0.3
    done

    echo "Force killing $name (PID: $pid)..."
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi

  rm -f "$pid_file"
  echo "$name stopped."
}

stop_one "Frontend" "$FRONTEND_PID_FILE" 3000 frontend
stop_one "Backend" "$BACKEND_PID_FILE" 8000 backend
