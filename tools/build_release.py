"""按锁定的原生 CPython 与 wheel 构建可离线安装的 Skill。"""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/goodwen-local"
LOCK = json.loads((SKILL / "scripts/runtime-lock.json").read_text())


def fetch(asset, cache):
    path = cache / asset["name"]
    if (
        path.exists()
        and hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        == asset["sha256"]
    ):
        return path
    request = Request(asset["url"], headers={"User-Agent": "goodwen-local-release"})
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as pending:
        tmp = Path(pending.name)
        try:
            with urlopen(request, timeout=120) as response:
                shutil.copyfileobj(response, pending)
            pending.flush()
            with tmp.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != asset["sha256"]:
                    raise ValueError(f"制品摘要不符 {path.name}")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, path)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--platform", choices=list(LOCK["platforms"]), action="append")
    args = parser.parse_args()
    cache = Path.home() / ".cache/goodwen-local-build"
    cache.mkdir(parents=True, exist_ok=True)
    platforms = args.platform or list(LOCK["platforms"])
    assets = {
        x["name"]: x
        for os_name in platforms
        for x in [
            LOCK["platforms"][os_name]["python"],
            *LOCK["platforms"][os_name]["wheels"],
        ]
    }
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda x: fetch(x, cache), assets.values()))
    if args.fetch_only:
        return
    target = ROOT / "dist"
    target.mkdir(exist_ok=True)
    checksums = []
    for os_name in platforms:
        config = LOCK["platforms"][os_name]
        archive = target / f"goodwen-local-{LOCK['version']}-{os_name}.zip"
        with ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted(SKILL.rglob("*")):
                if (
                    path.is_file()
                    and "__pycache__" not in path.parts
                    and path.suffix != ".pyc"
                ):
                    package.write(
                        path, "goodwen-local/" + path.relative_to(SKILL).as_posix()
                    )
            for name in ("LICENSE", "NOTICE", "docs/build-plan.md"):
                package.write(ROOT / name, "goodwen-local/" + name)
            readme = ROOT / "README.md"
            offline_readme = readme.read_text(encoding="utf-8").replace(
                "(skills/goodwen-local/references/cloud.md)", "(references/cloud.md)"
            )
            package.writestr(
                zipfile.ZipInfo.from_file(readme, "goodwen-local/README.md"),
                offline_readme,
                compress_type=zipfile.ZIP_DEFLATED,
            )
            for asset in [config["python"], *config["wheels"]]:
                package.write(
                    cache / asset["name"],
                    "goodwen-local/offline/" + asset["name"],
                    compress_type=zipfile.ZIP_STORED,
                )
    for archive in sorted(target.glob(f"goodwen-local-{LOCK['version']}-*.zip")):
        with archive.open("rb") as stream:
            checksums.append(
                hashlib.file_digest(stream, "sha256").hexdigest() + "  " + archive.name
            )
    (target / "SHA256SUMS").write_text("\n".join(checksums) + "\n")


if __name__ == "__main__":
    main()
