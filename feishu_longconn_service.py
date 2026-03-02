#!/usr/bin/env python3
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import lark_oapi as lark
except ImportError as err:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: lark-oapi\n"
        "Install with: python3 -m pip install --user lark-oapi"
    ) from err

from tg_codex_bot import BotState, CodexRunner, SessionStore, resolve_codex_bin


MAX_FEISHU_TEXT = 2000


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def chunk_text(text: str, size: int = 1800) -> List[str]:
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at > start:
                end = split_at + 1
        chunks.append(text[start:end])
        start = end
    return chunks


def parse_allowed_open_ids(raw: Optional[str]) -> Optional[Set[str]]:
    if not raw:
        return None
    result: Set[str] = set()
    for part in raw.split(","):
        value = part.strip()
        if value:
            result.add(value)
    return result or None


def parse_text_content(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    text = (parsed.get("text") or "").strip()
    if not text:
        return ""
    text = re.sub(r"<at[^>]*>.*?</at>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def adapt_markdown_for_feishu(markdown: str) -> Tuple[str, str]:
    """Convert common markdown syntax to formats better supported by lark_md."""
    if not markdown:
        return "", markdown

    # Some model outputs wrap the whole content in ```markdown ... ```.
    # Unwrap it first so headings/lists can be rendered as markdown instead of code.
    wrapped = markdown.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$", wrapped, flags=re.IGNORECASE)
    if m:
        markdown = m.group(1).strip()

    lines = markdown.splitlines()
    in_code_block = False
    title = ""
    title_found = False
    out: List[str] = []

    for raw in lines:
        line = raw.rstrip("\n")
        striped = line.strip()
        fence = re.match(r"^```[A-Za-z0-9_+-]*\s*$", striped)
        if fence:
            # lark_md is more stable with plain ``` fences than language-tag fences.
            in_code_block = not in_code_block
            out.append("```")
            continue
        if in_code_block:
            out.append(line)
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", striped)
        if m:
            heading_text = m.group(2).strip()
            if heading_text:
                if not title_found and len(m.group(1)) == 1:
                    title = heading_text[:80]
                    title_found = True
                out.append(f"**{heading_text}**")
            continue

        out.append(line)

    body = "\n".join(out).strip()
    return title, body or markdown


class FeishuAPI:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        log_level: str = "INFO",
        rich_message_enabled: bool = True,
    ):
        level = getattr(lark.LogLevel, log_level.upper(), lark.LogLevel.INFO)
        self.client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(level)
            .build()
        )
        self.level = level
        self.rich_message_enabled = rich_message_enabled

    def send_message(self, chat_id: str, text: str) -> bool:
        ok = True
        for part in chunk_text(text, size=min(1800, MAX_FEISHU_TEXT)):
            sent = self._send_text(receive_id_type="chat_id", receive_id=chat_id, text=part)
            ok = ok and sent
        return ok

    def send_agent_message(self, chat_id: str, text: str, title: str = "") -> bool:
        if not self.rich_message_enabled:
            return self.send_message(chat_id, text)
        adapted_title, adapted_text = adapt_markdown_for_feishu(text)
        final_title = adapted_title or title
        parts = chunk_text(adapted_text, size=3200)
        total = len(parts)
        ok = True
        for i, part in enumerate(parts, start=1):
            chunk_title = final_title if total == 1 else (
                f"{final_title} ({i}/{total})" if final_title else ""
            )
            sent = self._send_interactive_markdown(
                receive_id_type="chat_id",
                receive_id=chat_id,
                title=chunk_title,
                markdown=part,
            )
            ok = ok and sent
        return ok

    def send_message_to_open_id(self, open_id: str, text: str) -> bool:
        ok = True
        for part in chunk_text(text, size=min(1800, MAX_FEISHU_TEXT)):
            sent = self._send_text(receive_id_type="open_id", receive_id=open_id, text=part)
            ok = ok and sent
        return ok

    def _send_text(self, receive_id_type: str, receive_id: str, text: str) -> bool:
        request = (
            lark.im.v1.CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                lark.im.v1.CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self.client.im.v1.message.create(request)
        if response.success():
            return True
        log(
            "send failed: "
            f"code={response.code} msg={response.msg} "
            f"log_id={response.get_log_id()} receive_id_type={receive_id_type}"
        )
        return False

    def _send_interactive_markdown(
        self,
        receive_id_type: str,
        receive_id: str,
        title: str,
        markdown: str,
    ) -> bool:
        card = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": markdown},
                }
            ],
        }
        if title:
            card["header"] = {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title},
            }
        request = (
            lark.im.v1.CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                lark.im.v1.CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("interactive")
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self.client.im.v1.message.create(request)
        if response.success():
            return True
        log(
            "send failed: "
            f"code={response.code} msg={response.msg} "
            f"log_id={response.get_log_id()} receive_id_type={receive_id_type} "
            "msg_type=interactive"
        )
        return False


class FeishuCodexService:
    def __init__(
        self,
        api: FeishuAPI,
        sessions: SessionStore,
        state: BotState,
        codex: CodexRunner,
        default_cwd: Path,
        app_id: str,
        app_secret: str,
        allowed_open_ids: Optional[Set[str]],
        enable_p2p: bool,
    ):
        self.api = api
        self.sessions = sessions
        self.state = state
        self.codex = codex
        self.default_cwd = default_cwd
        self.allowed_open_ids = allowed_open_ids
        self.enable_p2p = enable_p2p
        self.seen_event_ids: Set[str] = set()
        self.seen_message_ids: Set[str] = set()
        self.event_handler = (
            lark.EventDispatcherHandler.builder("", "", api.level)
            .register_p2_im_message_receive_v1(self._on_message_receive)
            .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(self._on_ignored_event)
            .register_p2_im_chat_member_bot_added_v1(self._on_ignored_event)
            .register_p2_im_chat_member_bot_deleted_v1(self._on_ignored_event)
            .register_p2_customized_event("im.message.message_read_v1", self._on_custom_ignored_event)
            .build()
        )
        self.ws_client = lark.ws.Client(
            app_id,
            app_secret,
            log_level=api.level,
            event_handler=self.event_handler,
        )

    def run_forever(self) -> None:
        log("feishu long connection service started")
        self.ws_client.start()

    def _on_ignored_event(self, data: Any) -> None:
        header = getattr(data, "header", None)
        event_type = getattr(header, "event_type", "unknown")
        event_id = getattr(header, "event_id", "")
        log(f"event ignored: {event_type} id={event_id}")

    def _on_custom_ignored_event(self, data: Any) -> None:
        header = getattr(data, "header", None)
        event_type = getattr(header, "event_type", "unknown")
        event_id = getattr(header, "event_id", "")
        log(f"event ignored(custom): {event_type} id={event_id}")

    def _on_message_receive(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        header = data.header
        event_id = getattr(header, "event_id", "")
        if event_id:
            if event_id in self.seen_event_ids:
                return
            self.seen_event_ids.add(event_id)
            if len(self.seen_event_ids) > 5000:
                self.seen_event_ids.clear()

        event = data.event
        if not event or not event.message:
            return
        msg = event.message
        if msg.message_type != "text":
            return
        message_id = (msg.message_id or "").strip()
        if message_id:
            if message_id in self.seen_message_ids:
                log(f"duplicate message dropped: message_id={message_id}")
                return
            self.seen_message_ids.add(message_id)
            if len(self.seen_message_ids) > 10000:
                self.seen_message_ids.clear()

        sender = event.sender
        if sender and sender.sender_type == "app":
            return

        sender_open_id = ""
        sender_user_id = ""
        if sender and sender.sender_id:
            sender_open_id = (sender.sender_id.open_id or "").strip()
            sender_user_id = (sender.sender_id.user_id or "").strip()
        actor_id = sender_open_id or sender_user_id
        if not actor_id:
            return

        chat_id = (msg.chat_id or "").strip()
        chat_type = (msg.chat_type or "").strip().lower()
        if not chat_id:
            return

        if self.allowed_open_ids is not None and sender_open_id not in self.allowed_open_ids:
            self.api.send_message(chat_id, "没有权限使用这个 bot。")
            return

        text = parse_text_content(msg.content)
        if not text:
            return

        if chat_type == "p2p" and not self.enable_p2p:
            self.api.send_message(chat_id, "当前未启用私聊，请在群里 @机器人 使用。")
            return

        log(
            "message received: "
            f"actor={actor_id} chat_id={chat_id} chat_type={chat_type} text={text[:80]!r}"
        )
        self._handle_text(chat_id, actor_id, text)

    def _handle_text(self, chat_id: str, actor_id: str, text: str) -> None:
        if not text.startswith("/"):
            if self._try_handle_quick_session_pick(chat_id, actor_id, text):
                return
            self.state.set_pending_session_pick(actor_id, False)  # type: ignore[arg-type]
            self._run_prompt(chat_id, actor_id, text)
            return

        cmd, arg = self._parse_command(text)
        if cmd in ("start", "help"):
            self._send_help(chat_id)
            return
        if cmd == "sessions":
            self._handle_sessions(chat_id, actor_id, arg)
            return
        if cmd == "use":
            self._handle_use(chat_id, actor_id, arg)
            return
        if cmd == "status":
            self._handle_status(chat_id, actor_id)
            return
        if cmd == "new":
            self._handle_new(chat_id, actor_id, arg)
            return
        if cmd == "history":
            self._handle_history(chat_id, actor_id, arg)
            return
        if cmd == "ask":
            self._handle_ask(chat_id, actor_id, arg)
            return
        self.api.send_message(chat_id, f"未知命令: /{cmd}\n发送 /help 查看说明。")

    @staticmethod
    def _parse_command(text: str) -> Tuple[str, str]:
        parts = text.split(" ", 1)
        cmd = parts[0][1:]
        cmd = cmd.split("@", 1)[0].strip().lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        return cmd, arg

    def _send_help(self, chat_id: str) -> None:
        self.api.send_message(
            chat_id,
            "\n".join(
                [
                    "可用命令:",
                    "/sessions [N] - 查看最近 N 条会话（标题 + 编号）",
                    "/use <编号|session_id> - 切换当前会话",
                    "/history [编号|session_id] [N] - 查看会话最近 N 条消息",
                    "/new [cwd] - 进入新会话模式（下一条普通消息会新建 session）",
                    "/status - 查看当前绑定会话",
                    "/ask <内容> - 手动提问（可选）",
                    "执行 /sessions 后，可直接发送编号切换会话",
                    "直接发普通消息即可对话（会自动续聊当前 session）",
                ]
            ),
        )

    def _handle_sessions(self, chat_id: str, actor_id: str, arg: str) -> None:
        limit = 10
        if arg:
            try:
                limit = max(1, min(30, int(arg)))
            except ValueError:
                self.api.send_message(chat_id, "参数错误，示例: /sessions 10")
                return
        items = self.sessions.list_recent(limit=limit)
        if not items:
            self.api.send_message(chat_id, "未找到本地会话记录。")
            return
        lines = ["最近会话（用 /use 编号 切换）:"]
        session_ids = [s.session_id for s in items]
        for i, s in enumerate(items, start=1):
            short_id = s.session_id[:8]
            cwd_name = Path(s.cwd).name or s.cwd
            lines.append(f"{i}. {s.title} | {short_id} | {cwd_name}")
        lines.append("直接发送编号即可切换（例如发送: 1）")
        self.api.send_message(chat_id, "\n".join(lines))
        self.state.set_last_session_ids(actor_id, session_ids)  # type: ignore[arg-type]
        self.state.set_pending_session_pick(actor_id, True)  # type: ignore[arg-type]

    def _handle_use(self, chat_id: str, actor_id: str, arg: str) -> None:
        selector = arg.strip()
        if not selector:
            self.api.send_message(chat_id, "示例: /use 1 或 /use <session_id>")
            return
        session_id, err = self._resolve_session_selector(actor_id, selector)
        if err:
            self.api.send_message(chat_id, err)
            return
        if not session_id:
            self.api.send_message(chat_id, "无效的会话选择参数。")
            return
        self._switch_to_session(chat_id, actor_id, session_id)

    def _switch_to_session(self, chat_id: str, actor_id: str, session_id: str) -> None:
        meta = self.sessions.find_by_id(session_id)
        if not meta:
            self.api.send_message(chat_id, f"未找到 session: {session_id}")
            return
        self.state.set_active_session(actor_id, meta.session_id, meta.cwd)  # type: ignore[arg-type]
        self.state.set_pending_session_pick(actor_id, False)  # type: ignore[arg-type]
        self.api.send_message(
            chat_id,
            f"已切换到:\n{meta.title}\nsession: {meta.session_id}\ncwd: {meta.cwd}\n现在可直接发消息对话。",
        )

    def _try_handle_quick_session_pick(self, chat_id: str, actor_id: str, text: str) -> bool:
        if not self.state.is_pending_session_pick(actor_id):  # type: ignore[arg-type]
            return False
        raw = text.strip()
        if not raw.isdigit():
            return False
        idx = int(raw)
        recent_ids = self.state.get_last_session_ids(actor_id)  # type: ignore[arg-type]
        if idx <= 0 or idx > len(recent_ids):
            self.api.send_message(chat_id, "编号无效。请发送 /sessions 重新查看列表。")
            return True
        self._switch_to_session(chat_id, actor_id, recent_ids[idx - 1])
        return True

    def _handle_history(self, chat_id: str, actor_id: str, arg: str) -> None:
        tokens = [x for x in arg.split() if x]
        limit = 10
        session_id: Optional[str] = None

        if not tokens:
            session_id, _ = self.state.get_active(actor_id)  # type: ignore[arg-type]
            if not session_id:
                self.api.send_message(
                    chat_id,
                    "当前无 active session。先 /use 选择会话，或直接对话后再查看历史。",
                )
                return
        else:
            session_id, err = self._resolve_session_selector(actor_id, tokens[0])
            if err:
                self.api.send_message(chat_id, err)
                return
            if not session_id:
                self.api.send_message(chat_id, "无效的会话选择参数。")
                return
            if len(tokens) >= 2:
                try:
                    limit = int(tokens[1])
                except ValueError:
                    self.api.send_message(chat_id, "N 必须是数字，示例: /history 1 20")
                    return

        limit = max(1, min(50, limit))
        meta, messages = self.sessions.get_history(session_id, limit=limit)
        if not meta:
            self.api.send_message(chat_id, f"未找到 session: {session_id}")
            return
        if not messages:
            self.api.send_message(chat_id, "该会话暂无可展示历史消息。")
            return

        lines = [
            f"会话历史: {meta.title}",
            f"session: {meta.session_id}",
            f"显示最近 {len(messages)} 条消息:",
        ]
        for i, (role, message) in enumerate(messages, start=1):
            role_zh = "用户" if role == "user" else "助手"
            lines.append(f"{i}. [{role_zh}] {SessionStore.compact_message(message)}")
        self.api.send_message(chat_id, "\n".join(lines))

    def _resolve_session_selector(self, actor_id: str, selector: str) -> Tuple[Optional[str], Optional[str]]:
        raw = selector.strip()
        if not raw:
            return None, "示例: /use 1 或 /use <session_id>"
        if raw.isdigit():
            idx = int(raw)
            recent_ids = self.state.get_last_session_ids(actor_id)  # type: ignore[arg-type]
            if idx <= 0 or idx > len(recent_ids):
                return None, "编号无效。先执行 /sessions，再用编号。"
            return recent_ids[idx - 1], None
        return raw, None

    def _handle_status(self, chat_id: str, actor_id: str) -> None:
        session_id, cwd = self.state.get_active(actor_id)  # type: ignore[arg-type]
        if not session_id:
            self.api.send_message(
                chat_id,
                "当前没有绑定会话。可先 /sessions + /use，或 /new 后直接发消息。",
            )
            return
        title = f"session {session_id[:8]}"
        meta = self.sessions.find_by_id(session_id)
        if meta:
            title = meta.title
        self.api.send_message(
            chat_id,
            f"当前会话:\n{title}\nsession: {session_id}\ncwd: {cwd or str(self.default_cwd)}\n支持与本地 Codex 客户端交替续聊。",
        )

    def _handle_ask(self, chat_id: str, actor_id: str, arg: str) -> None:
        prompt = arg.strip()
        if not prompt:
            self.api.send_message(chat_id, "示例: /ask 帮我总结当前仓库结构")
            return
        self._run_prompt(chat_id, actor_id, prompt)

    def _handle_new(self, chat_id: str, actor_id: str, arg: str) -> None:
        cwd_raw = arg.strip()
        _, current_cwd = self.state.get_active(actor_id)  # type: ignore[arg-type]
        target_cwd = Path(current_cwd).expanduser() if current_cwd else self.default_cwd
        if cwd_raw:
            candidate = Path(cwd_raw).expanduser()
            if not candidate.exists() or not candidate.is_dir():
                self.api.send_message(chat_id, f"cwd 不存在或不是目录: {candidate}")
                return
            target_cwd = candidate
        self.state.clear_active_session(actor_id, str(target_cwd))  # type: ignore[arg-type]
        self.state.set_pending_session_pick(actor_id, False)  # type: ignore[arg-type]
        self.api.send_message(
            chat_id,
            f"已进入新会话模式，cwd: {target_cwd}\n下一条普通消息会创建一个新 session。",
        )

    def _run_prompt(self, chat_id: str, actor_id: str, prompt: str) -> None:
        active_id, active_cwd = self.state.get_active(actor_id)  # type: ignore[arg-type]
        cwd = Path(active_cwd).expanduser() if active_cwd else self.default_cwd
        if not cwd.exists():
            cwd = self.default_cwd

        mode = "继续当前会话" if active_id else "新建会话"
        log(f"run prompt: actor={actor_id} mode={mode} cwd={cwd} session={active_id}")
        try:
            thread_id, answer, stderr_text, return_code = self.codex.run_prompt(
                prompt=prompt,
                cwd=cwd,
                session_id=active_id,
            )
        except Exception as e:
            self.api.send_message(chat_id, f"调用 Codex 时出现异常: {e}")
            return

        if thread_id:
            self.state.set_active_session(actor_id, thread_id, str(cwd))  # type: ignore[arg-type]

        if return_code != 0:
            msg = f"Codex 执行失败 (exit={return_code})\n{answer}"
            if stderr_text:
                msg += f"\n\nstderr:\n{stderr_text[-1200:]}"
            self.api.send_message(chat_id, msg)
            return

        self.api.send_agent_message(chat_id, answer)


def build_service() -> FeishuCodexService:
    app_id = env("FEISHU_APP_ID")
    app_secret = env("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("missing FEISHU_APP_ID or FEISHU_APP_SECRET")

    allowed_open_ids = parse_allowed_open_ids(env("ALLOWED_FEISHU_OPEN_IDS"))
    session_root = Path(env("CODEX_SESSION_ROOT", "~/.codex/sessions")).expanduser()
    state_path = Path(env("STATE_PATH", "./feishu_bot_state.json"))
    codex_bin = resolve_codex_bin(env("CODEX_BIN"))
    codex_sandbox_mode = env("CODEX_SANDBOX_MODE")
    codex_approval_policy = env("CODEX_APPROVAL_POLICY")
    codex_dangerous_bypass = env("CODEX_DANGEROUS_BYPASS", "0") == "1"
    default_cwd = Path(env("DEFAULT_CWD", os.getcwd())).expanduser()
    enable_p2p = env("FEISHU_ENABLE_P2P", "0") == "1"
    log_level = env("FEISHU_LOG_LEVEL", "INFO") or "INFO"
    rich_message_enabled = env("FEISHU_RICH_MESSAGE", "1") == "1"

    api = FeishuAPI(
        app_id=app_id,
        app_secret=app_secret,
        log_level=log_level,
        rich_message_enabled=rich_message_enabled,
    )
    sessions = SessionStore(session_root)
    state = BotState(state_path)
    codex = CodexRunner(
        codex_bin=codex_bin,
        sandbox_mode=codex_sandbox_mode,
        approval_policy=codex_approval_policy,
        dangerous_bypass=codex_dangerous_bypass,
    )
    if codex_dangerous_bypass:
        log("[warn] CODEX_DANGEROUS_BYPASS=1, approvals and sandbox are fully bypassed")

    return FeishuCodexService(
        api=api,
        sessions=sessions,
        state=state,
        codex=codex,
        default_cwd=default_cwd,
        app_id=app_id,
        app_secret=app_secret,
        allowed_open_ids=allowed_open_ids,
        enable_p2p=enable_p2p,
    )


def main() -> None:
    service = build_service()
    service.run_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as err:
        log(f"fatal error: {err}")
        sys.exit(1)
