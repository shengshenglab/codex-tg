#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_PATH="${STATE_PATH:-$SCRIPT_DIR/.runtime/bot_state.json}"
CODEX_BIN_DEFAULT="/Applications/Codex.app/Contents/Resources/codex"
CODEX_BIN="${CODEX_BIN:-$CODEX_BIN_DEFAULT}"

TARGET_USER_ID="${TARGET_USER_ID:-}"
DRY_RUN=0

usage() {
  cat <<'EOF'
用法:
  ./open-current.sh [user_id] [--dry-run]

说明:
  - 从 .runtime/bot_state.json 读取当前 TG active_session_id
  - 直接在对应 cwd 执行 codex resume <session_id> --all
  - --dry-run 只打印，不真正执行
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$TARGET_USER_ID" ]]; then
        TARGET_USER_ID="$arg"
      else
        echo "[error] 参数过多: $arg"
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ ! -f "$STATE_PATH" ]]; then
  echo "[error] 未找到状态文件: $STATE_PATH"
  exit 1
fi

if [[ ! -x "$CODEX_BIN" ]]; then
  if command -v codex >/dev/null 2>&1; then
    CODEX_BIN="$(command -v codex)"
  else
    echo "[error] 找不到 codex 可执行文件，当前: $CODEX_BIN"
    exit 1
  fi
fi

line="$(
python3 - "$STATE_PATH" "$TARGET_USER_ID" <<'PY'
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
target_user = (sys.argv[2] or "").strip()
data = json.loads(state_path.read_text(encoding="utf-8"))
users = data.get("users", {})

if not isinstance(users, dict) or not users:
    print("ERR\t状态文件里没有 users")
    sys.exit(0)

if target_user:
    u = users.get(target_user)
    if not isinstance(u, dict):
        print(f"ERR\t未找到 user_id={target_user}")
        sys.exit(0)
    session_id = u.get("active_session_id")
    cwd = u.get("active_cwd")
    if not session_id:
        print(f"ERR\tuser_id={target_user} 没有 active_session_id")
        sys.exit(0)
    print(f"OK\t{target_user}\t{session_id}\t{cwd or ''}")
    sys.exit(0)

# If only one user, use it.
if len(users) == 1:
    user_id = next(iter(users.keys()))
    u = users[user_id]
    session_id = u.get("active_session_id")
    cwd = u.get("active_cwd")
    if not session_id:
        print(f"ERR\t唯一用户 {user_id} 没有 active_session_id")
        sys.exit(0)
    print(f"OK\t{user_id}\t{session_id}\t{cwd or ''}")
    sys.exit(0)

# Multiple users: pick the one with active session and lexicographically smallest user_id.
candidates = []
for uid, u in users.items():
    if not isinstance(u, dict):
        continue
    sid = u.get("active_session_id")
    if sid:
        candidates.append((str(uid), sid, u.get("active_cwd") or ""))

if not candidates:
    print("ERR\t多个用户都没有 active_session_id，请传 user_id")
    sys.exit(0)

candidates.sort(key=lambda x: x[0])
uid, sid, cwd = candidates[0]
print(f"OK\t{uid}\t{sid}\t{cwd}")
PY
)"

status="${line%%$'\t'*}"
if [[ "$status" != "OK" ]]; then
  echo "[error] ${line#*$'\t'}"
  exit 1
fi

rest="${line#*$'\t'}"
USER_ID="${rest%%$'\t'*}"
rest="${rest#*$'\t'}"
SESSION_ID="${rest%%$'\t'*}"
CWD="${rest#*$'\t'}"

if [[ -z "$CWD" ]] || [[ ! -d "$CWD" ]]; then
  CWD="$SCRIPT_DIR"
fi

echo "[info] user_id=$USER_ID"
echo "[info] session_id=$SESSION_ID"
echo "[info] cwd=$CWD"
echo "[info] command: $CODEX_BIN resume $SESSION_ID --all"

if [[ "$DRY_RUN" -eq 1 ]]; then
  exit 0
fi

cd "$CWD"
exec "$CODEX_BIN" resume "$SESSION_ID" --all
