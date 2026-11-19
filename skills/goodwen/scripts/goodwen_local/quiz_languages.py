"""问卷语言、译文结构与展示投影；不改变题目身份和评分规则。"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

DEFAULT_LANGUAGE = "zh-CN"


@lru_cache(maxsize=1)
def language_resources() -> dict[str, Any]:
    path = Path(__file__).with_name("locales.json")
    return json.loads(path.read_text(encoding="utf-8"))


def language_catalog() -> list[dict[str, str]]:
    return language_resources()["languages"]


def normalize_language(value: Any = None) -> str:
    if value is None:
        return DEFAULT_LANGUAGE
    if isinstance(value, str):
        for item in language_catalog():
            if value.strip().casefold() == item["code"].casefold():
                return item["code"]
    raise ValueError(f"不支持的问卷语言：{value!s}")


def system_text(language: str, key: str) -> str:
    return language_resources()["messages"][normalize_language(language)][key]


def available_languages(spec: dict[str, Any]) -> list[str]:
    base = normalize_language(spec.get("language"))
    return [base, *(item["code"] for item in language_catalog() if item["code"] != base and item["code"] in (spec.get("translations") or {}))]


def selected_language(spec: dict[str, Any], language: str | None = None) -> str:
    chosen = normalize_language(language) if language is not None else normalize_language(spec.get("language"))
    if chosen not in available_languages(spec):
        raise ValueError("该问卷版本未提供所选语言")
    return chosen


def validate_translations(spec: dict[str, Any], value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("translations 必须是语言 mapping")
    base = normalize_language(spec.get("language"))
    questions = {q["qid"]: q for q in spec.get("questions") or []}
    source_participant = spec.get("participant") or {}
    output = {}
    for raw_language, translation in value.items():
        language = normalize_language(raw_language)
        prefix = f"translations.{language}"
        if language == base or language in output:
            raise ValueError(f"{prefix} 重复定义语言")
        if not isinstance(translation, dict) or set(translation) - {"participant", "questions", "welcome_image", "end_image"}:
            raise ValueError(f"{prefix} 只能包含参与者文案、题目译文和图片")
        participant = translation.get("participant")
        if not isinstance(participant, dict) or set(participant) - {"title", "description", "instructions", "completion_message"}:
            raise ValueError(f"{prefix}.participant 必须仅包含对外文案")
        for key in ("title", "description", "completion_message"):
            text = participant.get(key)
            required = key == "title" or bool(source_participant.get(key))
            if (key in participant and not isinstance(text, str)) or (required and not str(text or "").strip()):
                raise ValueError(f"{prefix}.participant.{key} 缺少对应字符串译文")
        instructions = participant.get("instructions", [])
        if not isinstance(instructions, list) or any(not isinstance(item, str) or not item.strip() for item in instructions):
            raise ValueError(f"{prefix}.participant.instructions 必须是非空字符串列表")
        if len(instructions) != len(source_participant.get("instructions") or []):
            raise ValueError(f"{prefix}.participant.instructions 必须逐项对应主语言")
        translated_questions = translation.get("questions")
        if not isinstance(translated_questions, dict) or set(translated_questions) != set(questions):
            missing = sorted(set(questions) - set(translated_questions or {})) if isinstance(translated_questions, dict) else sorted(questions)
            extra = sorted(set(translated_questions) - set(questions)) if isinstance(translated_questions, dict) else []
            raise ValueError(f"{prefix}.questions 题号必须完全对应主语言，缺少：{', '.join(missing)}；多余：{', '.join(extra)}")
        for qid, source in questions.items():
            item = translated_questions[qid]
            path = f"{prefix}.questions.{qid}"
            if not isinstance(item, dict) or set(item) - {"stem_md", "options", "media"}:
                raise ValueError(f"{path} 只能包含 stem_md、options、media")
            if not isinstance(item.get("stem_md"), str) or (source.get("stem_md") and not item["stem_md"].strip()):
                raise ValueError(f"{path}.stem_md 缺少题干译文")
            options = item.get("options", {})
            keys = {o["key"] for o in source.get("options") or []}
            if not isinstance(options, dict) or set(options) != keys:
                raise ValueError(f"{path}.options 选项标识必须完全对应主语言")
            if any(not isinstance(text, str) or not text.strip() for text in options.values()):
                raise ValueError(f"{path}.options 缺少选项译文")
            if "media" in item and not isinstance(item["media"], str):
                raise ValueError(f"{path}.media 必须是图片路径字符串")
        for key in ("welcome_image", "end_image"):
            if key in translation and not isinstance(translation[key], str):
                raise ValueError(f"{prefix}.{key} 必须是图片路径字符串")
        output[language] = deepcopy(translation)
    return output


def public_translations(value: Any) -> dict[str, Any]:
    """各语言独立白名单投影，历史快照也不能携带评分或内部字段。"""
    output = {}
    for language, raw in (value or {}).items():
        if not isinstance(raw, dict):
            continue
        participant = raw.get("participant") or {}
        item = {"participant": {k: deepcopy(v) for k, v in participant.items() if k in {"title", "description", "instructions", "completion_message"}}, "questions": {}}
        for key in ("welcome_image", "end_image"):
            if key in raw:
                item[key] = raw[key]
        for qid, question in (raw.get("questions") or {}).items():
            if isinstance(question, dict):
                item["questions"][qid] = {key: deepcopy(question[key]) for key in ("stem_md", "options", "media") if key in question}
        output[language] = item
    return output


def participant_content(spec: dict[str, Any], language: str | None = None) -> dict[str, Any]:
    chosen = selected_language(spec, language)
    base = normalize_language(spec.get("language"))
    value = (spec.get("participant") or {}) if chosen == base else (spec["translations"][chosen].get("participant") or {})
    return {
        "title": value.get("title") or (spec.get("title") if chosen == base else "") or system_text(chosen, "participate"),
        "description": value.get("description") or "",
        "instructions": list(value.get("instructions") or []),
        "completion_message": value.get("completion_message") or system_text(chosen, "completion"),
    }


def localize_spec(spec: dict[str, Any], language: str | None = None) -> dict[str, Any]:
    chosen = selected_language(spec, language)
    out = deepcopy({key: value for key, value in spec.items() if key != "translations"})
    out["language"] = chosen
    out["participant"] = participant_content(spec, chosen)
    if chosen == normalize_language(spec.get("language")):
        return out
    translation = spec["translations"][chosen]
    for key in ("welcome_image", "end_image"):
        if key in translation:
            out[key] = translation[key]
    for question in out.get("questions") or []:
        item = translation["questions"][question["qid"]]
        for key in ("stem_md", "media", "stem_html"):
            if key in item:
                question[key] = item[key]
        if "stem_html" not in item:
            question.pop("stem_html", None)
        for option in question.get("options") or []:
            option["text"] = item["options"][option["key"]]
            option.pop("text_html", None)
            if option["key"] in item.get("options_html", {}):
                option["text_html"] = item["options_html"][option["key"]]
    return out
