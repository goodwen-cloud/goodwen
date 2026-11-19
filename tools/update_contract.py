"""从显式指定的 Goodwen 源码更新独立的 Apache-2.0 问卷契约。"""
import argparse
import ast
import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/goodwen"
DEST = SKILL / "scripts/goodwen_local"


def extract(source, names, *, owner=None):
    tree = ast.parse(source)
    body = tree.body if owner is None else next(node.body for node in tree.body if getattr(node, "name", "") == owner)
    items = {node.name: node for node in body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    blocks = []
    for name in names:
        block = textwrap.dedent(ast.get_source_segment(source, items[name]))
        if isinstance(items[name], ast.ClassDef) and items[name].decorator_list:
            block = "@dataclass(frozen=True, slots=True)\n" + block
        elif owner:
            lines = ast.get_source_segment(source, items[name], padded=True)
            block = textwrap.dedent(lines)
        blocks.append(block)
    return "\n\n\n".join(blocks)


def main(source):
    services = source / "backend/md_quiz/services"
    def read(name):
        return (services / (name + ".py")).read_text(encoding="utf-8")
    def save(name, value):
        (DEST / (name + ".py")).write_text(value.rstrip() + "\n", encoding="utf-8")
    for name in ("quiz_metadata", "quiz_languages", "quiz_rules", "quiz_rendering", "grading_traits", "qml"):
        value = (source / "backend/md_quiz/parsers/qml.py").read_text() if name == "qml" else read(name)
        value = value.replace("from backend.md_quiz.services.", "from .")
        value = value.replace('Path(__file__).resolve().parents[3] / "static/take/locales.json"',
                              'Path(__file__).with_name("locales.json")')
        value = value.replace("from backend.md_quiz.config import logger", 'import logging\n\nlogger = logging.getLogger(__name__)')
        if name == "quiz_rendering":
            value = value.partition('_P0_ASSET_SCHEME =')[0]
        save(name, value)
    raster = read("file_security")
    save("images", raster[:raster.index("def _verify_docx")].replace("import zipfile\n", ""))
    contract = read("questionnaire_workflow")
    plain = '''from __future__ import annotations
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any
from .qml import QmlParseError, parse_qml_markdown
from .quiz_metadata import apply_quiz_metadata
from .quiz_rendering import collect_rendered_quiz_image_references, _is_local_asset_path
'''
    constants = [line for line in read("quiz_repository_contract_shared").splitlines() if line.startswith("_FRONTMATTER_ID_RE =")]
    constants += [line for line in contract.splitlines() if line.startswith("_JSON_PROJECTION_MAX_")]
    save("validation", plain + "\n" + "\n".join(constants) + "\n\n" + extract(read("quiz_repository_contract"),
         ["_read_frontmatter_exam_id", "quiz_snapshot_digest"]) + "\n\n" + extract(contract,
         ["_ValidatedSource", "_issue", "_json_projection_issue_code", "_validate_plain_source"]))
    grading = extract(read("p0_participant"), ["_normalize_answer", "_grade"], owner="P0ParticipantService")
    save("grading", "from typing import Any\nfrom .grading_traits import _aggregate_traits\n\n\n" +
         grading.replace("InvalidAnswerError(", "ValueError(").replace("AttemptConflictError(", "ValueError("))
    shutil.copyfile(source / "static/take/locales.json", DEST / "locales.json")
    for filename in ("qml-spec.md", "parser-truth.md"):
        shutil.copyfile(source / "skills/qml-authoring/references" / filename, SKILL / "references" / filename)
    shutil.copyfile(source / "LICENSE", ROOT / "LICENSE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    main(parser.parse_args().upstream)
