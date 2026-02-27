#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BOT_SCRIPT="$SCRIPT_DIR/tg_codex_bot.py"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/bot.pid"
LOG_FILE="$RUNTIME_DIR/bot.log"
STATE_PATH="$RUNTIME_DIR/bot_state.json"

# ===================== Env Config =====================
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
ALLOWED_TELEGRAM_USER_IDS="${ALLOWED_TELEGRAM_USER_IDS:-}"
DEFAULT_CWD="${DEFAULT_CWD:-$SCRIPT_DIR}"
CODEX_BIN="${CODEX_BIN:-/Applications/Codex.app/Contents/Resources/codex}"
CODEX_SESSION_ROOT="${CODEX_SESSION_ROOT:-$HOME/.codex/sessions}"
TELEGRAM_INSECURE_SKIP_VERIFY="${TELEGRAM_INSECURE_SKIP_VERIFY:-1}"
TELEGRAM_CA_BUNDLE="${TELEGRAM_CA_BUNDLE:-}"
# ============================================================

fail_if_not_configured() {
  if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
    echo "[error] 缺少环境变量 TELEGRAM_BOT_TOKEN"
    exit 1
  fi
  if [[ -z "$ALLOWED_TELEGRAM_USER_IDS" ]]; then
    echo "[error] 缺少环境变量 ALLOWED_TELEGRAM_USER_IDS"
    exit 1
  fi
  if [[ ! "$TELEGRAM_BOT_TOKEN" =~ ^[0-9]{6,}:[A-Za-z0-9_-]{20,}$ ]]; then
    echo "[error] TELEGRAM_BOT_TOKEN 格式无效，应类似: 123456789:ABCDEF..."
    exit 1
  fi
  if [[ ! "$ALLOWED_TELEGRAM_USER_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo "[error] ALLOWED_TELEGRAM_USER_IDS 格式错误，应为数字 ID，多个用逗号分隔"
    exit 1
  fi
  if [[ ! -x "$CODEX_BIN" ]]; then
    echo "[error] CODEX_BIN 不存在或不可执行: $CODEX_BIN"
    exit 1
  fi
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
  fi
  local existing_pid
  existing_pid="$(pgrep -f "$BOT_SCRIPT" | head -n 1 || true)"
  if [[ -n "${existing_pid}" ]]; then
    echo "$existing_pid" >"$PID_FILE"
    return 0
  fi
  return 1
}

start() {
  fail_if_not_configured
  mkdir -p "$RUNTIME_DIR"

  if is_running; then
    echo "[info] 服务已运行，PID=$(cat "$PID_FILE")"
    exit 0
  fi

  echo "[info] 启动中..."
  nohup env \
    TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
    ALLOWED_TELEGRAM_USER_IDS="$ALLOWED_TELEGRAM_USER_IDS" \
    DEFAULT_CWD="$DEFAULT_CWD" \
    CODEX_BIN="$CODEX_BIN" \
    CODEX_SESSION_ROOT="$CODEX_SESSION_ROOT" \
    STATE_PATH="$STATE_PATH" \
    TELEGRAM_INSECURE_SKIP_VERIFY="$TELEGRAM_INSECURE_SKIP_VERIFY" \
    TELEGRAM_CA_BUNDLE="$TELEGRAM_CA_BUNDLE" \
    "$PYTHON_BIN" -u "$BOT_SCRIPT" >>"$LOG_FILE" 2>&1 &

  local pid=$!
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
  if is_running; then
    local pid
    pid="$(cat "$PID_FILE")"
    kill "$pid" >/dev/null 2>&1 || true
    rm -f "$PID_FILE"
    echo "[ok] 已停止，PID=$pid"
  else
    echo "[info] 服务未运行"
  fi
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

restart() {
  stop
  start
}

usage() {
  cat <<EOF
用法: ./run.sh [start|stop|restart|status|logs]
默认: start

启动前先设置环境变量：
export TELEGRAM_BOT_TOKEN="你的 bot token"
export ALLOWED_TELEGRAM_USER_IDS="你的数字ID,可多个"
EOF
}

cmd="${1:-start}"
case "$cmd" in
start) start ;;
stop) stop ;;
restart) restart ;;
status) status ;;
logs) logs ;;
help|-h|--help) usage ;;
*)
  usage
  exit 1
  ;;
esac
