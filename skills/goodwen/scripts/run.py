"""由随包启动器或开发环境运行。"""
import os
import sys
from pathlib import Path

if site := os.environ.get("GOODWEN_LOCAL_SITE"):
    sys.path.insert(0, site)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goodwen_local.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
