from __future__ import annotations
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any
from .qml import QmlParseError, parse_qml_markdown
from .quiz_metadata import apply_quiz_metadata
from .quiz_rendering import collect_rendered_quiz_image_references, _is_local_asset_path

_FRONTMATTER_ID_RE = re.compile(r"(?mi)^id:\s*(?P<id>[A-Za-z0-9_-]+)\s*$")
_JSON_PROJECTION_MAX_DEPTH = 64
_JSON_PROJECTION_MAX_NODES = 50_000
_JSON_PROJECTION_MAX_STRING_CHARS = 2_000_000

def _read_frontmatter_exam_id(markdown_text: str) -> str:
    text = str(markdown_text or "")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    front = text[: end + 1]
    match = _FRONTMATTER_ID_RE.search(front)
    return str(match.group("id") if match else "").strip()


def quiz_snapshot_digest(
    markdown_text: str,
    assets: dict[str, tuple[bytes, str]],
) -> str:
    hasher = hashlib.sha256()
    normalized = str(markdown_text or "").replace("\r\n", "\n").encode("utf-8", errors="ignore")
    hasher.update(normalized)
    for rel in sorted(assets.keys()):
        payload, _mime = assets[rel]
        hasher.update(rel.encode("utf-8", errors="ignore"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(payload).digest())
    return hasher.hexdigest()

@dataclass(frozen=True, slots=True)
class _ValidatedSource:
    source_md: str
    content_digest: str
    validation_status: str
    validation_issues: list[dict[str, Any]]
    quiz_key: str | None
    title: str
    spec: dict[str, Any] | None
    public_spec: dict[str, Any] | None


def _issue(code: str, message: str, *, line: int | None = None, **details: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": str(code),
        "message": str(message)[:1000],
    }
    if line is not None:
        item["line"] = int(line)
    for key, value in details.items():
        item[str(key)] = value
    return item


def _json_projection_issue_code(value: Any) -> str | None:
    """Validate a parser projection without expanding YAML alias graphs."""

    node_count = 0
    string_chars = 0
    active_containers: set[int] = set()

    def visit(item: Any, depth: int) -> None:
        nonlocal node_count, string_chars
        node_count += 1
        if node_count > _JSON_PROJECTION_MAX_NODES:
            raise OverflowError("node budget")
        if depth > _JSON_PROJECTION_MAX_DEPTH:
            raise OverflowError("depth budget")
        if item is None or isinstance(item, (bool, int)):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise TypeError("non-finite number")
            return
        if isinstance(item, str):
            string_chars += len(item)
            if string_chars > _JSON_PROJECTION_MAX_STRING_CHARS:
                raise OverflowError("string budget")
            return
        if not isinstance(item, (dict, list)):
            raise TypeError("unsupported JSON type")

        identity = id(item)
        if identity in active_containers:
            raise TypeError("recursive container")
        active_containers.add(identity)
        try:
            if isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise TypeError("non-string JSON key")
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        finally:
            active_containers.remove(identity)

    try:
        visit(value, 0)
    except OverflowError:
        return "projection_too_complex"
    except (TypeError, ValueError, RecursionError):
        return "projection_not_json_compatible"
    return None


def _validate_plain_source(
    source_md: str,
    *,
    asset_paths: frozenset[str] = frozenset(),
) -> _ValidatedSource:
    """Validate one Plain source with the production parser.

    Invalid input is still a useful immutable proposal.  The caller persists
    it with diagnostics, while ``spec``/``public_spec`` remain NULL so it can
    never be mistaken for a releasable parser snapshot.
    """

    text = str(source_md)
    content_digest = quiz_snapshot_digest(text, {})
    issues: list[dict[str, Any]] = []
    explicit_quiz_key = _read_frontmatter_exam_id(text) or None
    if explicit_quiz_key is None:
        issues.append(
            _issue(
                "missing_front_matter_id",
                "Front Matter 必须显式提供仅含字母、数字、下划线或连字符的 id",
                line=1,
            )
        )

    source_lines = text.splitlines()
    front_end = (
        next(
            (
                index
                for index, line_text in enumerate(source_lines[1:], start=1)
                if line_text.strip() == "---"
            ),
            0,
        )
        if source_lines and source_lines[0].strip() == "---"
        else 0
    )
    explicit_llm_line = next(
        (
            index + 1
            for index, line_text in enumerate(source_lines[: front_end + 1])
            if re.fullmatch(r"\s*llm\s*:.*", line_text, flags=re.IGNORECASE)
        ),
        None,
    )
    llm_block_line = next(
        (
            index + 1
            for index, line_text in enumerate(source_lines)
            if re.fullmatch(r"\s*\[/?llm\]\s*", line_text, flags=re.IGNORECASE)
        ),
        None,
    )
    if explicit_llm_line is not None or llm_block_line is not None:
        issues.append(
            _issue(
                "llm_directive_not_supported",
                "Goodwen 不再接受内置 LLM 指令；请只保留可人工审核的 [rubric]",
                line=explicit_llm_line or llm_block_line,
            )
        )

    spec: dict[str, Any] | None = None
    public_spec: dict[str, Any] | None = None
    parsed_spec: dict[str, Any] = {}
    try:
        raw_spec, raw_public_spec = parse_qml_markdown(text)
        if raw_spec.get("schema_version") != 3:
            issues.append(_issue("qml_v3_required", "新建或修改问卷必须使用 QML v3，并明确填写规则", line=1))
        parsed_spec = apply_quiz_metadata(raw_spec, default_schema_version=2)
        parsed_public_spec = apply_quiz_metadata(
            raw_public_spec,
            default_schema_version=2,
        )
        projection = {"spec": parsed_spec, "public_spec": parsed_public_spec}
        projection_issue_code = _json_projection_issue_code(projection)
        if projection_issue_code is None:
            try:
                json.dumps(
                    projection,
                    ensure_ascii=False,
                    allow_nan=False,
                )
            except (TypeError, ValueError, OverflowError, RecursionError):
                projection_issue_code = "projection_not_json_compatible"
        if projection_issue_code is not None:
            issues.append(
                _issue(
                    projection_issue_code,
                    (
                        "QML Front Matter 结构过深或展开后过大"
                        if projection_issue_code == "projection_too_complex"
                        else "QML Front Matter 必须只包含可持久化的 JSON 数据类型"
                    ),
                    line=1,
                )
            )
        if explicit_quiz_key is not None and str(parsed_spec.get("id") or "") != explicit_quiz_key:
            issues.append(
                _issue(
                    "front_matter_id_mismatch",
                    "Front Matter id 与 parser 结果不一致",
                    line=1,
                )
            )
        if not issues:
            spec = parsed_spec
            public_spec = parsed_public_spec
    except QmlParseError as exc:
        issues.append(_issue("qml_parse_error", str(exc), line=exc.line))
    except RecursionError:
        issues.append(
            _issue(
                "projection_too_complex",
                "QML Front Matter 结构过深或展开后过大",
                line=1,
            )
        )

    rendered_images = collect_rendered_quiz_image_references(parsed_spec)
    unsupported_images = [
        path for path in rendered_images if not _is_local_asset_path(path)
    ]
    if unsupported_images:
        issues.append(
            _issue(
                "external_images_unsupported",
                "编辑后的问卷只支持已上传的本地图片；请在 QML 编辑器光标处粘贴或拖入图片",
                paths=list(dict.fromkeys(unsupported_images))[:100],
            )
        )

    local_assets = [path for path in rendered_images if _is_local_asset_path(path)
                    if path.removeprefix("./") not in asset_paths]
    if local_assets:
        issues.append(
            _issue(
                "local_assets_unsupported",
                "图片尚未上传到当前草稿，请通过 questionnaire_draft_image_set 添加题图、欢迎图或结尾图",
                paths=local_assets[:100],
            )
        )

    if issues:
        spec = None
        public_spec = None
    title_value = str(parsed_spec.get("title") or "").strip() if parsed_spec else ""
    return _ValidatedSource(
        source_md=text,
        content_digest=content_digest,
        validation_status="invalid" if issues else "validated",
        validation_issues=issues,
        quiz_key=explicit_quiz_key,
        title=title_value,
        spec=spec,
        public_spec=public_spec,
    )
