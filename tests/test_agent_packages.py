import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.build_agent_packages import build_packages


ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_both_archives_ship_the_canonical_skill_and_only_their_platform_files(self):
        common = {
            "skills/goodwen/SKILL.md",
            "skills/goodwen/references/automation.md",
            "skills/goodwen/references/interactions.md",
            "skills/goodwen/references/processing.md",
        }
        platform_files = {
            "chatgpt": {"plugin.json", "mcp.json", "assets/icon.png"},
            "workbuddy": {"connector-meta.json", "mcp.json", "icon.png"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            builds = build_packages(target)
            self.assertEqual({meta["platform"] for _, meta in builds}, set(platform_files))
            sums = {}
            for archive, metadata in builds:
                platform = metadata["platform"]
                with self.subTest(platform=platform), ZipFile(archive) as package:
                    config = json.loads(package.read("mcp.json"))
                    self.assertEqual(config["mcpServers"]["goodwen"]["url"], "https://goodwen.cc/mcp")
                    self.assertCountEqual(package.namelist(), common | platform_files[platform])
                    for name in common:
                        self.assertEqual(package.read(name), (ROOT / name).read_bytes())
                    for name in platform_files[platform]:
                        self.assertEqual(package.read(name), (ROOT / "packages" / platform / name).read_bytes())
                sums[archive.name] = hashlib.sha256(archive.read_bytes()).hexdigest()
            for line in (target / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split()
                self.assertEqual(sums.pop(name), digest)
            self.assertFalse(sums)
