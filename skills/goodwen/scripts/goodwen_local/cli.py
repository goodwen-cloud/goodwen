"""Skill 内部命令，标准输出为结构化回执。"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from .library import Library, encode, load_source
from .webserver import Application


def request(url, payload=None):
    opener = build_opener(ProxyHandler({}))
    req = Request(
        url,
        data=encode(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=4) as response:
        return json.load(response)


def active(library):
    path = library.home / "server.json"
    try:
        port = json.loads(path.read_text())["port"]
        result = request(f"http://127.0.0.1:{int(port)}/control/status")
        return result if result.get("service") == "goodwen-local" else None
    except (OSError, ValueError, KeyError, URLError):
        return None


def start(library, address=None):
    running = active(library)
    if running:
        return running
    proc = subprocess.Popen(
        [
            sys.executable,
            "-I",
            str(Path(__file__).resolve().parents[1] / "run.py"),
            "_serve",
            *(["--address", address] if address else []),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            if os.name == "nt"
            else 0
        ),
    )
    for _ in range(100):
        if running := active(library):
            return running
        if proc.poll() not in (None, 0):
            break
        time.sleep(0.1)
    raise RuntimeError("本地服务启动失败，可运行 _serve 查看本机诊断")


def serve(library, address):
    with (library.home / "server.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        app = Application(library, address=address)
        state = library.home / "server.json"
        tmp = state.with_suffix(".tmp")
        tmp.write_text(encode({"port": app.author.server_port}))
        tmp.replace(state)
        try:
            app.author.serve_forever()
        finally:
            app.close()
            state.unlink(missing_ok=True)


def export(rows, dest, fmt):
    dest = Path(dest).expanduser()
    with tempfile.NamedTemporaryFile(
        dir=dest.parent,
        mode="w",
        newline="",
        encoding="utf-8-sig" if fmt == "csv" else "utf-8",
        delete=False,
    ) as out:
        tmp = Path(out.name)
        try:
            if fmt == "json":
                json.dump(rows, out, ensure_ascii=False, indent=2)
            else:
                cols = [
                    "id",
                    "snapshot",
                    "language",
                    "submitted",
                    "rule_score",
                    *dict.fromkeys(k for r in rows for k in r["answers"]),
                ]
                writer = csv.DictWriter(out, fieldnames=cols)
                writer.writeheader()
                for row in rows:
                    answers = {
                        k: encode(v) if isinstance(v, list) else v
                        for k, v in row["answers"].items()
                    }
                    writer.writerow(
                        {
                            **{k: row[k] for k in cols[:4]},
                            "rule_score": row["grading"]["rule_score"],
                            **answers,
                        }
                    )
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, dest)
    return {"path": str(dest.resolve()), "count": len(rows)}


def parser():
    p = argparse.ArgumentParser(prog="goodwen-local")
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("validate", "save"):
        cmd = commands.add_parser(name)
        cmd.add_argument("path", type=Path)
    for name in (
        "preview",
        "share",
        "results",
        "publish",
        "import",
        "online-results",
        "local-only",
    ):
        cmd = commands.add_parser(name)
        cmd.add_argument("id", help="本地 survey_id 或 snapshot_id")
        if name == "share":
            cmd.add_argument("--address")
        if name == "results":
            cmd.add_argument("--output")
            cmd.add_argument("--format", choices=("csv", "json"), default="json")
        if name == "import":
            cmd.add_argument("--confirm-count", type=int)
        if name == "local-only":
            cmd.add_argument("mode", choices=("on", "off"))
        if name == "online-results":
            cmd.add_argument(
                "--source", choices=("all", "online", "local"), default="all"
            )
        if name == "publish":
            cmd.add_argument(
                "--participant-id", help="Goodwen 已有参与者 ID，生成定向邀约"
            )
            cmd.add_argument(
                "--verification-method",
                action="append",
                choices=("phone", "email", "wechat", "google", "github"),
                help="公开入口允许的验证方式，可重复指定",
            )
    for name in (
        "list",
        "status",
        "stop",
        "connect",
        "sync",
        "pause",
        "resume",
        "_serve",
    ):
        cmd = commands.add_parser(name)
        if name == "_serve":
            cmd.add_argument("--address")
    return p


def run(args):
    lib = Library()
    cmd = args.command
    if cmd == "_serve":
        serve(lib, args.address)
        return
    if cmd == "validate":
        _, result, assets = load_source(args.path.expanduser().resolve(strict=True))
        return {
            "valid": True,
            "title": result.title,
            "questions": len(result.spec["questions"]),
            "assets": list(assets),
        }
    if cmd == "save":
        saved = lib.save(args.path)
        workspace = lib.pref("workspace")
        if (
            workspace
            and not saved["local_only"]
            and saved["workspace"] in (None, workspace)
            and lib.pref("paused") != "yes"
        ):
            from .cloud import sync

            try:
                saved["cloud"] = sync(lib, only=saved["snapshot_id"])
            except (OSError, RuntimeError, ValueError) as exc:
                saved["cloud"] = {"status": "pending", "reason": str(exc)}
        return saved
    if cmd == "list":
        return lib.surveys()
    if cmd in ("status", "stop"):
        service = active(lib)
        if service and cmd == "stop":
            return request(service["origin"] + "/control/stop", {})
        return service or {"status": "stopped"}
    if cmd in ("connect", "sync", "resume", "pause"):
        from .cloud import sync

        if cmd == "pause":
            lib.set_pref("paused", "yes")
            return {"paused": True}
        if cmd == "resume":
            lib.set_pref("paused", "no")
        return sync(lib, connect=cmd == "connect")
    snap = lib.snapshot(args.id)
    if cmd == "local-only":
        with lib.db(write=True) as db:
            db.execute(
                "UPDATE survey SET local_only=? WHERE id=?",
                (args.mode == "on", snap["survey_id"]),
            )
        return {"local_only": args.mode == "on"}
    if cmd in ("preview", "share"):
        service = start(lib, getattr(args, "address", None))
        url = service["origin"] + "/preview/" + snap["id"] + "/"
        return (
            request(url + "share", {"address": args.address})
            if cmd == "share"
            else {"url": url, "snapshot_id": snap["id"]}
        )
    if cmd == "results":
        rows = lib.responses(snap["id"])
        return (
            export(rows, args.output, args.format)
            if args.output
            else {"count": len(rows), "items": rows}
        )
    from .cloud import import_answers, online_results, publish

    if cmd == "publish":
        if args.participant_id and args.verification_method:
            raise ValueError("定向邀约的验证方式由 Goodwen 决定")
        return publish(
            lib,
            snap["id"],
            args.participant_id,
            verification_methods=args.verification_method,
        )
    if cmd == "import":
        return import_answers(lib, snap["id"], args.confirm_count)
    return online_results(lib, snap["id"], args.source)


def main():
    args = parser().parse_args()
    try:
        result = run(args)
        if result is not None:
            print(encode(result))
        return 0
    except (ValueError, KeyError, RuntimeError, OSError) as exc:
        print(encode({"error": str(exc)}), file=sys.stderr)
        return 1
