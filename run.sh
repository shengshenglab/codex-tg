#!/usr/bin/env bash
# ====== Fill These 2 Values ======
TELEGRAM_BOT_TOKEN="PASTE_YOUR_BOT_TOKEN"
ALLOWED_TELEGRAM_USER_IDS="PASTE_YOUR_NUMERIC_USER_ID"
# =================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BOT_SCRIPT="$SCRIPT_DIR/tg_codex_bot.py"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/bot.pid"
LOG_FILE="$RUNTIME_DIR/bot.log"

# Optional defaults (align with README)
CODEX_SESSION_ROOT="${CODEX_SESSION_ROOT:-$HOME/.codex/sessions}"
STATE_PATH="${STATE_PATH:-$RUNTIME_DIR/bot_state.json}"
DEFAULT_CWD="${DEFAULT_CWD:-$SCRIPT_DIR}"

validate_config() {
  if [[ "$TELEGRAM_BOT_TOKEN" == PASTE_* ]] || [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
    echo "[error] 请先在 run.sh 顶部填写 TELEGRAM_BOT_TOKEN"
    exit 1
  fi
  if [[ "$ALLOWED_TELEGRAM_USER_IDS" == PASTE_* ]] || [[ -z "$ALLOWED_TELEGRAM_USER_IDS" ]]; then
    echo "[error] 请先在 run.sh 顶部填写 ALLOWED_TELEGRAM_USER_IDS"
    exit 1
  fi
  if [[ ! "$ALLOWED_TELEGRAM_USER_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo "[error] ALLOWED_TELEGRAM_USER_IDS 格式错误，应为数字 ID，多个用逗号分隔"
    exit 1
  fi
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

start() {
  validate_config
  mkdir -p "$RUNTIME_DIR"

  if is_running; then
    echo "[info] 已运行，PID=$(cat "$PID_FILE")"
    exit 0
  fi

  nohup env \
    TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
    ALLOWED_TELEGRAM_USER_IDS="$ALLOWED_TELEGRAM_USER_IDS" \
    CODEX_SESSION_ROOT="$CODEX_SESSION_ROOT" \
    STATE_PATH="$STATE_PATH" \
    DEFAULT_CWD="$DEFAULT_CWD" \
    "$PYTHON_BIN" -u "$BOT_SCRIPT" >>"$LOG_FILE" 2>&1 &

  local pid="$!"
  echo "$pid" >"$PID_FILE"
  sleep 1

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[ok] 已启动，PID=$pid"
    echo "[ok] 日志: $LOG_FILE"
  else
    echo "[error] 启动失败，最近日志："
    tail -n 50 "$LOG_FILE" || true
    exit 1
  fi
}

stop() {
  if ! is_running; then
    echo "[info] 未运行"
    exit 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" >/dev/null 2>&1 || true
  rm -f "$PID_FILE"
  echo "[ok] 已停止，PID=$pid"
}

status() {
  if is_running; then
    echo "[ok] 运行中，PID=$(cat "$PID_FILE")"
  else
    echo "[info] 未运行"
  fi
}

logs() {
  mkdir -p "$RUNTIME_DIR"
  touch "$LOG_FILE"
  tail -f "$LOG_FILE"
}

usage() {
  cat <<'EOF'
用法: ./run.sh [start|stop|status|logs]
默认: start
EOF
}

cmd="${1:-start}"
case "$cmd" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  logs) logs ;;
  help|-h|--help) usage ;;
  *)
    usage
    exit 1
    ;;
esac
