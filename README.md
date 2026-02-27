# tg-codex

`tg-codex` 是一个 Telegram 机器人服务，用于在 Telegram 中远程调用本机 `codex` 会话。

## 功能

- 查看本地历史会话（标题化展示）
- 切换会话并继续追问
- 支持在 Telegram 中创建新会话或续聊已有会话
- 支持查看会话最近消息（`/history`）

## 环境要求

- Python 3.9+
- 本机已安装并可执行 `codex`（且已登录）
- Telegram Bot Token

## 快速开始

### 1) 获取 Telegram Bot Token

1. 在 Telegram 打开 `@BotFather`
2. 发送 `/newbot` 并按提示创建机器人
3. 保存返回的 token（用于 `TELEGRAM_BOT_TOKEN`）

### 2) 获取你的 Telegram User ID

方式 A（推荐）：
1. 在 Telegram 打开 `@userinfobot`
2. 发送任意消息，读取返回的数字 ID

方式 B（Bot API）：
1. 先给你的机器人发送 `/start`
2. 执行：

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
```

3. 在返回 JSON 中查找 `message.from.id`

### 3) 配置环境变量

```bash
export TELEGRAM_BOT_TOKEN="你的 bot token"
export ALLOWED_TELEGRAM_USER_IDS="123456789"          # 建议设置，多个用逗号分隔
export CODEX_SESSION_ROOT="$HOME/.codex/sessions"     # 可选
export STATE_PATH="./.runtime/bot_state.json"         # 可选
export DEFAULT_CWD="/path/to/your/project/codex-tg"   # 可选
export CODEX_BIN="/Applications/Codex.app/Contents/Resources/codex"  # 可选
```

### 4) 启动服务

推荐使用脚本：

```bash
./run.sh start
```

常用命令：

```bash
./run.sh stop
./run.sh status
./run.sh logs
./run.sh restart
```

也可直接运行：

```bash
python3 tg_codex_bot.py
```

## Telegram 命令

- `/help`
- `/sessions [N]`：查看最近 N 条会话（标题 + 编号）
- `/use <编号|session_id>`：切换会话
- `/history [编号|session_id] [N]`：查看会话最近 N 条消息（默认 10，最大 50）
- `/new [cwd]`：进入新会话模式，下一条普通消息会新建会话
- `/status`：查看当前绑定会话
- `/ask <内容>`：在当前会话提问
- 直接发送普通文本：自动续聊当前会话；若处于新会话模式则创建新会话

提示：
- 执行 `/sessions` 后，可直接发送编号（如 `1`）切换会话
- 执行 `/sessions` 后，也可点击返回消息中的“切换”按钮

## 已知限制

- 在 Telegram 侧新创建的会话，通常不会在 Codex 客户端会话列表中直接显示
- 但如果是历史老会话（已在本地客户端存在），通过 Telegram 继续对话后，仍可在客户端显示并续聊

## 说明

- 当前实现基于 Telegram Bot API 长轮询（无 webhook）
- 当前为一次请求结束后回包，未实现流式逐条推送
