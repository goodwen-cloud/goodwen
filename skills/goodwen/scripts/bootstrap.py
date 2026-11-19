"""使用锁定原生解释器准备依赖，再启动同一 Skill 内的入口。"""

import hashlib
import json
import os
import runpy
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

scripts = Path(__file__).resolve().parent
lock = json.loads((scripts / "runtime-lock.json").read_text(encoding="utf-8"))
platform, cache = sys.argv[1], Path(sys.argv[2])
dest = cache / (
    "site-"
    + hashlib.sha256((scripts / "runtime-lock.json").read_bytes()).hexdigest()[:16]
)
if not dest.is_dir():
    with tempfile.TemporaryDirectory(dir=cache) as work:
        folder = Path(work) / "packages"
        folder.mkdir()
        for wheel in lock["platforms"][platform]["wheels"]:
            offline = scripts.parent / "offline" / wheel["name"]
            path = offline
            if not offline.is_file():
                path = Path(work) / wheel["name"]
                with (
                    urlopen(
                        Request(wheel["url"], headers={"User-Agent": "goodwen-local"}),
                        timeout=45,
                    ) as src,
                    path.open("wb") as out,
                ):
                    shutil.copyfileobj(src, out)
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != wheel["sha256"]:
                    raise SystemExit("依赖校验失败 " + wheel["name"])
            with ZipFile(path) as content:
                content.extractall(folder)
        try:
            folder.rename(dest)
        except OSError:
            if not dest.is_dir():
                raise
os.environ["GOODWEN_LOCAL_SITE"] = str(dest)
entry = str(scripts / "run.py")
sys.argv = [entry, *sys.argv[3:]]
runpy.run_path(entry, run_name="__main__")
