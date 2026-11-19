"""发布版本中填写规则与参与者文案的唯一读取口径。"""
from __future__ import annotations

from typing import Any
from copy import deepcopy
from .quiz_languages import participant_content, public_translations, normalize_language


def quiz_behavior(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema_version") == 3:
        return spec["behavior"]
    # 冻结的历史版本维持原有逐题限时行为。
    return {"allow_backtracking": False, "timing": {"mode": "per_question"}}


def participant_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """历史 public_spec 也可能含内部简介，必须在对外出口剔除。"""
    result = deepcopy(spec)
    result.pop("description", None)
    result.pop("llm", None)
    result.pop("trait", None)
    result["language"] = normalize_language(spec.get("language"))
    result["translations"] = public_translations(spec.get("translations"))
    for question in result.get("questions") or []:
        for key in ("rubric", "rubric_html", "llm", "correct_answers"):
            question.pop(key, None)
        for option in question.get("options") or []:
            for key in ("correct", "points", "traits"):
                option.pop(key, None)
    result["participant"] = participant_content(spec)
    result["behavior"] = quiz_behavior(spec)
    return result
