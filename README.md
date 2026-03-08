# tg-codex

Language: English | [简体中文](README.zh-CN.md)

`tg-codex` lets you run and continue local `codex` sessions from chat apps. It supports Telegram and Feishu (long connection).

## Features

- List local session history with titles
- Switch to an existing session and continue asking
- Keep receiving commands while a session is running, and switch to another thread
- Create new sessions and control working directory
- View recent messages in a session (`/history`)
- Optionally transcribe Telegram voice/audio messages into text before continuing the session
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
export TG_STREAM_ENABLED=1                            # optional, default 1 (streaming reply edits)
export TG_STREAM_EDIT_INTERVAL_MS=300                # optional, stream edit throttle interval in ms
export TG_STREAM_MIN_DELTA_CHARS=8                    # optional, skip refresh if change is too small
export TG_THINKING_STATUS_INTERVAL_MS=700             # optional, thinking status refresh interval in ms
export TG_VOICE_TRANSCRIBE_ENABLED=1                  # optional; if unset, run.sh auto-enables when local env is ready
export TG_VOICE_TRANSCRIBE_BACKEND="local-whisper"    # optional, default local-whisper
export TG_VOICE_MAX_BYTES=26214400                    # optional, max Telegram audio bytes to transcribe

# Local Whisper backend (no external API)
export TG_VOICE_LOCAL_MODEL="base"                    # optional
export TG_VOICE_LOCAL_DEVICE="cpu"                    # optional: cpu | cuda | mps
export TG_VOICE_LOCAL_LANGUAGE="zh"                   # optional
export TG_VOICE_FFMPEG_BIN="/opt/homebrew/bin/ffmpeg" # optional, auto-detected if omitted

# OpenAI backend (optional fallback)
export OPENAI_API_KEY="sk-..."                        # required only when backend=openai
export OPENAI_BASE_URL="https://api.openai.com/v1"    # optional
export TG_VOICE_TRANSCRIBE_MODEL="gpt-4o-mini-transcribe"  # optional for backend=openai
export TG_VOICE_TRANSCRIBE_TIMEOUT_SEC=180            # optional

# Feishu (optional)
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"

# Shared (optional)
export DEFAULT_CWD="/path/to/your/project/codex-tg"
export CODEX_BIN="/Applications/Codex.app/Contents/Resources/codex"
export CODEX_SESSION_ROOT="$HOME/.codex/sessions"
export CODEX_SANDBOX_MODE=""                         # optional: used only when CODEX_DANGEROUS_BYPASS=1
export CODEX_APPROVAL_POLICY=""                      # optional: used only when CODEX_DANGEROUS_BYPASS=1
export CODEX_DANGEROUS_BYPASS=0                      # 0/1/2 (see permission section below)
export CODEX_IDLE_TIMEOUT_SEC=3600                  # optional: kill codex exec after this many idle seconds with no output; 0 disables it
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

Permission behavior is controlled by `CODEX_DANGEROUS_BYPASS`:

- `0` (default): no extra permission flags (least privilege)
- `1`: enable permission flags
  - `CODEX_SANDBOX_MODE` defaults to `danger-full-access` (override allowed)
  - `CODEX_APPROVAL_POLICY` defaults to `never` (override allowed)
- `2`: append `--dangerously-bypass-approvals-and-sandbox`

Notes:
- `CODEX_SANDBOX_MODE` / `CODEX_APPROVAL_POLICY` are applied only when `CODEX_DANGEROUS_BYPASS=1`
- `CODEX_DANGEROUS_BYPASS=2` takes full bypass path

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

## Telegram Voice Messages

Telegram voice and audio messages can be transcribed and then sent into the current Codex session as text.

Notes:

- `local-whisper` does not call an external API; it uses local `whisper` plus `ffmpeg`
- `run.sh` now probes the local environment on startup: if local Whisper is ready, it auto-enables Telegram voice transcription by default
- If local dependencies are missing, `run.sh` prints install commands and leaves voice transcription disabled by default
- This is currently Telegram-only; Feishu still handles text messages only
- Captions on Telegram audio messages are appended as extra context before the transcript
- If transcription is not configured, the bot will reply with a clear hint instead of silently ignoring the message
- Send normal text directly: continue current session, or create one if in new-session mode

Tips:

- After `/sessions`, send an index directly (for example `1`) to switch
- During long-running tasks, you can still send `/use`, `/sessions`, and `/status`
- In Feishu group chats, it is recommended to `@bot` before sending commands

## Additional Scripts

- `tg_codex_bot.py`: Telegram service entry
- `feishu_longconn_service.py`: Feishu long-connection service entry
- `run_feishu.sh`: Feishu-only process management script

## Known Limitations

- New sessions are mainly visible in terminal/CLI session history
- Codex Desktop may need restart before newly continued sessions become visible
- Only one in-flight task is allowed per session; switch to another thread for parallel work
