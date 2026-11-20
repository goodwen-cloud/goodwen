"""核对各平台 CI 制品，为 GitHub Release 准备稳定下载名和统一校验清单。"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def prepare(artifacts, output):
    lock = json.loads((ROOT / "skills/goodwen/scripts/runtime-lock.json").read_text(encoding="utf-8"))
    version = lock["version"]
    chatgpt = json.loads((ROOT / "packages/chatgpt/plugin.json").read_text(encoding="utf-8"))["version"]
    workbuddy = json.loads((ROOT / "packages/workbuddy/connector-meta.json").read_text(encoding="utf-8"))["version"]
    groups = {
        f"goodwen-{platform}": {f"goodwen-local-{version}-{platform}.zip": f"goodwen-{platform}.zip"}
        for platform in lock["platforms"]
    }
    groups["goodwen-agents"] = {
        f"goodwen-chatgpt-{chatgpt}.zip": "goodwen-chatgpt.zip",
        f"goodwen-connector-{workbuddy}.zip": "goodwen-workbuddy.zip",
    }
    if {p.name for p in artifacts.iterdir()} != set(groups):
        raise ValueError("构建批次未包含完整的平台组")
    skill = (ROOT / "skills/goodwen/SKILL.md").read_bytes()
    verified = []
    for group, names in groups.items():
        folder = artifacts / group
        if {p.name for p in folder.iterdir()} != {*names, "SHA256SUMS"}:
            raise ValueError(f"{group} 制品清单不符")
        checks = (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        entry = "skills/goodwen/SKILL.md" if group == "goodwen-agents" else "goodwen/SKILL.md"
        for filename, public_name in names.items():
            source = folder / filename
            with source.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if f"{digest}  {filename}" not in checks:
                raise ValueError(f"{filename} 的 SHA-256 与构建回执不一致")
            with ZipFile(source) as package:
                if package.testzip() or package.read(entry) != skill:
                    raise ValueError(f"{filename} 未通过 ZIP 或共用技能校验")
            verified.append((source, public_name, digest))
    output.mkdir(parents=True, exist_ok=False)
    for source, name, _ in verified:
        shutil.copyfile(source, output / name)
    sums = [f"{digest}  {name}" for _, name, digest in verified]
    (output / "SHA256SUMS").write_text("\n".join(sorted(sums)) + "\n", encoding="utf-8")
    notes = f"""用 Goodwen 制作问卷，在本机试填、现场收卷，或发布到 goodwen.cc 给外部填写者。

| 安装入口 | 版本 | 选择的文件 |
| --- | --- | --- |
| Windows x64、macOS Apple Silicon、Linux x64（glibc） | {version} | 对应系统的 `goodwen-<系统>-<架构>.zip` |
| ChatGPT | {chatgpt} | `goodwen-chatgpt.zip` |
| WorkBuddy | {workbuddy} | `goodwen-workbuddy.zip` |

本地包已附运行环境。在 Assets 下载对应 ZIP，用同页的 `SHA256SUMS` 核对文件。
[图文操作教程](https://github.com/goodwen-cloud/goodwen/blob/v{version}/docs/guide.md) · [注册并打开 Goodwen](https://goodwen.cc/login)
"""
    (output / "notes.md").write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.artifacts, args.output)
