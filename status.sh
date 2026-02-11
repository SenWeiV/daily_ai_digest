#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/data/runtime"

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

print_status() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local log_file="$4"
  local url="$5"
  local kind="$6"

  local pid=""
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
  fi

  if ! is_running "$pid"; then
    pid="$(find_port_pid "$port" || true)"
  fi

  if is_running "$pid" && matches_kind "$kind" "$pid"; then
    echo "$name: running (PID: $pid, URL: $url)"
  else
    echo "$name: stopped"
  fi

  if [[ -f "$log_file" ]]; then
    echo "  log: $log_file"
  fi
}

print_status "Backend" "$BACKEND_PID_FILE" 8000 "$BACKEND_LOG_FILE" "http://localhost:8000" backend
print_status "Frontend" "$FRONTEND_PID_FILE" 3000 "$FRONTEND_LOG_FILE" "http://localhost:3000" frontend
