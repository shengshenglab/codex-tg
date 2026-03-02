# tg-codex

语言: [English](README.md) | 简体中文

`tg-codex` 用于在聊天软件中远程调用本机 `codex` 会话，支持 Telegram 与飞书（长连接）。

## 功能

- 查看本地会话列表（标题化展示）
- 切换会话并继续追问
- 新建会话并设置工作目录
- 查看会话最近消息（`/history`）
- Telegram 与飞书可单独启用，也可同时启用

## 环境要求

- Python 3.9+
- 本机已安装并可执行 `codex`（且已登录）
- 渠道凭据（按需）
  - Telegram: `TELEGRAM_BOT_TOKEN`
  - 飞书: `FEISHU_APP_ID` + `FEISHU_APP_SECRET`

## 快速开始

### 1) 配置环境变量（按需）

```bash
# Telegram（可选）
export TELEGRAM_BOT_TOKEN="你的 bot token"
export ALLOWED_TELEGRAM_USER_IDS="123456789"          # 可选，建议设置，多个用逗号分隔

# 飞书（可选）
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"

# 通用（可选）
export DEFAULT_CWD="/path/to/your/project/codex-tg"
export CODEX_BIN="/Applications/Codex.app/Contents/Resources/codex"
export CODEX_SESSION_ROOT="$HOME/.codex/sessions"
export CODEX_SANDBOX_MODE="danger-full-access"       # 默认已提升权限
export CODEX_APPROVAL_POLICY="never"                 # 默认不询问审批
export CODEX_DANGEROUS_BYPASS=0                      # 设为 1 将完全绕过审批和沙箱（极高风险）
```

### 2) 启动服务

```bash
./run.sh start
```

`run.sh` 启动策略：

- 配置 `TELEGRAM_BOT_TOKEN`：启动 Telegram 渠道
- 配置 `FEISHU_APP_ID + FEISHU_APP_SECRET`：启动飞书渠道
- 两组都配置：两个渠道都启动

常用命令：

```bash
./run.sh stop
./run.sh status
./run.sh logs
./run.sh restart
```

## 飞书配置说明

飞书渠道使用官方 SDK 长连接接收事件（不需要公网回调 URL）。

### 飞书应用侧要求

- 开启机器人能力
- 订阅事件：`im.message.receive_v1`
- 发布版本并安装应用到企业

### 飞书可选环境变量

```bash
export ALLOWED_FEISHU_OPEN_IDS="ou_xxx,ou_yyy"  # 可选，飞书用户白名单（open_id）
export FEISHU_ENABLE_P2P=1                        # 默认 1，启用私聊；设为 0 仅群聊
export FEISHU_LOG_LEVEL="INFO"                  # DEBUG/INFO/WARN/ERROR
export FEISHU_RICH_MESSAGE=1                      # 默认 1，助手回复使用富文本卡片
```

说明：

- `FEISHU_RICH_MESSAGE=1` 时，回复使用飞书卡片 Markdown（标题、列表、代码块）
- 若需仅管理飞书渠道，可用：`./run_feishu.sh start|stop|status|logs|restart`

## 权限开关与风险

服务会把以下环境变量透传给 `codex exec`：

- `CODEX_SANDBOX_MODE`：默认 `danger-full-access`
- `CODEX_APPROVAL_POLICY`：默认 `never`
- `CODEX_DANGEROUS_BYPASS`：默认 `0`

当 `CODEX_DANGEROUS_BYPASS=1` 时，会追加参数 `--dangerously-bypass-approvals-and-sandbox`，这会完全跳过审批与沙箱保护。

风险说明：

- 可能执行任意命令并修改/删除本机文件
- 可能读取并外发敏感数据（如密钥、配置、源码）
- 建议仅在受控环境中临时开启，使用后立即恢复为 `0`

## 命令列表（Telegram / 飞书）

- `/help`
- `/sessions [N]`：查看最近 `N` 条会话（标题 + 编号）
- `/use <编号|session_id>`：切换当前会话
- `/history [编号|session_id] [N]`：查看最近 `N` 条消息（默认 10，最大 50）
- `/new [cwd]`：进入新会话模式，下一条普通消息会新建会话
- `/status`：查看当前绑定会话
- `/ask <内容>`：在当前会话提问
- 直接发送普通文本：自动续聊当前会话；若处于新会话模式则创建新会话

提示：

- `/sessions` 后可直接发送编号（如 `1`）切换会话
- 飞书群聊中建议 `@机器人` 后发送命令

## 其他脚本

- `tg_codex_bot.py`：Telegram 服务主程序
- `feishu_longconn_service.py`：飞书长连接服务主程序
- `run_feishu.sh`：仅管理飞书渠道的启动脚本

## 已知限制

- 新建会话主要在终端/CLI 会话历史中可见
- Codex Desktop 可能需要重启后才会显示新续聊会话
- 当前为一次请求结束后回包，暂未实现流式推送
