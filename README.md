# tg-codex

Language: English | [简体中文](README.zh-CN.md)

`tg-codex` lets you run and continue local `codex` sessions from chat apps. It supports Telegram and Feishu (long connection).

## Features

- List local session history with titles
- Switch to an existing session and continue asking
- Create new sessions and control working directory
- View recent messages in a session (`/history`)
- Run Telegram only, Feishu only, or both at the same time

## Requirements

- Python 3.9+
- Local `codex` installed and already logged in
- Channel credentials (as needed)
  - Telegram: `TELEGRAM_BOT_TOKEN`
  - Feishu: `FEISHU_APP_ID` + `FEISHU_APP_SECRET`

## Quick Start

### 1) Configure environment variables (as needed)

```bash
# Telegram (optional)
export TELEGRAM_BOT_TOKEN="your bot token"
export ALLOWED_TELEGRAM_USER_IDS="123456789"         # optional, recommended

# Feishu (optional)
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"

# Shared (optional)
export DEFAULT_CWD="/path/to/your/project/codex-tg"
export CODEX_BIN="/Applications/Codex.app/Contents/Resources/codex"
export CODEX_SESSION_ROOT="$HOME/.codex/sessions"
export CODEX_SANDBOX_MODE="danger-full-access"       # elevated by default
export CODEX_APPROVAL_POLICY="never"                 # no approval prompts by default
export CODEX_DANGEROUS_BYPASS=0                      # set 1 to bypass both approval and sandbox (VERY HIGH RISK)
```

### 2) Start services

```bash
./run.sh start
```

`run.sh` startup behavior:

- `TELEGRAM_BOT_TOKEN` configured: starts Telegram
- `FEISHU_APP_ID` + `FEISHU_APP_SECRET` configured: starts Feishu
- both configured: starts both channels

Common commands:

```bash
./run.sh stop
./run.sh status
./run.sh logs
./run.sh restart
```

## Feishu Setup

Feishu uses official SDK long connection mode (no public callback URL required).

### Feishu app requirements

- Enable Bot capability
- Subscribe to event: `im.message.receive_v1`
- Publish and install the app in your tenant

### Optional Feishu env vars

```bash
export ALLOWED_FEISHU_OPEN_IDS="ou_xxx,ou_yyy"   # optional open_id allowlist
export FEISHU_ENABLE_P2P=1                         # default 1 (DM enabled), set 0 for group-only
export FEISHU_LOG_LEVEL="INFO"                  # DEBUG/INFO/WARN/ERROR
export FEISHU_RICH_MESSAGE=1                       # default 1, render replies as rich cards
```

Notes:

- With `FEISHU_RICH_MESSAGE=1`, replies are sent as card markdown (titles/lists/code blocks)
- To manage Feishu only, use `./run_feishu.sh start|stop|status|logs|restart`

## Permission Switches & Risks

The service passes these env vars to `codex exec`:

- `CODEX_SANDBOX_MODE` (default: `danger-full-access`)
- `CODEX_APPROVAL_POLICY` (default: `never`)
- `CODEX_DANGEROUS_BYPASS` (default: `0`)

When `CODEX_DANGEROUS_BYPASS=1`, it adds `--dangerously-bypass-approvals-and-sandbox`, which disables both approval and sandbox protections.

Risk notes:

- It may execute arbitrary commands and modify/delete local files
- It may read and exfiltrate sensitive data (keys, configs, source code)
- Enable only in controlled environments and switch back to `0` afterward

## Commands (Telegram / Feishu)

- `/help`
- `/sessions [N]`: list recent `N` sessions (title + index)
- `/use <index|session_id>`: switch active session
- `/history [index|session_id] [N]`: show latest `N` messages (default 10, max 50)
- `/new [cwd]`: enter new-session mode; next normal message creates a new session
- `/status`: show current active session
- `/ask <text>`: ask in the current session
- Send normal text directly: continue current session, or create one if in new-session mode

Tips:

- After `/sessions`, send an index directly (for example `1`) to switch
- In Feishu group chats, it is recommended to `@bot` before sending commands

## Additional Scripts

- `tg_codex_bot.py`: Telegram service entry
- `feishu_longconn_service.py`: Feishu long-connection service entry
- `run_feishu.sh`: Feishu-only process management script

## Known Limitations

- New sessions are mainly visible in terminal/CLI session history
- Codex Desktop may need restart before newly continued sessions become visible
- Replies are returned after each request finishes (no streaming push yet)
