"""每次提交在同一 SQLite 事务内检查版本、会话、游标和题目期限。"""

import json
import time
import uuid
from hashlib import sha256

from .grading import _grade, _normalize_answer
from .library import encode
from .quiz_languages import available_languages, localize_spec, selected_language
from .quiz_rendering import build_render_ready_public_spec


def session_key(secret):
    return sha256(secret.encode("ascii")).hexdigest()


def begin(library, snapshot, secret, preview, language):
    now = time.time()
    chosen = selected_language(snapshot["spec"], language)
    with library.db(write=True) as db:
        db.execute(
            "INSERT OR IGNORE INTO attempt(id,snapshot,session,preview,language,started,question_started) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                snapshot["id"],
                session_key(secret),
                preview,
                chosen,
                now,
                now,
            ),
        )


def visit(
    library,
    snapshot,
    secret,
    preview,
    *,
    action="state",
    qid=None,
    answer=None,
    language=None,
):
    spec = snapshot["spec"]
    questions = spec["questions"]
    with library.db(write=True) as db:
        row = db.execute(
            "SELECT * FROM attempt WHERE session=? AND snapshot=? AND preview=?",
            (session_key(secret), snapshot["id"], preview),
        ).fetchone()
        if not row:
            raise ValueError("请先开始填写")
        row = dict(row)
        answers = json.loads(row["answers"])
        timing = json.loads(row["timing"])
        index = row["cursor"]
        now = time.time()
        back = spec["behavior"]["allow_backtracking"]
        if language and row["submitted"] is None:
            row["language"] = selected_language(spec, language)
            db.execute(
                "UPDATE attempt SET language=? WHERE id=?", (row["language"], row["id"])
            )
        if row["submitted"] is None:
            current = questions[index] if index < len(questions) else None
            deadline = (
                row["question_started"] + current["answer_time_seconds"]
                if current and current.get("answer_time_seconds")
                else None
            )
            if deadline and now >= deadline:
                timing[current["qid"]] = {
                    "timed_out": True,
                    "seconds": current["answer_time_seconds"],
                }
                index += 1
                row["question_started"] = now
            elif action == "answer":
                position = next(
                    (i for i, q in enumerate(questions) if q["qid"] == qid), None
                )
                if (
                    position is None
                    or position > index
                    or (position < index and not back)
                ):
                    raise ValueError("题目状态已变化，请刷新")
                answers[qid] = _normalize_answer(questions[position], answer)
                if position == index:
                    timing[qid] = {
                        "timed_out": False,
                        "seconds": max(0, round(now - row["question_started"], 2)),
                    }
                    index += 1
                    row["question_started"] = now
            elif action == "submit":
                if index != len(questions):
                    raise ValueError("请先完成当前题目")
                score, maximum, details, traits = _grade(spec, answers)
                grading = {
                    "rule_score": score if maximum else None,
                    "rule_score_max": maximum,
                    "details": details,
                    "traits": traits,
                    "subjective_score_max": sum(
                        q.get("max_points", 0)
                        for q in questions
                        if q["type"] == "short"
                    ),
                }
                db.execute(
                    "UPDATE attempt SET submitted=?,grading=? WHERE id=?",
                    (now, encode(grading), row["id"]),
                )
                row["submitted"] = now
            db.execute(
                "UPDATE attempt SET answers=?,timing=?,cursor=?,question_started=? WHERE id=?",
                (
                    encode(answers),
                    encode(timing),
                    index,
                    row["question_started"],
                    row["id"],
                ),
            )
        elif action == "answer":
            raise ValueError("这份答卷已经提交")
        public = localize_spec(snapshot["public"], row["language"])
        visible = (
            public["questions"][: min(index + 1, len(questions))]
            if back
            else public["questions"][index : index + 1]
        )
        public["questions"] = visible if row["submitted"] is None else []
        public = build_render_ready_public_spec(public)
        current = questions[index] if index < len(questions) else None
        deadline = (
            row["question_started"] + current["answer_time_seconds"]
            if current and current.get("answer_time_seconds")
            else None
        )
        return {
            "id": row["id"],
            "submitted": row["submitted"] is not None,
            "cursor": index,
            "count": len(questions),
            "deadline": deadline,
            "server_now": now,
            "answers": answers if back else {},
            "spec": public,
            "languages": available_languages(spec),
        }
