"""本机问卷、不可变版本、填写记录和云端回执。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .images import validate_raster_image
from .quiz_rendering import (
    collect_quiz_edge_image_references,
    collect_rendered_quiz_image_references,
)
from .quiz_rules import participant_spec
from .validation import _validate_plain_source, quiz_snapshot_digest


def data_home():
    if configured := os.getenv("GOODWEN_LOCAL_HOME"):
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "Goodwen" / "Local"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Goodwen Local"
    return (
        Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / "goodwen-local"
    )


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS survey (
 id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, title TEXT NOT NULL, latest TEXT,
 local_only INTEGER NOT NULL DEFAULT 0, owner TEXT);
CREATE TABLE IF NOT EXISTS snapshot (
 id TEXT PRIMARY KEY, survey_id TEXT NOT NULL REFERENCES survey(id), digest TEXT NOT NULL,
 source TEXT NOT NULL, spec TEXT NOT NULL, public TEXT NOT NULL, created REAL NOT NULL,
 shared INTEGER NOT NULL DEFAULT 0, UNIQUE(survey_id,digest));
CREATE TABLE IF NOT EXISTS blob (hash TEXT PRIMARY KEY, content BLOB NOT NULL, mime TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resource (snapshot TEXT NOT NULL REFERENCES snapshot(id), path TEXT NOT NULL,
 hash TEXT NOT NULL REFERENCES blob(hash), public INTEGER NOT NULL, PRIMARY KEY(snapshot,path));
CREATE TABLE IF NOT EXISTS attempt (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL REFERENCES snapshot(id),
 session TEXT NOT NULL, preview INTEGER NOT NULL, language TEXT NOT NULL, cursor INTEGER NOT NULL DEFAULT 0,
 answers TEXT NOT NULL DEFAULT '{}', timing TEXT NOT NULL DEFAULT '{}', started REAL NOT NULL,
 question_started REAL NOT NULL, submitted REAL, grading TEXT, UNIQUE(snapshot,session,preview));
CREATE INDEX IF NOT EXISTS attempt_results ON attempt(snapshot,preview,submitted);
CREATE TABLE IF NOT EXISTS preference (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cloud_map (workspace TEXT NOT NULL, survey TEXT NOT NULL REFERENCES survey(id),
 snapshot TEXT NOT NULL, draft TEXT NOT NULL, digest TEXT NOT NULL, review TEXT NOT NULL,
 pack TEXT, release TEXT, PRIMARY KEY(workspace,survey));
CREATE TABLE IF NOT EXISTS cloud_version (workspace TEXT NOT NULL,snapshot TEXT NOT NULL REFERENCES snapshot(id),
 draft TEXT NOT NULL,digest TEXT NOT NULL,pack TEXT,release TEXT,PRIMARY KEY(workspace,snapshot));
CREATE TABLE IF NOT EXISTS publication (snapshot TEXT PRIMARY KEY REFERENCES snapshot(id), workspace TEXT,
 status TEXT NOT NULL, url TEXT, error TEXT);
"""


class Library:
    def __init__(self, home=None):
        self.home = Path(home or data_home()).resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = self.home / "library.sqlite3"
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        if os.name != "nt":
            self.file.chmod(0o600)

    @contextmanager
    def db(self, *, write=False):
        conn = sqlite3.connect(self.file, timeout=12, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def pref(self, key):
        with self.db() as db:
            row = db.execute(
                "SELECT value FROM preference WHERE key=?", (key,)
            ).fetchone()
            return row[0] if row else None

    def set_pref(self, key, value):
        with self.db(write=True) as db:
            db.execute("INSERT OR REPLACE INTO preference VALUES(?,?)", (key, value))

    def save(self, path):
        path = Path(path).expanduser().resolve(strict=True)
        source, validated, assets = load_source(path)
        digest = quiz_snapshot_digest(
            source, {name: (data, mime) for name, (data, mime) in assets.items()}
        )
        public = participant_spec(validated.public_spec)
        visible = set(collect_rendered_quiz_image_references(public))
        with self.db(write=True) as db:
            survey = db.execute(
                "SELECT id,local_only,owner FROM survey WHERE path=?", (str(path),)
            ).fetchone()
            survey_id = survey[0] if survey else str(uuid.uuid4())
            if not survey:
                db.execute(
                    "INSERT INTO survey(id,path,title) VALUES(?,?,?)",
                    (survey_id, str(path), validated.title),
                )
            existing = db.execute(
                "SELECT id FROM snapshot WHERE survey_id=? AND digest=?",
                (survey_id, digest),
            ).fetchone()
            snapshot = existing[0] if existing else str(uuid.uuid4())
            if not existing:
                db.execute(
                    "INSERT INTO snapshot(id,survey_id,digest,source,spec,public,created) VALUES(?,?,?,?,?,?,?)",
                    (
                        snapshot,
                        survey_id,
                        digest,
                        source,
                        encode(validated.spec),
                        encode(public),
                        time.time(),
                    ),
                )
                for name, (data, mime) in assets.items():
                    checksum = hashlib.sha256(data).hexdigest()
                    db.execute(
                        "INSERT OR IGNORE INTO blob VALUES(?,?,?)",
                        (checksum, data, mime),
                    )
                    db.execute(
                        "INSERT INTO resource VALUES(?,?,?,?)",
                        (snapshot, name, checksum, int(name in visible)),
                    )
            db.execute(
                "UPDATE survey SET latest=?,title=? WHERE id=?",
                (snapshot, validated.title, survey_id),
            )
        return {
            "survey_id": survey_id,
            "snapshot_id": snapshot,
            "local_only": bool(survey and survey["local_only"]),
            "workspace": survey["owner"] if survey else None,
            "title": validated.title,
            "digest": digest,
        }

    def surveys(self):
        with self.db() as db:
            return [
                dict(r) for r in db.execute("SELECT * FROM survey ORDER BY title,id")
            ]

    def snapshot(self, identifier):
        with self.db() as db:
            row = db.execute(
                "SELECT snapshot.* FROM snapshot WHERE id=? OR id=(SELECT latest FROM survey WHERE id=?)",
                (identifier, identifier),
            ).fetchone()
            if not row:
                raise ValueError("未找到本地问卷版本")
            return {
                **dict(row),
                "spec": json.loads(row["spec"]),
                "public": json.loads(row["public"]),
            }

    def responses(self, snapshot):
        with self.db() as db:
            rows = db.execute(
                "SELECT id,snapshot,language,answers,timing,submitted,grading FROM attempt "
                "WHERE snapshot=? AND preview=0 AND submitted IS NOT NULL ORDER BY submitted,id",
                (snapshot,),
            )
            return [
                {
                    **dict(row),
                    **{
                        key: json.loads(row[key])
                        for key in ("answers", "timing", "grading")
                    },
                }
                for row in rows
            ]


def load_source(path):
    if path.stat().st_size > 4_000_000:
        raise ValueError("QML 超过大小限制")
    source = path.read_text(encoding="utf-8-sig")
    if len(source) > 1_000_000:
        raise ValueError("QML 超过一百万字符")
    first = _validate_plain_source(source)
    errors = [
        i for i in first.validation_issues if i["code"] != "local_assets_unsupported"
    ]
    if errors:
        raise ValueError(format_issues(errors))
    expected = {p for issue in first.validation_issues for p in issue.get("paths", [])}
    # 服务端诊断只展示前 100 项。直接解析一次以取得完整资源集合。
    from .qml import parse_qml_markdown

    spec, _ = parse_qml_markdown(source)
    expected.update(collect_rendered_quiz_image_references(spec))
    edges = collect_quiz_edge_image_references(spec)
    # 同时用于首尾画面和题目的图片按题图上限检查。
    question_spec = {
        k: v for k, v in spec.items() if k not in ("welcome_image", "end_image")
    }
    question_spec["translations"] = {
        lang: {
            k: v
            for k, v in translation.items()
            if k not in ("welcome_image", "end_image")
        }
        for lang, translation in spec.get("translations", {}).items()
    }
    question_assets = set(collect_rendered_quiz_image_references(question_spec))
    assets = {}
    root = (path.parent / "assets").resolve()
    if expected and not root.is_relative_to(path.parent):
        raise ValueError("资源目录超出问卷所在目录")
    for name in sorted(expected):
        parts = PurePosixPath(name).parts
        if len(parts) < 2 or parts[0] != "assets" or ".." in parts:
            raise ValueError(f"图片必须位于问卷 assets 目录内 {name}")
        target = (path.parent / name).resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError(f"图片超出资源目录 {name}")
        limit = (
            (2 if name in edges and name not in question_assets else 1) * 1024 * 1024
        )
        with target.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"图片超出 {limit} 字节限制 {name}")
        image = validate_raster_image(
            filename=target.name,
            declared_mime=mimetypes.guess_type(name)[0] or "",
            content=data,
        )
        assets[name] = (data, image.mime)
    validated = _validate_plain_source(source, asset_paths=frozenset(assets))
    if validated.validation_issues:
        raise ValueError(format_issues(validated.validation_issues))
    return source, validated, assets


def format_issues(issues):
    return "\n".join(f"第 {i.get('line') or 1} 行 · {i['message']}" for i in issues)
