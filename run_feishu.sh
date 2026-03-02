#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BOT_SCRIPT="$SCRIPT_DIR/feishu_longconn_service.py"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/feishu_bot.pid"
LOG_FILE="$RUNTIME_DIR/feishu_bot.log"
STATE_PATH="$RUNTIME_DIR/feishu_bot_state.json"

# ===================== Env Config =====================
FEISHU_APP_ID="${FEISHU_APP_ID:-}"
FEISHU_APP_SECRET="${FEISHU_APP_SECRET:-}"
ALLOWED_FEISHU_OPEN_IDS="${ALLOWED_FEISHU_OPEN_IDS:-}"
FEISHU_ENABLE_P2P="${FEISHU_ENABLE_P2P:-1}"
FEISHU_LOG_LEVEL="${FEISHU_LOG_LEVEL:-INFO}"
FEISHU_RICH_MESSAGE="${FEISHU_RICH_MESSAGE:-1}"
DEFAULT_CWD="${DEFAULT_CWD:-$SCRIPT_DIR}"
CODEX_BIN="${CODEX_BIN:-/Applications/Codex.app/Contents/Resources/codex}"
CODEX_SESSION_ROOT="${CODEX_SESSION_ROOT:-$HOME/.codex/sessions}"
CODEX_SANDBOX_MODE="${CODEX_SANDBOX_MODE:-danger-full-access}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-never}"
CODEX_DANGEROUS_BYPASS="${CODEX_DANGEROUS_BYPASS:-0}"
# ======================================================

fail_if_not_configured() {
  if [[ -z "$FEISHU_APP_ID" ]]; then
    echo "[error] 缺少环境变量 FEISHU_APP_ID"
    exit 1
  fi
  if [[ -z "$FEISHU_APP_SECRET" ]]; then
    echo "[error] 缺少环境变量 FEISHU_APP_SECRET"
    exit 1
  fi
  if [[ ! -x "$CODEX_BIN" ]]; then
    echo "[error] CODEX_BIN 不存在或不可执行: $CODEX_BIN"
    exit 1
  fi
}

ensure_dependency() {
  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import lark_oapi
PY
  then
    echo "[info] 安装依赖 lark-oapi..."
    "$PYTHON_BIN" -m pip install --user lark-oapi
  fi
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    rm -f "$PID_FILE"
  fi
  local existing_pid
  existing_pid="$(pgrep -f "$BOT_SCRIPT" 2>/dev/null | head -n 1 || true)"
  if [[ -n "${existing_pid}" ]]; then
    echo "$existing_pid" >"$PID_FILE"
    return 0
  fi
  return 1
}

start() {
  fail_if_not_configured
  ensure_dependency
  mkdir -p "$RUNTIME_DIR"

  if is_running; then
    echo "[info] 服务已运行，PID=$(cat "$PID_FILE")"
    exit 0
  fi

  echo "[info] 启动飞书长连接服务..."
  nohup env \
    FEISHU_APP_ID="$FEISHU_APP_ID" \
    FEISHU_APP_SECRET="$FEISHU_APP_SECRET" \
    ALLOWED_FEISHU_OPEN_IDS="$ALLOWED_FEISHU_OPEN_IDS" \
    FEISHU_ENABLE_P2P="$FEISHU_ENABLE_P2P" \
    FEISHU_LOG_LEVEL="$FEISHU_LOG_LEVEL" \
    FEISHU_RICH_MESSAGE="$FEISHU_RICH_MESSAGE" \
    DEFAULT_CWD="$DEFAULT_CWD" \
    CODEX_BIN="$CODEX_BIN" \
    CODEX_SESSION_ROOT="$CODEX_SESSION_ROOT" \
    CODEX_SANDBOX_MODE="$CODEX_SANDBOX_MODE" \
    CODEX_APPROVAL_POLICY="$CODEX_APPROVAL_POLICY" \
    CODEX_DANGEROUS_BYPASS="$CODEX_DANGEROUS_BYPASS" \
    STATE_PATH="$STATE_PATH" \
    "$PYTHON_BIN" -u "$BOT_SCRIPT" >>"$LOG_FILE" 2>&1 &

  local pid=$!
  echo "$pid" >"$PID_FILE"
  sleep 2

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[ok] 已启动，PID=$pid"
    echo "[ok] 日志: $LOG_FILE"
  else
    rm -f "$PID_FILE"
    echo "[error] 启动失败，最近日志："
    tail -n 80 "$LOG_FILE" || true
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
用法: ./run_feishu.sh [start|stop|restart|status|logs]
默认: start

启动前先设置环境变量：
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"

可选：
export ALLOWED_FEISHU_OPEN_IDS="ou_xxx,ou_yyy"
export FEISHU_ENABLE_P2P=1
export FEISHU_LOG_LEVEL=INFO
export FEISHU_RICH_MESSAGE=1

# Codex command execution policy (high risk defaults)
export CODEX_SANDBOX_MODE="danger-full-access"
export CODEX_APPROVAL_POLICY="never"
export CODEX_DANGEROUS_BYPASS=0
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
