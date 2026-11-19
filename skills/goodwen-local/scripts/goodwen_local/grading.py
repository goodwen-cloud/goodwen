from typing import Any
from .grading_traits import _aggregate_traits


def _normalize_answer(question: dict[str, Any], raw: Any) -> str | list[str]:
    qtype = str(question.get("type") or "")
    legal = {str(item.get("key") or "") for item in (question.get("options") or [])}
    if qtype == "single":
        value = str(raw or "").strip()
        if value not in legal:
            raise ValueError("单选答案无效")
        return value
    if qtype == "multiple":
        values = raw if isinstance(raw, list) else [raw]
        normalized = sorted({str(item or "").strip() for item in values if str(item or "").strip()})
        if not normalized or any(value not in legal for value in normalized):
            raise ValueError("多选答案无效")
        return normalized
    if qtype == "short":
        value = str(raw or "").strip()
        if not value:
            raise ValueError("简答内容不能为空")
        if len(value) > 20000:
            raise ValueError("简答内容不能超过 20000 个字符")
        return value
    raise ValueError("不支持的题型")


def _grade(
    spec: dict[str, Any],
    answers: dict[str, Any],
) -> tuple[int, int, list[dict[str, Any]], dict[str, Any] | None]:
    total = 0
    scored = 0
    grading: list[dict[str, Any]] = []
    trait_questions: list[dict[str, Any]] = []
    for question in spec.get("questions") or []:
        qid = str(question.get("qid") or "")
        qtype = str(question.get("type") or "")
        if qtype == "short" or question.get("scoring_mode") == "none":
            # Subjective answers are frozen separately and never enter the
            # deterministic rule score.
            continue
        if qtype not in {"single", "multiple"}:
            raise ValueError("问卷或测评版本包含不支持的题型")
        max_points = int(question.get("max_points") or question.get("points") or 0)
        selected_raw = answers.get(qid)
        selected = (
            {str(item) for item in selected_raw}
            if isinstance(selected_raw, list)
            else ({str(selected_raw)} if selected_raw not in {None, ""} else set())
        )
        correct = {
            str(option.get("key") or "")
            for option in (question.get("options") or [])
            if option.get("correct")
        }
        mode = str(question.get("scoring_mode") or "")
        if mode == "traits":
            trait_questions.append(question)
            question_score = 0
        elif mode == "completion":
            total += max_points
            question_score = max_points if selected else 0
        elif selected == correct:
            total += max_points
            question_score = max_points
        elif qtype == "multiple" and bool(question.get("partial")) and correct:
            total += max_points
            correct_selected = len(selected & correct)
            wrong_selected = len(selected - correct)
            ratio = max(0.0, (correct_selected - wrong_selected) / len(correct))
            question_score = int(round(max_points * ratio))
        else:
            total += max_points
            question_score = 0
        scored += question_score
        grading.append(
            {
                "question_id": qid,
                "selected": sorted(selected),
                "correct": sorted(correct),
                "score": question_score,
                "score_max": max_points,
                "scoring_mode": mode or "objective",
            }
        )
    traits = (
        _aggregate_traits(spec, {"answers": answers}, trait_questions)
        if trait_questions
        else None
    )
    return scored, total, grading, traits
