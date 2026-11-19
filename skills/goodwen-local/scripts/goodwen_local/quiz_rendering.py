from __future__ import annotations

import copy
import html
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

import markdown as mdlib

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*]\((?P<path>[^)]+)\)")
_HTML_IMG_SRC_RE = re.compile(
    r"""<img\b(?P<before>[^>]*?)\bsrc\s*=\s*(?P<quote>["']?)(?P<path>[^"'>\s]+)(?P=quote)(?P<after>[^>]*)>""",
    re.IGNORECASE,
)
_DISPLAY_ESCAPE_RE = re.compile(r"\\(?P<char>[_{}\[\]#*])")
_STANDALONE_MD_IMAGE_RE = re.compile(r"^\s*!\[[^\]]*]\((?P<path>[^)]+)\)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_FENCED_BLOCK_RE = re.compile(r"^\s*(```|~~~)")
_HORIZONTAL_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_TRAILING_HARD_BREAK_RE = re.compile(r"(?:\\|[ \t]{2,})\s*$")
PUBLIC_INVITE_MATERIAL_MODES = {"none", "resume", "business_card"}


def normalize_public_invite_material_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in PUBLIC_INVITE_MATERIAL_MODES else "resume"


_MARKDOWN_EXTENSIONS = [
    "markdown.extensions.fenced_code",
    "markdown.extensions.footnotes",
    "markdown.extensions.attr_list",
    "markdown.extensions.def_list",
    "markdown.extensions.tables",
    "markdown.extensions.abbr",
    "markdown.extensions.md_in_html",
    "markdown.extensions.sane_lists",
]


def _protect_math_for_markdown(raw: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Python-Markdown treats trailing backslashes as hard line breaks and can
    consume TeX row separators like `\\\\` at end-of-line (e.g. inside `cases`).
    To keep MathJax/TeX intact, temporarily replace math segments with tokens
    before markdown processing, then restore them in the generated HTML.
    """

    text = str(raw or "")
    replacements: list[tuple[str, str]] = []
    out: list[str] = []

    def is_escaped(pos: int) -> bool:
        # Consider a '$' escaped if preceded by an odd number of backslashes.
        bs = 0
        j = pos - 1
        while j >= 0 and text[j] == "\\":
            bs += 1
            j -= 1
        return (bs % 2) == 1

    i = 0
    while i < len(text):
        if text.startswith("$$", i) and not is_escaped(i):
            j = i + 2
            while True:
                k = text.find("$$", j)
                if k < 0:
                    break
                if not is_escaped(k):
                    seg = text[i : k + 2]
                    token = f"@@MATH{len(replacements)}@@"
                    replacements.append((token, html.escape(seg, quote=False)))
                    out.append(token)
                    i = k + 2
                    break
                j = k + 1
            else:
                # Unreachable; keep structure explicit.
                pass
            if i != j and out and out[-1].startswith("@@MATH"):
                continue

        if text.startswith("\\[", i):
            k = text.find("\\]", i + 2)
            if k >= 0:
                seg = text[i : k + 2]
                token = f"@@MATH{len(replacements)}@@"
                replacements.append((token, html.escape(seg, quote=False)))
                out.append(token)
                i = k + 2
                continue

        if text.startswith("\\(", i):
            k = text.find("\\)", i + 2)
            if k >= 0:
                seg = text[i : k + 2]
                token = f"@@MATH{len(replacements)}@@"
                replacements.append((token, html.escape(seg, quote=False)))
                out.append(token)
                i = k + 2
                continue

        if text[i] == "$" and not is_escaped(i) and not text.startswith("$$", i):
            j = i + 1
            while True:
                k = text.find("$", j)
                if k < 0:
                    break
                if not is_escaped(k):
                    seg = text[i : k + 1]
                    token = f"@@MATH{len(replacements)}@@"
                    replacements.append((token, html.escape(seg, quote=False)))
                    out.append(token)
                    i = k + 1
                    break
                j = k + 1
            if out and out[-1].startswith("@@MATH"):
                continue

        out.append(text[i])
        i += 1

    return "".join(out), replacements


def _strip_display_escapes(raw: str) -> str:
    return _DISPLAY_ESCAPE_RE.sub(lambda match: str(match.group("char") or ""), str(raw or ""))


def _split_display_blocks(raw: str) -> list[list[str]]:
    text = str(raw or "").strip()
    if not text:
        return []

    blocks: list[list[str]] = []
    current: list[str] = []
    in_fenced_block = False
    fence_marker = ""

    def flush_current() -> None:
        nonlocal current
        if current:
            blocks.append(current)
            current = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if in_fenced_block:
            current.append(line)
            if stripped.startswith(fence_marker):
                in_fenced_block = False
                fence_marker = ""
            continue

        if not stripped:
            flush_current()
            continue

        if _FENCED_BLOCK_RE.match(stripped):
            flush_current()
            current.append(line)
            in_fenced_block = True
            fence_marker = stripped[:3]
            continue

        is_list_item = bool(_LIST_ITEM_RE.match(stripped))
        prev_stripped = current[-1].strip() if current else ""
        if is_list_item and prev_stripped and not _LIST_ITEM_RE.match(prev_stripped):
            flush_current()

        current.append(line)

    flush_current()
    return blocks


def _is_simple_display_block(block: list[str]) -> bool:
    if not block:
        return False

    for line in block:
        stripped = line.strip()
        if not stripped:
            return False
        if stripped.startswith(("$$", "\\[", "```", "~~~", "#", ">", "|")):
            return False
        if _HORIZONTAL_RULE_RE.fullmatch(stripped):
            return False
        if _LIST_ITEM_RE.match(stripped):
            return False
        if _STANDALONE_MD_IMAGE_RE.fullmatch(stripped):
            return False
        if stripped.startswith("<") and stripped.endswith(">"):
            return False
        if line.startswith(("    ", "\t")):
            return False
    return True


def _is_inline_math_only_block(block: str) -> bool:
    text = str(block or "").strip()
    if not text:
        return False
    if text.startswith("$$") and text.endswith("$$"):
        return False
    if text.startswith("$") and text.endswith("$") and text.count("$") >= 2:
        return True
    if text.startswith("\\(") and text.endswith("\\)"):
        return True
    return False


def _normalize_simple_display_block(block: list[str]) -> str:
    parts: list[str] = []
    for line in block:
        compact = _TRAILING_HARD_BREAK_RE.sub("", line).strip()
        if compact:
            parts.append(compact)
    return " ".join(parts)


def _normalize_display_markdown(raw: str) -> str:
    blocks = _split_display_blocks(raw)
    if not blocks:
        return ""

    out: list[str] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if not _is_simple_display_block(block):
            out.append("\n".join(block).strip())
            i += 1
            continue

        run: list[str] = []
        has_inline_math_only = False
        j = i
        while j < len(blocks) and _is_simple_display_block(blocks[j]):
            normalized = _normalize_simple_display_block(blocks[j])
            if normalized:
                run.append(normalized)
                has_inline_math_only = has_inline_math_only or _is_inline_math_only_block(normalized)
            j += 1

        if has_inline_math_only:
            out.append(" ".join(run))
        else:
            out.extend(run)
        i = j

    return "\n\n".join(out)


def _prepare_display_markdown(markdown_text: str) -> tuple[str, list[tuple[str, str]]]:
    normalized = _normalize_display_markdown(markdown_text)
    protected, math_repls = _protect_math_for_markdown(normalized)
    return _strip_display_escapes(protected), math_repls


def _safe_relpath(raw: str) -> str:
    p = (raw or "").strip().strip('"').strip("'")
    if len(p) >= 2 and p.startswith("<") and p.endswith(">"):
        p = p[1:-1].strip()
    p = p.split("#", 1)[0].strip()
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _is_local_asset_path(p: str) -> bool:
    if not p:
        return False
    lower = p.lower()
    if lower.startswith(("http://", "https://", "data:", "mailto:")):
        return False
    return True


def _render_markdown_html(markdown_text: str) -> str:
    text = str(markdown_text or "").strip()
    if not text:
        return ""

    protected, math_repls = _prepare_display_markdown(text)
    rendered = mdlib.markdown(
        protected,
        extensions=_MARKDOWN_EXTENSIONS,
        output_format="html5",
    )
    for token, math_html in math_repls:
        rendered = rendered.replace(token, math_html)
    return rendered


class _RenderedImageSourceCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        for name, value in attrs:
            if name.lower() == "src" and value:
                path = _safe_relpath(value)
                if path:
                    self.sources.add(path)
                return


def _collect_rendered_markdown_assets(markdown_text: str) -> set[str]:
    collector = _RenderedImageSourceCollector()
    collector.feed(_render_markdown_html(markdown_text))
    collector.close()
    return collector.sources


def collect_quiz_edge_image_references(spec: dict[str, Any]) -> frozenset[str]:
    """全部语种首尾图的路径，用于统一的上传、复制与仓库大小规则。"""
    return frozenset(
        _safe_relpath(str(content[key]))
        for content in [spec, *(spec.get("translations") or {}).values()]
        for key in ("welcome_image", "end_image")
        if content.get(key)
    )


def collect_rendered_quiz_image_references(spec: dict[str, Any]) -> list[str]:
    """返回实际会渲染为图片的全部引用，而不是源码中的字符串命中。

    先使用与预览相同的 Markdown 渲染器，因此 fenced code、inline code
    或普通说明文字中的图片示例不会被误当作 Release 资源。
    """

    references: set[str] = set()

    def add_direct(value: Any) -> None:
        path = _safe_relpath(str(value or ""))
        if path:
            references.add(path)

    for key in ("welcome_image", "end_image"):
        add_direct(spec.get(key))
    for question in spec.get("questions") or []:
        if not isinstance(question, dict):
            continue
        add_direct(question.get("media"))
        references.update(
            _collect_rendered_markdown_assets(str(question.get("stem_md") or ""))
        )
        references.update(
            _collect_rendered_markdown_assets(str(question.get("rubric") or ""))
        )
        for option in question.get("options") or []:
            if isinstance(option, dict):
                references.update(
                    _collect_rendered_markdown_assets(str(option.get("text") or ""))
                )
    for translation in (spec.get("translations") or {}).values():
        localized = {**translation, "questions": [{**q, "options": [{"key": k, "text": v} for k, v in (q.get("options") or {}).items()]} for q in (translation.get("questions") or {}).values()]}
        references.update(collect_rendered_quiz_image_references(localized))
    return sorted(references)


def collect_rendered_quiz_asset_references(spec: dict[str, Any]) -> list[str]:
    """返回当前 spec 实际渲染的本地 Release 资源引用。"""

    return [
        path
        for path in collect_rendered_quiz_image_references(spec)
        if _is_local_asset_path(path)
    ]


def build_render_ready_question(question: dict[str, Any], *, include_rubric_html: bool = False) -> dict[str, Any]:
    q2 = copy.deepcopy(question or {})
    q2["stem_html"] = _render_markdown_html(str(q2.get("stem_md") or ""))
    options_out = []
    for option in q2.get("options") or []:
        if not isinstance(option, dict):
            options_out.append(option)
            continue
        opt = dict(option)
        opt["text_html"] = _render_markdown_html(str(opt.get("text") or ""))
        options_out.append(opt)
    if isinstance(q2.get("options"), list):
        q2["options"] = options_out
    if include_rubric_html:
        q2["rubric_html"] = _render_markdown_html(str(q2.get("rubric") or ""))
    return q2


def build_render_ready_public_spec(
    public_spec: dict[str, Any],
    *,
    include_rubric_html: bool = False,
) -> dict[str, Any]:
    out = copy.deepcopy(public_spec or {})
    questions_out = []
    for q in out.get("questions") or []:
        if not isinstance(q, dict):
            continue
        questions_out.append(
            build_render_ready_question(q, include_rubric_html=include_rubric_html)
        )
    out["questions"] = questions_out
    for translation in (out.get("translations") or {}).values():
        for question in (translation.get("questions") or {}).values():
            question["stem_html"] = _render_markdown_html(str(question.get("stem_md") or ""))
            question["options_html"] = {key: _render_markdown_html(text) for key, text in (question.get("options") or {}).items()}
    return out
