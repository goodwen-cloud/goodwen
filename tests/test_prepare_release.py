import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from skills.goodwen.scripts.goodwen_local import __version__
from tools.prepare_release import ROOT, SHARED_FILES, prepare


class ReleaseManifestTest(unittest.TestCase):
    def test_public_manifest_matches_all_five_archives_and_rejects_changed_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            artifacts = work / "artifacts"
            lock = json.loads((ROOT / "skills/goodwen/scripts/runtime-lock.json").read_bytes())
            self.assertEqual(lock["version"], __version__)
            for group in [*lock["platforms"], "chatgpt", "workbuddy"]:
                online = group in {"chatgpt", "workbuddy"}
                folder = artifacts / ("goodwen-agents" if online else "goodwen-" + group)
                folder.mkdir(parents=True, exist_ok=True)
                prefix = "skills/goodwen/" if online else "goodwen/"
                if online:
                    metadata = "plugin.json" if group == "chatgpt" else "connector-meta.json"
                    data = (ROOT / "packages" / group / metadata).read_bytes()
                    name = "goodwen-chatgpt" if group == "chatgpt" else "goodwen-connector"
                    filename = f"{name}-{json.loads(data)['version']}.zip"
                else:
                    metadata = prefix + "scripts/runtime-lock.json"
                    data = json.dumps(lock).encode()
                    filename = f"goodwen-local-{lock['version']}-{group}.zip"
                archive = folder / filename
                with ZipFile(archive, "w") as package:
                    package.writestr(metadata, data)
                    for name in SHARED_FILES:
                        package.write(ROOT / "skills/goodwen" / name, prefix + name)
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                with (folder / "SHA256SUMS").open("a") as sums:
                    sums.write(f"{digest}  {filename}\n")
            output = work / "release"
            prepare(artifacts, output)
            manifest = json.loads((output / "release-manifest.json").read_bytes())
            self.assertEqual(set(manifest["packages"]), {*lock["platforms"], "chatgpt", "workbuddy"})
            self.assertEqual(len(manifest["commit"]), 40)
            for platform, item in manifest["packages"].items():
                self.assertEqual(item["version"], __version__)
                self.assertEqual(item["file"], f"goodwen-{platform}.zip")
                self.assertEqual(item["sha256"], hashlib.sha256((output / item["file"]).read_bytes()).hexdigest())
            for name in SHARED_FILES:
                self.assertEqual(manifest["shared"][name], hashlib.sha256((ROOT / "skills/goodwen" / name).read_bytes()).hexdigest())
            # 即使构建目录内的 ZIP 与其校验清单相符，错误的共享正文仍应阻止发布。
            with ZipFile(archive) as package:
                entries = {name: package.read(name) for name in package.namelist()}
            entries[prefix + "references/automation.md"] = b"older instructions"
            with ZipFile(archive, "w") as package:
                for name, value in entries.items():
                    package.writestr(name, value)
            sums = folder / "SHA256SUMS"
            sums.write_text(sums.read_text().replace(digest, hashlib.sha256(archive.read_bytes()).hexdigest()))
            with self.assertRaisesRegex(ValueError, "共用技能"):
                prepare(artifacts, work / "rejected")
