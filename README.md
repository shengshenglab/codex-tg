# tg-codex

Language: English | [简体中文](README.zh-CN.md)

`tg-codex` is a Telegram bot service that lets you run and continue local `codex` sessions from Telegram.

## Features

- List local session history with titles
- Switch to an existing session and continue asking
- Create new sessions from Telegram
- View recent messages in a session (`/history`)

## Requirements

- Python 3.9+
- Local `codex` installed and already logged in
- Telegram Bot Token

## Quick Start

### 1) Get a Telegram Bot Token

1. Open `@BotFather` in Telegram
2. Send `/newbot` and follow the prompts
3. Save the returned token for `TELEGRAM_BOT_TOKEN`

### 2) Get Your Telegram User ID

Method A (recommended):
1. Open `@userinfobot`
2. Send any message and copy your numeric user ID

Method B (Bot API):
1. Send `/start` to your bot first
2. Run:

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
```

3. Find `message.from.id` in the JSON response

### 3) Configure Environment Variables

```bash
export TELEGRAM_BOT_TOKEN="your bot token"
export ALLOWED_TELEGRAM_USER_IDS="123456789"         # recommended, comma-separated for multiple users
export CODEX_SESSION_ROOT="$HOME/.codex/sessions"    # optional
export STATE_PATH="./.runtime/bot_state.json"        # optional
export DEFAULT_CWD="/path/to/your/project/codex-tg"  # optional
export CODEX_BIN="/Applications/Codex.app/Contents/Resources/codex"  # optional
```

### 4) Start the Service

Recommended:

```bash
./run.sh start
```

Common commands:

```bash
./run.sh stop
./run.sh status
./run.sh logs
./run.sh restart
```

Or run directly:

```bash
python3 tg_codex_bot.py
```

## Telegram Commands

- `/help`
- `/sessions [N]`: list recent `N` sessions (title + index)
- `/use <index|session_id>`: switch active session
- `/history [index|session_id] [N]`: show the latest `N` messages (default 10, max 50)
- `/new [cwd]`: enter new-session mode; next normal message creates a new session
- `/status`: show current active session
- `/ask <text>`: ask in the current session
- Send normal text directly: continue current session, or create one if in new-session mode

Tips:
- After `/sessions`, you can send an index directly (for example `1`) to switch
- After `/sessions`, you can also use the inline switch buttons

## Known Limitation

- New sessions created from Telegram are mainly visible in terminal/CLI session history
- Codex Desktop client usually needs a restart before newly continued sessions become visible

## Notes

- Uses Telegram Bot API long polling (no webhook)
- Replies are returned after each request finishes (no streaming push yet)
