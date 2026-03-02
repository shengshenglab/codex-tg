#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"

# Telegram runtime
TG_BOT_SCRIPT="$SCRIPT_DIR/tg_codex_bot.py"
TG_PID_FILE="$RUNTIME_DIR/bot.pid"
TG_LOG_FILE="$RUNTIME_DIR/bot.log"
TG_STATE_PATH="$RUNTIME_DIR/bot_state.json"

# Feishu runtime
FEISHU_RUN_SCRIPT="$SCRIPT_DIR/run_feishu.sh"
FEISHU_LOG_FILE="$RUNTIME_DIR/feishu_bot.log"

# Shared env
DEFAULT_CWD="${DEFAULT_CWD:-$SCRIPT_DIR}"
CODEX_BIN="${CODEX_BIN:-/Applications/Codex.app/Contents/Resources/codex}"
CODEX_SESSION_ROOT="${CODEX_SESSION_ROOT:-$HOME/.codex/sessions}"
CODEX_SANDBOX_MODE="${CODEX_SANDBOX_MODE:-danger-full-access}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-never}"
CODEX_DANGEROUS_BYPASS="${CODEX_DANGEROUS_BYPASS:-0}"

# Telegram env
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
ALLOWED_TELEGRAM_USER_IDS="${ALLOWED_TELEGRAM_USER_IDS:-}"
TELEGRAM_INSECURE_SKIP_VERIFY="${TELEGRAM_INSECURE_SKIP_VERIFY:-1}"
TELEGRAM_CA_BUNDLE="${TELEGRAM_CA_BUNDLE:-}"

# Feishu env
FEISHU_APP_ID="${FEISHU_APP_ID:-}"
FEISHU_APP_SECRET="${FEISHU_APP_SECRET:-}"

has_tg_config() {
  [[ -n "$TELEGRAM_BOT_TOKEN" ]]
}

has_feishu_config() {
  [[ -n "$FEISHU_APP_ID" || -n "$FEISHU_APP_SECRET" ]]
}

validate_tg_config() {
  if ! has_tg_config; then
    return 0
  fi
  if [[ ! "$TELEGRAM_BOT_TOKEN" =~ ^[0-9]{6,}:[A-Za-z0-9_-]{20,}$ ]]; then
    echo "[error] TELEGRAM_BOT_TOKEN 格式无效，应类似: 123456789:ABCDEF..."
    exit 1
  fi
  if [[ -n "$ALLOWED_TELEGRAM_USER_IDS" ]] && [[ ! "$ALLOWED_TELEGRAM_USER_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo "[error] ALLOWED_TELEGRAM_USER_IDS 格式错误，应为数字 ID，多个用逗号分隔"
    exit 1
  fi
}

validate_feishu_config() {
  if ! has_feishu_config; then
    return 0
  fi
  if [[ -z "$FEISHU_APP_ID" || -z "$FEISHU_APP_SECRET" ]]; then
    echo "[error] FEISHU_APP_ID 和 FEISHU_APP_SECRET 需要同时配置"
    exit 1
  fi
}

validate_shared_config() {
  if [[ ! -x "$CODEX_BIN" ]]; then
    echo "[error] CODEX_BIN 不存在或不可执行: $CODEX_BIN"
    exit 1
  fi
}

tg_is_running() {
  if [[ -f "$TG_PID_FILE" ]]; then
    local pid
    pid="$(cat "$TG_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    rm -f "$TG_PID_FILE"
  fi
  local existing_pid
  existing_pid="$(pgrep -f "$TG_BOT_SCRIPT" 2>/dev/null | head -n 1 || true)"
  if [[ -n "${existing_pid}" ]]; then
    echo "$existing_pid" >"$TG_PID_FILE"
    return 0
  fi
  return 1
}

tg_start() {
  mkdir -p "$RUNTIME_DIR"

  if tg_is_running; then
    echo "[info] Telegram 已运行，PID=$(cat "$TG_PID_FILE")"
    return 0
  fi

  echo "[info] 启动 Telegram 服务..."
  nohup env \
    TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
    ALLOWED_TELEGRAM_USER_IDS="$ALLOWED_TELEGRAM_USER_IDS" \
    DEFAULT_CWD="$DEFAULT_CWD" \
    CODEX_BIN="$CODEX_BIN" \
    CODEX_SESSION_ROOT="$CODEX_SESSION_ROOT" \
    CODEX_SANDBOX_MODE="$CODEX_SANDBOX_MODE" \
    CODEX_APPROVAL_POLICY="$CODEX_APPROVAL_POLICY" \
    CODEX_DANGEROUS_BYPASS="$CODEX_DANGEROUS_BYPASS" \
    STATE_PATH="$TG_STATE_PATH" \
    TELEGRAM_INSECURE_SKIP_VERIFY="$TELEGRAM_INSECURE_SKIP_VERIFY" \
    TELEGRAM_CA_BUNDLE="$TELEGRAM_CA_BUNDLE" \
    "$PYTHON_BIN" -u "$TG_BOT_SCRIPT" >>"$TG_LOG_FILE" 2>&1 &

  local pid=$!
  echo "$pid" >"$TG_PID_FILE"
  sleep 1

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[ok] Telegram 已启动，PID=$pid"
    echo "[ok] Telegram 日志: $TG_LOG_FILE"
  else
    rm -f "$TG_PID_FILE"
    echo "[error] Telegram 启动失败，最近日志："
    tail -n 50 "$TG_LOG_FILE" || true
    exit 1
  fi
}

tg_stop() {
  if tg_is_running; then
    local pid
    pid="$(cat "$TG_PID_FILE")"
    kill "$pid" >/dev/null 2>&1 || true
    rm -f "$TG_PID_FILE"
    echo "[ok] Telegram 已停止，PID=$pid"
  else
    echo "[info] Telegram 未运行"
  fi
}

tg_status() {
  if tg_is_running; then
    echo "[ok] Telegram 运行中，PID=$(cat "$TG_PID_FILE")"
  else
    echo "[info] Telegram 未运行"
  fi
}

feishu_start() {
  if [[ ! -x "$FEISHU_RUN_SCRIPT" ]]; then
    echo "[error] 找不到飞书启动脚本: $FEISHU_RUN_SCRIPT"
    exit 1
  fi
  echo "[info] 启动飞书服务..."
  "$FEISHU_RUN_SCRIPT" start
}

feishu_stop() {
  if [[ -x "$FEISHU_RUN_SCRIPT" ]]; then
    "$FEISHU_RUN_SCRIPT" stop
  else
    echo "[info] 飞书脚本不存在，跳过停止"
  fi
}

feishu_status() {
  if [[ -x "$FEISHU_RUN_SCRIPT" ]]; then
    "$FEISHU_RUN_SCRIPT" status
  else
    echo "[info] 飞书脚本不存在"
  fi
}

start() {
  validate_tg_config
  validate_feishu_config
  validate_shared_config

  if ! has_tg_config && ! has_feishu_config; then
    echo "[error] 未检测到可启动渠道。"
    echo "请至少配置一组："
    echo "  1) TELEGRAM_BOT_TOKEN"
    echo "  2) FEISHU_APP_ID + FEISHU_APP_SECRET"
    exit 1
  fi

  if has_tg_config; then
    tg_start
  else
    echo "[info] 未配置 TELEGRAM_BOT_TOKEN，跳过 Telegram"
  fi

  if has_feishu_config; then
    feishu_start
  else
    echo "[info] 未配置 FEISHU_APP_ID/FEISHU_APP_SECRET，跳过飞书"
  fi
}

stop() {
  tg_stop
  feishu_stop
}

status() {
  tg_status
  feishu_status
}

logs() {
  mkdir -p "$RUNTIME_DIR"
  touch "$TG_LOG_FILE" "$FEISHU_LOG_FILE"
  tail -f "$TG_LOG_FILE" "$FEISHU_LOG_FILE"
}

restart() {
  stop
  start
}

usage() {
  cat <<EOF
用法: ./run.sh [start|stop|restart|status|logs]
默认: start

行为：
- 配置 TELEGRAM_BOT_TOKEN -> 启动 Telegram
- 配置 FEISHU_APP_ID + FEISHU_APP_SECRET -> 启动飞书
- 两者都配置 -> 两个都启动

示例：
export TELEGRAM_BOT_TOKEN="123456:xxxx"
export ALLOWED_TELEGRAM_USER_IDS="123456789"   # 可选，推荐

export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"

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
