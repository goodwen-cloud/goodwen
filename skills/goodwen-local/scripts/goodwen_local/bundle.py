"""把实际图片引用指向不可变内容路径，保留题目、注释和 Markdown 代码示例。"""

import re
from pathlib import PurePosixPath

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from .validation import _validate_plain_source

TARGET = re.compile(
    r"""(?P<prefix>!\[[^\]\n]*\]\(\s*<?|<img\b[^>\n]*?\bsrc\s*=\s*["']?|^\s{0,3}\[[^\]\n]+\]:\s*<?)(?P<path>(?:\./|/)?assets/[^\s<>)"']+)""",
    re.I | re.M,
)
MEDIA = re.compile(
    r"""(\bmedia\s*=\s*["']?)((?:\./|/)?assets/[^,}"']+?)(?=\s*[,}"'])"""
)
CODE = re.compile(r"(`+)(.*?)\1", re.S)
EXT = {
    "image/jpeg": "jpg",
    "image/tiff": "tiff",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
}


def prepare_bundle(lib, snapshot):
    with lib.db() as db:
        resources = [
            dict(row)
            for row in db.execute(
                "SELECT r.path, r.hash, b.mime FROM resource r JOIN blob b USING(hash) "
                "WHERE snapshot=? ORDER BY r.path",
                (snapshot["id"],),
            )
        ]
    mapping = {x["path"]: f"assets/{x['hash']}.{EXT[x['mime']]}" for x in resources}

    def replace_path(value):
        path, separator, fragment = value.partition("#")
        clean = path.removeprefix("./").removeprefix("/")
        if clean not in mapping:
            return value
        prefix = "./" if path.startswith("./") else ""
        return prefix + mapping[clean] + separator + fragment

    def markdown(value):
        def links(s):
            # 带空格的 Markdown 目标与 HTML src 必须先按边界读取。
            def quoted(m):
                return m[1] + replace_path(m[2]) + m[3]

            s = re.sub(
                r"""(!\[[^\]\n]*\]\(\s*<|^\s{0,3}\[[^\]\n]+\]:\s*<)((?:\./|/)?assets/[^>\n]+)(>)""",
                quoted,
                s,
                flags=re.I | re.M,
            )
            s = re.sub(
                r"""(<img\b[^>\n]*?\bsrc\s*=\s*")((?:\./|/)?assets/[^"\n]+)(")""",
                quoted,
                s,
                flags=re.I,
            )
            s = re.sub(
                r"""(<img\b[^>\n]*?\bsrc\s*=\s*')((?:\./|/)?assets/[^'\n]+)(')""",
                quoted,
                s,
                flags=re.I,
            )
            return TARGET.sub(lambda m: m["prefix"] + replace_path(m["path"]), s)

        output = []
        fence = None
        for line in value.splitlines(keepends=True):
            marker = re.match(r"^\s*(`{3,}|~{3,})", line)
            if marker and (not fence or marker[1].startswith(fence)):
                fence = None if fence else marker[1]
                output.append(line)
            elif fence:
                output.append(line)
            else:
                cursor = 0
                for inline in CODE.finditer(line):
                    output.extend([links(line[cursor : inline.start()]), inline[0]])
                    cursor = inline.end()
                output.append(links(line[cursor:]))
        return "".join(output)

    source = snapshot["source"]
    if mapping:
        front = re.match(
            r"^---[^\S\n]*\n(.*?)^---[^\S\n]*(?:\n|$)", source, re.S | re.M
        )
        if not front:
            raise ValueError("缺少 QML Front Matter")
        raw = front[1]
        changes = []
        parents = set()

        def walk(node, keys=()):
            if id(node) in parents:
                raise ValueError("QML 元数据包含循环引用")
            parents.add(id(node))
            if isinstance(node, MappingNode):
                for key, value in node.value:
                    walk(value, (*keys, key.value))
            elif isinstance(node, SequenceNode):
                for item in node.value:
                    walk(item, keys)
            elif isinstance(node, ScalarNode):
                start, end = node.start_mark.index, node.end_mark.index
                original = raw[start:end]
                updated = original
                if keys[-1:] in (("welcome_image",), ("end_image",), ("media",)):
                    updated = original.replace(node.value, replace_path(node.value), 1)
                elif keys[:1] == ("translations",) and (
                    "options" in keys or keys[-1:] == ("stem_md",)
                ):
                    updated = markdown(original)
                if original != updated:
                    changes.append((start, end, updated))
            parents.remove(id(node))

        walk(yaml.compose(raw, Loader=yaml.SafeLoader))
        for start, end, new in sorted(set(changes), reverse=True):
            raw = raw[:start] + new + raw[end:]
        body = markdown(source[front.end() :])
        body = re.sub(
            r"^##[^\n]*\[(?:single|multiple|short)\][^\n]*$",
            lambda m: MEDIA.sub(lambda v: v[1] + replace_path(v[2]), m[0]),
            body,
            flags=re.M,
        )
        source = (
            source[: front.start(1)] + raw + source[front.end(1) : front.end()] + body
        )
    verified = _validate_plain_source(source, asset_paths=frozenset(mapping.values()))
    if verified.validation_issues:
        raise ValueError(
            "图片引用转换未通过 Goodwen 校验 "
            + verified.validation_issues[0]["message"]
        )
    return source, resources, verified.content_digest
