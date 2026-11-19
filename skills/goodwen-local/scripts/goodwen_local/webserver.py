"""本机作者入口和按需开放的独立局域网参与者监听器。"""

import ipaddress
import json
import mimetypes
import secrets
import socket
import threading
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import attempts
from .library import encode
from .quiz_languages import (
    available_languages,
    language_catalog,
    language_resources,
    localize_spec,
)

WEB = Path(__file__).resolve().parents[2] / "assets/web"
STATIC = {"app.js", "style.css", "index.html"}


class Application:
    def __init__(self, library, *, port=0, address=None):
        self.lib = library
        self.lock = threading.Lock()
        self.public = None
        self.address = address
        self.jobs = set()
        self.authorization = {}
        self.author = self.listener("127.0.0.1", port, True)

    def listener(self, host, port, private):
        app = self

        class Handler(Request):
            application = app
            author_listener = private

        return ThreadingHTTPServer((host, port), Handler)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.author.server_port}"

    def share(self, snapshot_id, address=None):
        with self.lock:
            if address and self.public and self.address != address:
                raise ValueError(
                    "此服务已在另一张网卡发放。换网卡前请停止服务再重新发放"
                )
            if self.public is None:
                address = address or self.address
                if not address:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.connect(("192.0.2.1", 9))
                        address = sock.getsockname()[0]
                interface = ipaddress.IPv4Address(address)
                if (
                    interface.is_loopback
                    or interface.is_unspecified
                    or interface.is_multicast
                    or address == "255.255.255.255"
                ):
                    raise ValueError("请通过 --address 指定本机局域网地址")
                try:
                    saved = json.loads(self.lib.pref("last_lan_listener") or "{}")
                    port = (
                        saved.get("port", 0) if saved.get("address") == address else 0
                    )
                    self.public = self.listener(address, port, False)
                except OSError as exc:
                    raise ValueError("无法在指定的 IPv4 网卡上发放问卷") from exc
                self.address = address
                self.lib.set_pref(
                    "last_lan_listener",
                    encode({"address": address, "port": self.public.server_port}),
                )
                threading.Thread(target=self.public.serve_forever, daemon=True).start()
            with self.lib.db(write=True) as db:
                db.execute("UPDATE snapshot SET shared=1 WHERE id=?", (snapshot_id,))
            return f"http://{self.address}:{self.public.server_port}/q/{snapshot_id}/"

    def publish(self, snapshot_id):
        from .cloud import publish

        with self.lock:
            if snapshot_id in self.jobs:
                return
            self.jobs.add(snapshot_id)

        def run():
            try:
                publish(
                    self.lib,
                    snapshot_id,
                    on_login=lambda url: self.authorization.update({snapshot_id: url}),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                with self.lib.db(write=True) as db:
                    db.execute(
                        "UPDATE publication SET status='error',error=? WHERE snapshot=?",
                        (str(exc), snapshot_id),
                    )
            finally:
                with self.lock:
                    self.jobs.discard(snapshot_id)
                    self.authorization.pop(snapshot_id, None)

        with self.lib.db(write=True) as db:
            db.execute(
                "INSERT INTO publication(snapshot,status) VALUES(?,'connecting') ON CONFLICT(snapshot) "
                "DO UPDATE SET status='connecting',error=NULL",
                (snapshot_id,),
            )
        threading.Thread(target=run, daemon=True).start()

    def close(self):
        if self.public:
            self.public.shutdown()
            self.public.server_close()
        self.author.server_close()


class Request(BaseHTTPRequestHandler):
    application: Application
    author_listener: bool
    server_version = "GoodwenLocal/0.1"

    def log_message(self, *args):
        pass

    def send(self, status, data, mime="application/json; charset=utf-8", cookie=None):
        data = data if isinstance(data, bytes) else encode(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.handle_action(False)

    def do_POST(self):
        self.handle_action(True)

    def handle_action(self, post):
        try:
            return self.route(post)
        except (ValueError, KeyError, FileNotFoundError) as exc:
            return self.send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except (ConnectionResetError, BrokenPipeError):
            return

    def route(self, post):
        app = self.application
        host = self.headers.get("Host", "")
        expected = f"{self.server.server_address[0]}:{self.server.server_port}"
        if host != expected:
            return self.send(403, {"error": "访问地址不匹配"})
        request = {}
        if post:
            origin = self.headers.get("Origin")
            if (
                origin and origin != f"http://{host}"
            ) or self.headers.get_content_type() != "application/json":
                return self.send(403, {"error": "无效来源"})
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 128000:
                return self.send(413, {"error": "请求大小无效"})
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict):
                raise ValueError("请求格式无效")
        path = unquote(urlsplit(self.path).path)
        parts = path.strip("/").split("/")
        if not post and len(parts) == 2 and parts[0] == "static" and parts[1] in STATIC:
            return self.send(
                200, (WEB / parts[1]).read_bytes(), mimetypes.guess_type(parts[1])[0]
            )
        if parts[0] == "control" and self.author_listener:
            if parts == ["control", "status"] and not post:
                return self.send(
                    200,
                    {
                        "service": "goodwen-local",
                        "origin": app.origin,
                        "lan": app.address if app.public else None,
                    },
                )
            if parts == ["control", "stop"] and post:
                threading.Thread(target=app.author.shutdown, daemon=True).start()
                return self.send(200, {"stopping": True})
        if len(parts) < 2 or parts[0] not in ("q", "preview"):
            return self.send(404, {"error": "入口不存在"})
        preview = parts[0] == "preview"
        if preview and not self.author_listener:
            return self.send(404, {"error": "入口不存在"})
        snap = app.lib.snapshot(parts[1])
        if snap["id"] != parts[1] or not (preview or snap["shared"]):
            return self.send(404, {"error": "问卷尚未发放"})
        tail = parts[2:]
        if not tail and not post:
            return self.send(
                200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8"
            )
        if tail[:1] == ["assets"] and not post:
            with app.lib.db() as db:
                asset = db.execute(
                    "SELECT content,mime FROM resource JOIN blob USING(hash) "
                    "WHERE snapshot=? AND path=? AND public=1",
                    (snap["id"], "/".join(tail)),
                ).fetchone()
            if asset:
                return self.send(200, asset["content"], asset["mime"])
            return self.send(404, {"error": "资源不存在"})
        if len(tail) != 1:
            return self.send(404, {"error": "入口不存在"})
        action = tail[0]
        if preview and post and action == "share":
            return self.send(
                200, {"url": app.share(snap["id"], request.get("address"))}
            )
        if preview and post and action == "publish":
            app.publish(snap["id"])
            return self.send(202, {"status": "connecting"})
        if preview and not post and action == "publication":
            with app.lib.db() as db:
                row = db.execute(
                    "SELECT status,url,error FROM publication WHERE snapshot=?",
                    (snap["id"],),
                ).fetchone()
            if snap["id"] in app.authorization:
                return self.send(
                    200, {"status": "connecting", "url": app.authorization[snap["id"]]}
                )
            return self.send(200, dict(row) if row else {"status": "local"})
        cookies = SimpleCookie()
        cookies.load(self.headers.get("Cookie", ""))
        token = cookies["gw_attempt"].value if "gw_attempt" in cookies else ""
        if not post and action == "info":
            languages = available_languages(snap["public"])
            chosen = parse_qs(urlsplit(self.path).query).get("language", [None])[0]
            spec = localize_spec(snap["public"], chosen)
            author_info = {}
            if preview and not app.lib.pref("workspace"):
                author_info["managed_count"] = sum(
                    not s["local_only"] and not s["owner"] for s in app.lib.surveys()
                )
            return self.send(
                200,
                {
                    "participant": spec["participant"],
                    "count": len(spec["questions"]),
                    "languages": languages,
                    "language": spec["language"],
                    "language_names": {
                        i["code"]: i["name"]
                        for i in language_catalog()
                        if i["code"] in languages
                    },
                    "messages": {
                        code: language_resources()["messages"][code]
                        for code in languages
                    },
                    "welcome_image": spec.get("welcome_image"),
                    "preview": preview,
                    **author_info,
                },
            )
        if post and action == "begin":
            token = (
                token
                if len(token) == 43 and token.isascii()
                else secrets.token_urlsafe(32)
            )
            attempts.begin(app.lib, snap, token, preview, request.get("language"))
            cookie = f"gw_attempt={token}; Path=/{parts[0]}/{snap['id']}/; HttpOnly; SameSite=Strict; Max-Age=2592000"
            return self.send(
                200, attempts.visit(app.lib, snap, token, preview), cookie=cookie
            )
        if token and action in (
            ("answer", "submit", "language") if post else ("state",)
        ):
            return self.send(
                200,
                attempts.visit(
                    app.lib,
                    snap,
                    token,
                    preview,
                    action=action,
                    qid=request.get("qid"),
                    answer=request.get("answer"),
                    language=request.get("language"),
                ),
            )
        return self.send(404, {"error": "请先开始填写"})
