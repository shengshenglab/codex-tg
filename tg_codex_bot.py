#!/usr/bin/env python3
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


MAX_TELEGRAM_TEXT = 4096
BOT_COMMANDS: List[Dict[str, str]] = [
    {"command": "start", "description": "开始使用"},
    {"command": "help", "description": "查看帮助"},
    {"command": "sessions", "description": "查看最近会话"},
    {"command": "use", "description": "切换会话"},
    {"command": "history", "description": "查看会话历史"},
    {"command": "new", "description": "新建会话模式"},
    {"command": "status", "description": "查看当前会话"},
    {"command": "ask", "description": "在当前会话提问"},
]


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def chunk_text(text: str, size: int = 3800) -> List[str]:
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


def parse_allowed_user_ids(raw: Optional[str]) -> Optional[Set[int]]:
    if not raw:
        return None
    result: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError:
            raise ValueError(f"invalid user id in ALLOWED_TELEGRAM_USER_IDS: {part}")
    return result


def parse_dangerous_bypass_level(raw: Optional[str]) -> int:
    value = (raw or "0").strip()
    if not value:
        return 0
    try:
        level = int(value)
    except ValueError:
        raise ValueError("CODEX_DANGEROUS_BYPASS must be 0, 1, or 2")
    if level < 0:
        level = 0
    if level > 2:
        level = 2
    return level


class TelegramAPI:
    def __init__(
        self,
        token: str,
        ca_bundle: Optional[str] = None,
        insecure_skip_verify: bool = False,
    ):
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.ssl_context: Optional[ssl.SSLContext] = None
        if insecure_skip_verify:
            self.ssl_context = ssl._create_unverified_context()
        elif ca_bundle:
            self.ssl_context = ssl.create_default_context(cafile=ca_bundle)

    def _request(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=80, context=self.ssl_context) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        if not parsed.get("ok"):
            raise RuntimeError(f"telegram api error for {method}: {raw}")
        return parsed["result"]

    def get_updates(self, offset: Optional[int], timeout: int = 30) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        return self._request("getUpdates", payload)

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: Optional[int] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_to is not None:
            payload["reply_to_message_id"] = reply_to
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        for part in chunk_text(text, size=min(3800, MAX_TELEGRAM_TEXT)):
            payload["text"] = part
            self._request("sendMessage", payload)

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self._request("sendChatAction", {"chat_id": chat_id, "action": action})

    def set_my_commands(self, commands: List[Dict[str, str]]) -> None:
        self._request("setMyCommands", {"commands": commands})

    def set_chat_menu_button_commands(self) -> None:
        self._request("setChatMenuButton", {"menu_button": {"type": "commands"}})

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> None:
        payload: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text
        self._request("answerCallbackQuery", payload)


@dataclass
class SessionMeta:
    session_id: str
    timestamp: str
    cwd: str
    file_path: str
    title: str


class TypingStatus:
    def __init__(self, api: TelegramAPI, chat_id: int, interval_sec: float = 4.0):
        self.api = api
        self.chat_id = chat_id
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.api.send_chat_action(self.chat_id, "typing")
            except Exception:
                pass
            self._stop_event.wait(self.interval_sec)


class SessionStore:
    def __init__(self, root: Path):
        self.root = root.expanduser()

    def list_recent(self, limit: int = 10) -> List[SessionMeta]:
        if not self.root.exists():
            return []
        files = sorted(self.root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        sessions: List[SessionMeta] = []
        for path in files:
            meta = self._parse_session_meta(path)
            if not meta:
                continue
            sessions.append(meta)
            if len(sessions) >= limit:
                break
        return sessions

    def find_by_id(self, session_id: str) -> Optional[SessionMeta]:
        if not self.root.exists():
            return None
        for path in self.root.rglob("*.jsonl"):
            meta = self._parse_session_meta(path)
            if meta and meta.session_id == session_id:
                return meta
        return None

    def mark_as_desktop_session(self, session_id: str) -> bool:
        meta = self.find_by_id(session_id)
        if not meta:
            return False
        path = Path(meta.file_path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines:
                return False
            first = json.loads(lines[0])
            if first.get("type") != "session_meta":
                return False
            payload = first.get("payload") or {}
            changed = False
            if payload.get("source") != "vscode":
                payload["source"] = "vscode"
                changed = True
            if payload.get("originator") != "Codex Desktop":
                payload["originator"] = "Codex Desktop"
                changed = True
            if not changed:
                return True
            first["payload"] = payload
            lines[0] = json.dumps(first, ensure_ascii=False, separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
        except Exception:
            return False

    def get_history(
        self,
        session_id: str,
        limit: int = 10,
    ) -> Tuple[Optional[SessionMeta], List[Tuple[str, str]]]:
        meta = self.find_by_id(session_id)
        if not meta:
            return None, []
        path = Path(meta.file_path)
        messages: List[Tuple[str, str]] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get("type") != "event_msg":
                        continue
                    payload = evt.get("payload") or {}
                    msg_type = payload.get("type")
                    if msg_type not in ("user_message", "agent_message"):
                        continue
                    message = (payload.get("message") or "").strip()
                    if not message:
                        continue
                    role = "user" if msg_type == "user_message" else "assistant"
                    messages.append((role, message))
        except Exception:
            return meta, []
        if limit > 0:
            messages = messages[-limit:]
        return meta, messages

    @staticmethod
    def _parse_session_meta(path: Path) -> Optional[SessionMeta]:
        try:
            with path.open("r", encoding="utf-8") as f:
                first_line = f.readline()
            parsed = json.loads(first_line)
            payload = parsed.get("payload") or {}
            if parsed.get("type") != "session_meta":
                return None
            session_id = payload.get("id")
            if not session_id:
                return None
            title = SessionStore._extract_title(path)
            return SessionMeta(
                session_id=session_id,
                timestamp=payload.get("timestamp", "unknown"),
                cwd=payload.get("cwd", "unknown"),
                file_path=str(path),
                title=title or f"session {session_id[:8]}",
            )
        except Exception:
            return None

    @staticmethod
    def _extract_title(path: Path) -> Optional[str]:
        try:
            with path.open("r", encoding="utf-8") as f:
                for _ in range(240):
                    line = f.readline()
                    if not line:
                        break
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get("type") != "event_msg":
                        continue
                    payload = evt.get("payload") or {}
                    if payload.get("type") != "user_message":
                        continue
                    message = (payload.get("message") or "").strip()
                    if not message:
                        continue
                    return SessionStore._compact_title(message)
        except Exception:
            return None
        return None

    @staticmethod
    def _compact_title(text: str, limit: int = 46) -> str:
        one_line = " ".join(text.split())
        if len(one_line) <= limit:
            return one_line
        return one_line[: limit - 1] + "…"

    @staticmethod
    def compact_message(text: str, limit: int = 320) -> str:
        one_line = " ".join(text.split())
        if len(one_line) <= limit:
            return one_line
        return one_line[: limit - 1] + "…"


class BotState:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = {"users": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {"users": {}}

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_user(self, user_id: int) -> Dict[str, Any]:
        users = self.data.setdefault("users", {})
        key = str(user_id)
        if key not in users:
            users[key] = {}
        return users[key]

    def set_active_session(self, user_id: int, session_id: str, cwd: str) -> None:
        user_data = self.get_user(user_id)
        user_data["active_session_id"] = session_id
        user_data["active_cwd"] = cwd
        self.save()

    def clear_active_session(self, user_id: int, cwd: str) -> None:
        user_data = self.get_user(user_id)
        user_data["active_session_id"] = None
        user_data["active_cwd"] = cwd
        self.save()

    def get_active(self, user_id: int) -> Tuple[Optional[str], Optional[str]]:
        user_data = self.get_user(user_id)
        return user_data.get("active_session_id"), user_data.get("active_cwd")

    def set_last_session_ids(self, user_id: int, session_ids: List[str]) -> None:
        user_data = self.get_user(user_id)
        user_data["last_session_ids"] = session_ids
        self.save()

    def get_last_session_ids(self, user_id: int) -> List[str]:
        user_data = self.get_user(user_id)
        values = user_data.get("last_session_ids")
        if not isinstance(values, list):
            return []
        return [str(v) for v in values]

    def set_pending_session_pick(self, user_id: int, enabled: bool) -> None:
        user_data = self.get_user(user_id)
        user_data["pending_session_pick"] = bool(enabled)
        self.save()

    def is_pending_session_pick(self, user_id: int) -> bool:
        user_data = self.get_user(user_id)
        return bool(user_data.get("pending_session_pick"))


class CodexRunner:
    def __init__(
        self,
        codex_bin: str,
        sandbox_mode: Optional[str] = None,
        approval_policy: Optional[str] = None,
        dangerous_bypass_level: int = 0,
    ):
        self.codex_bin = codex_bin
        self.sandbox_mode = sandbox_mode
        self.approval_policy = approval_policy
        self.dangerous_bypass_level = max(0, min(2, int(dangerous_bypass_level)))

    @staticmethod
    def _to_toml_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def run_prompt(
        self,
        prompt: str,
        cwd: Path,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[str], str, str, int]:
        config_flags: List[str] = []
        if self.dangerous_bypass_level == 1:
            sandbox_mode = self.sandbox_mode or "danger-full-access"
            approval_policy = self.approval_policy or "never"
            config_flags.extend(["-c", f"sandbox_mode={self._to_toml_string(sandbox_mode)}"])
            config_flags.extend(["-c", f"approval_policy={self._to_toml_string(approval_policy)}"])

        exec_flags: List[str] = ["--json", "--skip-git-repo-check"]
        if self.dangerous_bypass_level >= 2:
            exec_flags.append("--dangerously-bypass-approvals-and-sandbox")

        if session_id:
            cmd = [
                self.codex_bin,
                "exec",
                "resume",
                *config_flags,
                *exec_flags,
                session_id,
                prompt,
            ]
        else:
            cmd = [
                self.codex_bin,
                "exec",
                *config_flags,
                *exec_flags,
                prompt,
            ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as e:
            return None, f"找不到 codex 可执行文件: {self.codex_bin}", str(e), 127
        thread_id, agent_text = self._parse_exec_json(proc.stdout)
        if not agent_text:
            merged = (proc.stdout + "\n" + proc.stderr).strip()
            if merged:
                agent_text = merged[-3500:]
            else:
                agent_text = "Codex 没有返回可展示内容。"
        return thread_id, agent_text, proc.stderr.strip(), proc.returncode

    @staticmethod
    def _parse_exec_json(stdout: str) -> Tuple[Optional[str], str]:
        thread_id: Optional[str] = None
        messages: List[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "thread.started":
                thread_id = evt.get("thread_id")
            if evt.get("type") == "item.completed":
                item = evt.get("item") or {}
                if item.get("type") == "agent_message":
                    text = item.get("text")
                    if text:
                        messages.append(text)
        return thread_id, "\n\n".join(messages).strip()


class TgCodexService:
    def __init__(
        self,
        api: TelegramAPI,
        sessions: SessionStore,
        state: BotState,
        codex: CodexRunner,
        default_cwd: Path,
        allowed_user_ids: Optional[Set[int]],
    ):
        self.api = api
        self.sessions = sessions
        self.state = state
        self.codex = codex
        self.default_cwd = default_cwd
        self.allowed_user_ids = allowed_user_ids
        self.offset: Optional[int] = None

    def run_forever(self) -> None:
        while True:
            try:
                updates = self.api.get_updates(self.offset, timeout=30)
                for update in updates:
                    self.offset = update["update_id"] + 1
                    self._handle_update(update)
            except urllib.error.URLError as e:
                print(f"[warn] telegram network error: {e}", file=sys.stderr)
                time.sleep(2)
            except Exception as e:
                print(f"[warn] loop error: {e}", file=sys.stderr)
                traceback.print_exc()
                time.sleep(2)

    def setup_bot_menu(self) -> None:
        self.api.set_my_commands(BOT_COMMANDS)
        try:
            self.api.set_chat_menu_button_commands()
        except Exception:
            # Non-critical; setMyCommands already provides slash-menu commands.
            pass

    def _handle_update(self, update: Dict[str, Any]) -> None:
        callback_query = update.get("callback_query")
        if callback_query:
            self._handle_callback_query(callback_query)
            return

        msg = update.get("message")
        if not msg:
            return
        text = (msg.get("text") or "").strip()

        chat_id = msg["chat"]["id"]
        message_id = msg["message_id"]
        user = msg.get("from") or {}
        user_id = user.get("id")

        if user_id is None:
            return
        log(
            f"update received: user_id={user_id} chat_id={chat_id} "
            f"text={text[:80]!r}"
        )

        if self.allowed_user_ids is not None and int(user_id) not in self.allowed_user_ids:
            log(f"blocked by allowlist: user_id={user_id}")
            self.api.send_message(chat_id, "没有权限使用这个 bot。", reply_to=message_id)
            return

        if not text:
            return
        if not text.startswith("/"):
            if self._try_handle_quick_session_pick(chat_id, message_id, int(user_id), text):
                return
            self.state.set_pending_session_pick(int(user_id), False)
            self._handle_chat_message(chat_id, message_id, int(user_id), text)
            return

        cmd, arg = self._parse_command(text)
        log(f"command: /{cmd} arg={arg[:80]!r}")
        if cmd in ("start", "help"):
            self._send_help(chat_id, message_id)
            return
        if cmd == "sessions":
            self._handle_sessions(chat_id, message_id, arg, int(user_id))
            return
        if cmd == "use":
            self._handle_use(chat_id, message_id, int(user_id), arg)
            return
        if cmd == "status":
            self._handle_status(chat_id, message_id, int(user_id))
            return
        if cmd == "new":
            self._handle_new(chat_id, message_id, int(user_id), arg)
            return
        if cmd == "history":
            self._handle_history(chat_id, message_id, int(user_id), arg)
            return
        if cmd == "ask":
            self._handle_ask(chat_id, message_id, int(user_id), arg)
            return

        self.api.send_message(chat_id, f"未知命令: /{cmd}\n发送 /help 查看说明。", reply_to=message_id)

    def _handle_callback_query(self, callback_query: Dict[str, Any]) -> None:
        cq_id = callback_query.get("id")
        data = (callback_query.get("data") or "").strip()
        msg = callback_query.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        reply_to = msg.get("message_id")
        user = callback_query.get("from") or {}
        user_id = user.get("id")

        if not cq_id or user_id is None:
            return
        if self.allowed_user_ids is not None and int(user_id) not in self.allowed_user_ids:
            self.api.answer_callback_query(cq_id, text="没有权限。", show_alert=True)
            return
        if not isinstance(chat_id, int):
            self.api.answer_callback_query(cq_id, text="无法解析聊天上下文。", show_alert=True)
            return

        if data.startswith("use:"):
            session_id = data[4:]
            self.api.answer_callback_query(cq_id, text="正在切换会话...")
            self._switch_to_session(chat_id, reply_to, int(user_id), session_id)
            return

        self.api.answer_callback_query(cq_id, text="不支持的操作。", show_alert=True)

    @staticmethod
    def _parse_command(text: str) -> Tuple[str, str]:
        parts = text.split(" ", 1)
        cmd = parts[0][1:]
        cmd = cmd.split("@", 1)[0].strip().lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        return cmd, arg

    def _send_help(self, chat_id: int, reply_to: int) -> None:
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
                    "执行 /sessions 后，也可点击按钮直接切换会话",
                    "直接发普通消息即可对话（会自动续聊当前 session）",
                ]
            ),
            reply_to=reply_to,
        )

    def _handle_sessions(self, chat_id: int, reply_to: int, arg: str, user_id: int) -> None:
        limit = 10
        if arg:
            try:
                limit = max(1, min(30, int(arg)))
            except ValueError:
                self.api.send_message(chat_id, "参数错误，示例: /sessions 10", reply_to=reply_to)
                return
        items = self.sessions.list_recent(limit=limit)
        if not items:
            self.api.send_message(chat_id, "未找到本地会话记录。", reply_to=reply_to)
            return
        lines = ["最近会话（用 /use 编号 切换）:"]
        session_ids = [s.session_id for s in items]
        keyboard_rows: List[List[Dict[str, str]]] = []
        for i, s in enumerate(items, start=1):
            short_id = s.session_id[:8]
            cwd_name = Path(s.cwd).name or s.cwd
            lines.append(f"{i}. {s.title} | {short_id} | {cwd_name}")
            keyboard_rows.append(
                [
                    {
                        "text": f"切换 {i}",
                        "callback_data": f"use:{s.session_id}",
                    }
                ]
            )
        lines.append("直接发送编号即可切换（例如发送: 1）")
        self.api.send_message(
            chat_id,
            "\n".join(lines),
            reply_to=reply_to,
            reply_markup={"inline_keyboard": keyboard_rows},
        )
        self.state.set_last_session_ids(user_id, session_ids)
        self.state.set_pending_session_pick(user_id, True)

    def _handle_use(self, chat_id: int, reply_to: int, user_id: int, arg: str) -> None:
        selector = arg.strip()
        if not selector:
            self.api.send_message(chat_id, "示例: /use 1 或 /use <session_id>", reply_to=reply_to)
            return
        session_id, err = self._resolve_session_selector(user_id, selector)
        if err:
            self.api.send_message(chat_id, err, reply_to=reply_to)
            return
        if not session_id:
            self.api.send_message(chat_id, "无效的会话选择参数。", reply_to=reply_to)
            return
        self._switch_to_session(chat_id, reply_to, user_id, session_id)

    def _switch_to_session(self, chat_id: int, reply_to: int, user_id: int, session_id: str) -> None:
        meta = self.sessions.find_by_id(session_id)
        if not meta:
            self.api.send_message(chat_id, f"未找到 session: {session_id}", reply_to=reply_to)
            return
        self.state.set_active_session(user_id, meta.session_id, meta.cwd)
        self.state.set_pending_session_pick(user_id, False)
        self.api.send_message(
            chat_id,
            f"已切换到:\n{meta.title}\nsession: {meta.session_id}\ncwd: {meta.cwd}\n现在可直接发消息对话。",
            reply_to=reply_to,
        )

    def _try_handle_quick_session_pick(self, chat_id: int, reply_to: int, user_id: int, text: str) -> bool:
        if not self.state.is_pending_session_pick(user_id):
            return False
        raw = text.strip()
        if not raw.isdigit():
            return False
        idx = int(raw)
        recent_ids = self.state.get_last_session_ids(user_id)
        if idx <= 0 or idx > len(recent_ids):
            self.api.send_message(
                chat_id,
                "编号无效。请发送 /sessions 重新查看列表。",
                reply_to=reply_to,
            )
            return True
        self._switch_to_session(chat_id, reply_to, user_id, recent_ids[idx - 1])
        return True

    def _handle_history(self, chat_id: int, reply_to: int, user_id: int, arg: str) -> None:
        tokens = [x for x in arg.split() if x]
        limit = 10
        session_id: Optional[str] = None

        if not tokens:
            session_id, _ = self.state.get_active(user_id)
            if not session_id:
                self.api.send_message(
                    chat_id,
                    "当前无 active session。先 /use 选择会话，或直接对话后再查看历史。",
                    reply_to=reply_to,
                )
                return
        else:
            session_id, err = self._resolve_session_selector(user_id, tokens[0])
            if err:
                self.api.send_message(chat_id, err, reply_to=reply_to)
                return
            if not session_id:
                self.api.send_message(chat_id, "无效的会话选择参数。", reply_to=reply_to)
                return
            if len(tokens) >= 2:
                try:
                    limit = int(tokens[1])
                except ValueError:
                    self.api.send_message(chat_id, "N 必须是数字，示例: /history 1 20", reply_to=reply_to)
                    return

        limit = max(1, min(50, limit))
        meta, messages = self.sessions.get_history(session_id, limit=limit)
        if not meta:
            self.api.send_message(chat_id, f"未找到 session: {session_id}", reply_to=reply_to)
            return
        if not messages:
            self.api.send_message(chat_id, "该会话暂无可展示历史消息。", reply_to=reply_to)
            return

        lines = [
            f"会话历史: {meta.title}",
            f"session: {meta.session_id}",
            f"显示最近 {len(messages)} 条消息:",
        ]
        for i, (role, message) in enumerate(messages, start=1):
            role_zh = "用户" if role == "user" else "助手"
            lines.append(f"{i}. [{role_zh}] {SessionStore.compact_message(message)}")
        self.api.send_message(chat_id, "\n".join(lines), reply_to=reply_to)

    def _resolve_session_selector(self, user_id: int, selector: str) -> Tuple[Optional[str], Optional[str]]:
        raw = selector.strip()
        if not raw:
            return None, "示例: /use 1 或 /use <session_id>"
        if raw.isdigit():
            idx = int(raw)
            recent_ids = self.state.get_last_session_ids(user_id)
            if idx <= 0 or idx > len(recent_ids):
                return None, "编号无效。先执行 /sessions，再用编号。"
            return recent_ids[idx - 1], None
        return raw, None

    def _handle_status(self, chat_id: int, reply_to: int, user_id: int) -> None:
        session_id, cwd = self.state.get_active(user_id)
        if not session_id:
            self.api.send_message(
                chat_id,
                "当前没有绑定会话。可先 /sessions + /use，或 /new 后直接发消息。",
                reply_to=reply_to,
            )
            return
        title = f"session {session_id[:8]}"
        meta = self.sessions.find_by_id(session_id)
        if meta:
            title = meta.title
        self.api.send_message(
            chat_id,
            f"当前会话:\n{title}\nsession: {session_id}\ncwd: {cwd or str(self.default_cwd)}\n支持与本地 Codex 客户端交替续聊。",
            reply_to=reply_to,
        )

    def _handle_ask(self, chat_id: int, reply_to: int, user_id: int, arg: str) -> None:
        prompt = arg.strip()
        if not prompt:
            self.api.send_message(chat_id, "示例: /ask 帮我总结当前仓库结构", reply_to=reply_to)
            return
        self._run_prompt(chat_id, reply_to, user_id, prompt)

    def _handle_new(self, chat_id: int, reply_to: int, user_id: int, arg: str) -> None:
        cwd_raw = arg.strip()
        _, current_cwd = self.state.get_active(user_id)
        target_cwd = Path(current_cwd).expanduser() if current_cwd else self.default_cwd
        if cwd_raw:
            candidate = Path(cwd_raw).expanduser()
            if not candidate.exists() or not candidate.is_dir():
                self.api.send_message(chat_id, f"cwd 不存在或不是目录: {candidate}", reply_to=reply_to)
                return
            target_cwd = candidate
        self.state.clear_active_session(user_id, str(target_cwd))
        self.state.set_pending_session_pick(user_id, False)
        self.api.send_message(
            chat_id,
            f"已进入新会话模式，cwd: {target_cwd}\n下一条普通消息会创建一个新 session。",
            reply_to=reply_to,
        )

    def _handle_chat_message(self, chat_id: int, reply_to: int, user_id: int, text: str) -> None:
        self._run_prompt(chat_id, reply_to, user_id, text)

    def _run_prompt(self, chat_id: int, reply_to: int, user_id: int, prompt: str) -> None:
        active_id, active_cwd = self.state.get_active(user_id)
        cwd = Path(active_cwd).expanduser() if active_cwd else self.default_cwd
        if not cwd.exists():
            cwd = self.default_cwd

        mode = "继续当前会话" if active_id else "新建会话"
        log(f"run prompt: user_id={user_id} mode={mode} cwd={cwd} session={active_id}")
        typing = TypingStatus(self.api, chat_id)
        typing.start()
        try:
            thread_id, answer, stderr_text, return_code = self.codex.run_prompt(
                prompt=prompt,
                cwd=cwd,
                session_id=active_id,
            )
        except Exception as e:
            self.api.send_message(
                chat_id,
                f"调用 Codex 时出现异常: {e}",
                reply_to=reply_to,
            )
            return
        finally:
            typing.stop()

        if thread_id:
            self.state.set_active_session(user_id, thread_id, str(cwd))

        if return_code != 0:
            msg = f"Codex 执行失败 (exit={return_code})\n{answer}"
            if stderr_text:
                msg += f"\n\nstderr:\n{stderr_text[-1200:]}"
            self.api.send_message(chat_id, msg, reply_to=reply_to)
            return

        self.api.send_message(chat_id, answer, reply_to=reply_to)


def resolve_codex_bin(configured: Optional[str]) -> str:
    if configured:
        return configured
    found = shutil.which("codex")
    if found:
        return found
    app_path = "/Applications/Codex.app/Contents/Resources/codex"
    if Path(app_path).exists():
        return app_path
    return "codex"


def build_service() -> TgCodexService:
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("missing TELEGRAM_BOT_TOKEN")

    allowed_user_ids = parse_allowed_user_ids(env("ALLOWED_TELEGRAM_USER_IDS"))
    session_root = Path(env("CODEX_SESSION_ROOT", "~/.codex/sessions")).expanduser()
    state_path = Path(env("STATE_PATH", "./bot_state.json"))
    codex_bin = resolve_codex_bin(env("CODEX_BIN"))
    codex_sandbox_mode = env("CODEX_SANDBOX_MODE")
    codex_approval_policy = env("CODEX_APPROVAL_POLICY")
    codex_dangerous_bypass_level = parse_dangerous_bypass_level(env("CODEX_DANGEROUS_BYPASS", "0"))
    default_cwd = Path(env("DEFAULT_CWD", os.getcwd())).expanduser()
    ca_bundle = env("TELEGRAM_CA_BUNDLE")
    insecure_skip_verify = env("TELEGRAM_INSECURE_SKIP_VERIFY", "0") == "1"

    api = TelegramAPI(
        token=token,
        ca_bundle=ca_bundle,
        insecure_skip_verify=insecure_skip_verify,
    )
    sessions = SessionStore(session_root)
    state = BotState(state_path)
    codex = CodexRunner(
        codex_bin=codex_bin,
        sandbox_mode=codex_sandbox_mode,
        approval_policy=codex_approval_policy,
        dangerous_bypass_level=codex_dangerous_bypass_level,
    )
    if codex_dangerous_bypass_level == 1:
        log("[warn] CODEX_DANGEROUS_BYPASS=1, enabling sandbox_mode=danger-full-access and approval_policy=never")
    elif codex_dangerous_bypass_level >= 2:
        log("[warn] CODEX_DANGEROUS_BYPASS=2, approvals and sandbox are fully bypassed")

    return TgCodexService(
        api=api,
        sessions=sessions,
        state=state,
        codex=codex,
        default_cwd=default_cwd,
        allowed_user_ids=allowed_user_ids,
    )


def main() -> None:
    service = build_service()
    try:
        service.setup_bot_menu()
        log("bot command menu configured")
    except Exception as e:
        log(f"bot command menu setup failed: {e}")
    log("tg-codex service started")
    service.run_forever()


if __name__ == "__main__":
    main()
