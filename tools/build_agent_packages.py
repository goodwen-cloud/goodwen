#!/usr/bin/env python3
"""从同一份 Goodwen Skill 构建 ChatGPT 插件与 WorkBuddy 连接器。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from PIL import Image
import yaml


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
SKILL = ROOT / "skills/goodwen"
PLATFORMS = {"goodwen-connector": "workbuddy", "goodwen-chatgpt": "chatgpt"}
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
ENDPOINT = "https://goodwen.cc/mcp"
SKILL_REFERENCES = {"processing.md", "interactions.md", "automation.md"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def shared_files() -> dict[str, Path]:
    entry = SKILL / "SKILL.md"
    body = entry.read_text(encoding="utf-8")
    parts = body.split("---", 2)
    require(len(parts) == 3 and not parts[0], "Skill 缺少 frontmatter")
    meta = yaml.safe_load(parts[1])
    require(meta["name"] == "goodwen" and bool(meta["description"].strip()), "Skill 元数据无效")
    references = {"references/" + name for name in SKILL_REFERENCES}
    links = set(re.findall(r"\]\(([^)]+)\)", body))
    require({link for link in links if not urlsplit(link).scheme} == references, "线上包引用清单不符")
    files = {}
    for relative in {"SKILL.md", *references}:
        path = SKILL / relative
        require(path.is_file() and path == path.resolve(), f"共享 Skill 文件无效: {relative}")
        files[f"skills/goodwen/{relative}"] = path
    return files


def package_files(name: str, shared: dict[str, Path]) -> dict[str, Path]:
    base = PACKAGES / PLATFORMS[name]
    allowed = {"mcp.json", "connector-meta.json", "icon.png"} if name == "goodwen-connector" else {"mcp.json", "plugin.json", "assets/icon.png"}
    paths = list(base.rglob("*"))
    require(base == base.resolve() and not any(path.is_symlink() for path in paths), f"{name} 不允许符号链接")
    files = {path.relative_to(base).as_posix(): path for path in paths if path.is_file()}
    require(files.keys() == allowed, f"{name} 平台文件清单不符")
    return {**files, **shared}


def validate_packages(expected_scopes: set[str] | None) -> dict[str, str]:
    versions = {}
    for name, platform in PLATFORMS.items():
        base = PACKAGES / platform
        config = read_json(base / "mcp.json")
        require(set(config["mcpServers"]) == {"goodwen"}, "每包必须只有 Goodwen 一个 Server")
        server = config["mcpServers"]["goodwen"]
        require(server["url"] == ENDPOINT, "MCP 地址不符")
        if name == "goodwen-connector":
            meta = read_json(base / "connector-meta.json")
            require(server == {"type": "streamableHttp", "url": ENDPOINT, "timeout": 30000}, "WorkBuddy 连接配置不符")
            require(meta["source"] == "goodwen", "WorkBuddy source 必须为 goodwen")
            require(meta.get("auth_mode") == "server-side", "市场版 OAuth 必须声明 server-side")
            auth = meta["server_auth"]
            require(auth["auth_type"] == "mcp_oauth", "市场版使用云端 DCR")
            require(set(auth) == {"auth_type", "data"} and set(auth["data"]) == {"mcp_oauth"}, "DCR 配置不应包含平台维护字段")
            oauth = auth["data"]["mcp_oauth"]
            require(set(oauth) == {"server_url", "scopes"} and oauth["server_url"] == ENDPOINT, "DCR 资源地址或字段不符")
            scopes = oauth["scopes"].split()
            require(bool(scopes) and len(scopes) == len(set(scopes)) and "results:import" not in scopes,
                    "WorkBuddy 默认权限必须唯一，导入历史答卷需另行授权")
            if expected_scopes is not None:
                require(set(scopes) == expected_scopes, "WorkBuddy 默认授权范围与服务端契约不符")
            require(tuple(map(int, meta["minWorkbuddyVersion"].split("."))) >= (4, 24, 0), "云端授权配置需要 WorkBuddy 4.24.0")
            for field in ("name", "name_zh", "name_en", "description", "description_zh", "description_en"):
                require(isinstance(meta[field], str) and bool(meta[field].strip()), f"缺少 {field}")
            for field in ("examples_zh", "examples_en"):
                require(2 <= len(meta[field]) <= 5 and all(isinstance(x, str) and x.strip() for x in meta[field]), f"示例不符: {field}")
            icon = base / "icon.png"
        else:
            meta = read_json(base / "plugin.json")
            require(meta["$schema"] == PLUGIN_SCHEMA and meta["name"] == name, "portable manifest 标识不符")
            require(config["$schema"] == MCP_SCHEMA and server["type"] == "streamable-http", "portable MCP schema/transport 不符")
            require(not set(meta).intersection({"apps", "skills", "mcpServers", "interface"}), "portable manifest 存在旧式顶层声明")
            openai = meta["extensions"]["com.openai"]
            require(not openai.get("apps") and not openai.get("hooks"), "公开上传包不包含 apps/hooks")
            interface = openai["interface"]
            require(0 < len(interface["displayName"]) <= 30 and 0 < len(interface["shortDescription"]) <= 30, "目录名称或副标题超长")
            require(len(interface["longDescription"]) <= 4000, "完整介绍超长")
            require(interface["category"] == "Business & Operations", "分类不符")
            prompts = interface["defaultPrompt"]
            require(1 <= len(prompts) <= 3 and all(0 < len(p) <= 128 and "\n" not in p for p in prompts), "默认提示词不符")
            require(len({" ".join(p.split()) for p in prompts}) == len(prompts), "默认提示词重复")
            for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
                parsed = urlsplit(interface[field])
                require(parsed.scheme == "https" and parsed.netloc == "goodwen.cc", f"公开页面域名不符: {field}")
            # Portable schema 不接受 Server extensions；OAuth 由真实 401/metadata 发现。
            require(server == {"type": "streamable-http", "url": ENDPOINT}, "portable Server 配置不符")
            cases = openai["review"]["test_cases"]
            require(len(cases["positive"]) == 5 and len(cases["negative"]) == 3, "审核用例必须 5 正向 / 3 负向")
            for case in cases["positive"]:
                require(all(isinstance(case[k], str) and case[k].strip() for k in ("description", "prompt", "tools_triggered", "expected_behavior")), "正向用例字段不符")
            for case in cases["negative"]:
                require(all(isinstance(case[k], str) and case[k].strip() for k in ("description", "prompt")), "负向用例字段不符")
            review_prompts = openai["review"]["prompts"]
            require(0 < len(review_prompts) <= 20 and all(isinstance(p, str) and 0 < len(p) <= 4000 for p in review_prompts), "审核提示词不符")
            require(interface["logo"] == interface["composerIcon"] == "./assets/icon.png", "图标引用不符")
            icon = base / "assets/icon.png"
        require(re.fullmatch(r"\d+\.\d+\.\d+", meta["version"]) is not None, "版本必须为 SemVer")
        versions[name] = meta["version"]
        with Image.open(icon) as image:
            require(image.format == "PNG" and image.width == image.height and image.width >= 256, "图标必须为至少 256px 的方形 PNG")
            require(image.mode == "RGBA" and image.getextrema()[3][0] == 0, "图标应保留透明背景")
        require(icon.stat().st_size <= 5 * 1024 * 1024, "图标超过 5 MiB")
    return versions


def build_packages(target: Path, *, expected_scopes: set[str] | None = None) -> list[tuple[Path, dict[str, str]]]:
    target = target.resolve()
    require(not any(target.is_relative_to(p) for p in (PACKAGES, SKILL)), "输出必须位于源码包目录之外")
    shared = shared_files()
    versions = validate_packages(expected_scopes)
    target.mkdir(parents=True, exist_ok=True)
    checksums = []
    downloads = []
    for name, version in versions.items():
        archive = target / f"{name}-{version}.zip"
        files = package_files(name, shared)
        expected = {}
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_file:
            for relative, path in sorted(files.items()):
                data = path.read_bytes()
                info = ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zip_file.writestr(info, data)
                expected[relative] = data
        with ZipFile(archive) as zip_file:
            require(zip_file.testzip() is None, f"ZIP CRC 错误: {name}")
            require(set(zip_file.namelist()) == set(expected), f"ZIP 清单不符: {name}")
            require(all(zip_file.read(p) == data for p, data in expected.items()), f"ZIP 内容不符: {name}")
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksums.append(f"{checksum}  {archive.name}")
        if name == "goodwen-connector":
            description = read_json(PACKAGES / "workbuddy/connector-meta.json")["description_zh"]
            platform, platform_name = "workbuddy", "WorkBuddy"
        else:
            description = read_json(PACKAGES / "chatgpt/plugin.json")["extensions"]["com.openai"]["publication"]["translations"]["zh-CN"]["subtitle"]
            platform, platform_name = "chatgpt", "ChatGPT"
        downloads.append((archive, {
            "id": f"{platform}-{version}", "platform": platform, "platform_name": platform_name,
            "version": version, "description": description,
        }))
    (target / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return downloads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/agents")
    args = parser.parse_args()
    for archive, _ in build_packages(args.output_dir):
        print(archive.name)


if __name__ == "__main__":
    main()
