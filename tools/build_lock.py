"""从上游发布清单生成固定运行环境。仅维护者升级依赖时运行。"""

import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {
    "linux-x64": ("x86_64-unknown-linux-gnu", "manylinux", "x86_64"),
    "macos-arm64": ("aarch64-apple-darwin", "macosx", "arm64"),
    "windows-x64": ("x86_64-pc-windows-msvc", "win_amd64", "amd64"),
}
PYTHON_TAG = "20261110"
PYTHON_VERSION = "3.12.16"
VERSIONS = {"PyYAML": "6.0.3", "Markdown": "3.5.2", "Pillow": "12.2.0"}


def fetch(url):
    with urlopen(
        Request(url, headers={"User-Agent": "goodwen-local-build"}), timeout=35
    ) as response:
        return json.load(response)


def main():
    release = fetch(
        "https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/"
        + PYTHON_TAG
    )
    wheels = {
        name: fetch(f"https://pypi.org/pypi/{name}/{version}/json")["urls"]
        for name, version in VERSIONS.items()
    }
    lock = {"version": "0.1.1", "platforms": {}}
    for key, (target, os_tag, arch) in PLATFORMS.items():
        filename = f"cpython-{PYTHON_VERSION}+{PYTHON_TAG}-{target}-install_only_stripped.tar.gz"
        asset = next(item for item in release["assets"] if item["name"] == filename)
        runtime = {
            "name": filename,
            "url": asset["browser_download_url"],
            "sha256": asset["digest"].split(":")[1],
        }
        selected = []
        for name, candidates in wheels.items():
            matches = [
                item
                for item in candidates
                if item["filename"].endswith("none-any.whl")
                or (
                    "-cp312-cp312-" in item["filename"]
                    and os_tag in item["filename"]
                    and arch in item["filename"]
                    and item["filename"].endswith(".whl")
                )
            ]
            wheel = sorted(matches, key=lambda x: x["filename"])[0]
            selected.append(
                {
                    "name": wheel["filename"],
                    "url": wheel["url"],
                    "sha256": wheel["digests"]["sha256"],
                }
            )
        lock["platforms"][key] = {"python": runtime, "wheels": selected}
    (ROOT / "skills/goodwen/scripts/runtime-lock.json").write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )
    lines = []
    for platform, config in lock["platforms"].items():
        runtime = config["python"]
        lines.append(
            f"{platform} {runtime['name']} {runtime['sha256']} {runtime['url']}"
        )
    (ROOT / "skills/goodwen/scripts/python-lock.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
