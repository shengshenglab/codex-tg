# tg-codex (MVP)

一个最小可运行的 Telegram 机器人服务，用来远程调用本机 `codex`，支持：
- 查看本机历史会话（标题化显示）
- 切换会话
- 在当前会话继续提问（可直接发普通消息）

## 1. 环境要求

- Python 3.9+
- 本机可执行 `codex`（已登录）
- Telegram Bot Token

## 2. 配置环境变量

```bash
export TELEGRAM_BOT_TOKEN="你的 bot token"
export ALLOWED_TELEGRAM_USER_IDS="123456789"   # 可选，逗号分隔
export CODEX_SESSION_ROOT="$HOME/.codex/sessions"  # 可选
export STATE_PATH="./bot_state.json"                # 可选
export DEFAULT_CWD="/path/to/your/project/codex-tg" # 可选（示例占位：当前仓库目录）
```

说明：
- `ALLOWED_TELEGRAM_USER_IDS` 不设置时，任何人都可与 bot 交互，不建议公网使用。

## 3. 启动

```bash
python3 tg_codex_bot.py
```

## 4. Telegram 命令

- `/help`
- `/sessions [N]`：查看最近 N 条 session（标题 + 编号）
- `/use <编号|session_id>`：切换到指定 session
- `/new [cwd]`：进入新会话模式，下一条普通消息会新建 session
- `/status`：查看当前绑定会话
- `/ask <内容>`：在当前会话提问；若未绑定会话，会自动创建新会话
- 直接发送普通文本：自动续聊当前会话；若当前是新会话模式则自动创建会话

说明：
- Telegram 与本地 Codex 客户端使用同一个 session id，可交替续聊同一会话。

## 5. 当前实现边界（MVP）

- 使用 Telegram Bot API 长轮询（无 webhook）
- 调用 `codex exec` / `codex exec resume --json`
- 未实现多任务队列和流式消息逐条推送（当前为一次请求结束后回包）
