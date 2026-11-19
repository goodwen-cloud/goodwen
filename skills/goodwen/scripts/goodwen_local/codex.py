"""通过 Codex App Server 使用宿主授权，文件内容仅经过本机 stdio。"""

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import webbrowser
from urllib.parse import urlsplit

from . import __version__

ENDPOINT = "https://goodwen.cc/mcp"
SCOPES = [
    "packs:read",
    "questionnaires:read",
    "questionnaires:write",
    "distributions:write",
    "results:read",
    "offline_access",
]


class Codex:
    def __init__(self, *, interactive=False, import_scope=False, on_login=None):
        self.interactive = interactive
        self.import_scope = import_scope
        self.on_login = on_login
        self.inbox = queue.Queue()
        self.events = []
        self.seq = 0
        self.proc = None

    def __enter__(self):
        executable = shutil.which(
            "codex.exe" if os.name == "nt" else "codex"
        ) or shutil.which("codex")
        if not executable:
            raise RuntimeError("请在可运行 Codex 的环境中连接 Goodwen")
        listing = subprocess.run(
            [executable, "mcp", "list", "--json"], capture_output=True, timeout=25
        )
        if listing.returncode:
            raise RuntimeError("Codex 未能读取 MCP 连接")
        entries = json.loads(listing.stdout)
        exact = next(
            (
                x
                for x in entries
                if x.get("enabled", True)
                and x.get("transport", {}).get("url") == ENDPOINT
                and not any(
                    x["transport"].get(k)
                    for k in (
                        "bearer_token_env_var",
                        "http_headers",
                        "env_http_headers",
                    )
                )
            ),
            None,
        )
        used = {x["name"] for x in entries}
        self.name = (
            exact["name"]
            if exact
            else next(
                (n for n in ("goodwen", "goodwen-local-cloud") if n not in used), None
            )
        )
        if not self.name:
            raise RuntimeError("Codex 中的 Goodwen 连接名称已被其他地址占用")
        if not exact and not self.interactive:
            raise RuntimeError("请运行 connect 登录并连接 Goodwen")
        self.proc = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

        def read():
            try:
                for line in self.proc.stdout:
                    self.inbox.put(json.loads(line))
            finally:
                self.inbox.put(None)

        threading.Thread(target=read, daemon=True).start()
        try:
            self.rpc(
                "initialize",
                {"clientInfo": {"name": "goodwen-local", "version": __version__}},
            )
            self.send({"method": "initialized"})
            if not exact:
                self.rpc(
                    "config/value/write",
                    {
                        "keyPath": f"mcp_servers.{self.name}",
                        "value": {"url": ENDPOINT},
                        "mergeStrategy": "upsert",
                    },
                )
            self.thread = self.rpc("thread/start", {"ephemeral": True})["thread"]["id"]
            if not exact or exact.get("auth_status") in (
                "notLoggedIn",
                "not_logged_in",
            ):
                if not self.interactive:
                    raise RuntimeError("Goodwen 授权已经失效，请重新连接")
                self.login()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        if self.proc:
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                self.proc.wait(timeout=8)
            self.proc.stdout.close()

    def send(self, msg):
        self.proc.stdin.write(
            (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        )
        self.proc.stdin.flush()

    def receive(self, deadline):
        try:
            msg = self.inbox.get(timeout=max(0.05, deadline - time.monotonic()))
        except queue.Empty:
            raise RuntimeError("Codex 请求超时，请在原会话重试") from None
        if msg is None:
            raise RuntimeError("Codex App Server 已退出")
        return msg

    def rpc(self, method, params):
        self.seq += 1
        current = self.seq
        self.send({"id": current, "method": method, "params": params})
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            msg = self.receive(deadline)
            if msg.get("id") == current and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError(
                        f"Codex {method} 失败 ({msg['error'].get('code')})"
                    )
                return msg["result"]
            if "id" in msg and "method" in msg:
                self.send(
                    {
                        "id": msg["id"],
                        "error": {
                            "code": -32601,
                            "message": "请在 Codex 中处理交互请求",
                        },
                    }
                )
            elif msg.get("method") == "mcpServer/oauthLogin/completed":
                self.events.append(msg)
        raise RuntimeError("Codex 工具调用超时")

    def login(self):
        scopes = SCOPES + (["results:import"] if self.import_scope else [])
        auth = self.rpc(
            "mcpServer/oauth/login",
            {
                "name": self.name,
                "threadId": self.thread,
                "scopes": scopes,
                "clientRegistration": "cimd",
                "timeoutSecs": 180,
            },
        )
        url = auth["authorizationUrl"]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "goodwen.cc":
            raise RuntimeError("Goodwen 授权地址无效")
        if self.on_login:
            self.on_login(url)
        webbrowser.open(url)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            msg = self.events.pop(0) if self.events else self.receive(deadline)
            item = msg.get("params", {})
            if (
                msg.get("method") == "mcpServer/oauthLogin/completed"
                and item.get("name") == self.name
                and (not auth.get("loginId") or item.get("loginId") == auth["loginId"])
            ):
                if not item.get("success"):
                    raise RuntimeError("连接授权未完成")
                self.rpc("config/mcpServer/reload", {})
                return
        raise RuntimeError("授权超时，请重新连接")

    def call(self, name, **fields):
        data = self.rpc(
            "mcpServer/tool/call",
            {
                "threadId": self.thread,
                "server": self.name,
                "tool": name,
                "arguments": fields,
            },
        )
        payload = data.get("structuredContent")
        if payload is None:
            for block in data.get("content", []):
                if block.get("type") == "text":
                    try:
                        payload = json.loads(block["text"])
                        break
                    except ValueError:
                        pass
        if not isinstance(payload, dict) or data.get("isError"):
            raise RuntimeError(f"Goodwen 未完成 {name}，请检查宿主授权和服务版本")
        if payload.get("ok") is False:
            error = payload.get("error", {})
            raise RuntimeError(
                f"{error.get('code', 'goodwen_error')} · {error.get('message', '请求失败')}"
            )
        return payload
