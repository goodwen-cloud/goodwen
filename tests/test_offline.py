import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/goodwen"
sys.path.insert(0, str(SKILL / "scripts"))
from goodwen_local.bundle import prepare_bundle
from goodwen_local.cli import export
from goodwen_local.library import Library
from goodwen_local.webserver import Application


class Browser:
    def __init__(self):
        self.client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def call(self, url, data=None):
        body = json.dumps(data).encode() if data is not None else None
        request = Request(url, data=body, headers={"Content-Type": "application/json"})
        with self.client.open(request, timeout=5) as response:
            return json.load(response)


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.path = self.root / "source/quiz.md"
        shutil.copytree(SKILL / "examples/feedback", self.path.parent)
        self.library = Library(self.root / "data")
        self.snapshot = self.library.save(self.path)["snapshot_id"]

    def test_bundle_preserves_inline_code_and_binds_picture_bytes(self):
        text = self.path.read_text(encoding="utf-8")
        inline = "`![示例](assets/visit.png)`"
        text = text.replace(
            "这次到访的整体体验如何？",
            f"这次到访的整体体验如何？\n{inline}\n![照片](assets/visit.png)",
        )
        self.path.write_text(text, encoding="utf-8")
        snapshot = self.library.snapshot(self.library.save(self.path)["snapshot_id"])
        source, images, digest = prepare_bundle(self.library, snapshot)
        expected = "assets/" + images[0]["hash"] + ".png"
        self.assertIn(inline, source)
        self.assertIn(f"![照片]({expected})", source)
        self.assertIn(f"./{expected}", source)
        self.assertEqual(len(digest), 64)
        self.assertNotEqual(self.snapshot, snapshot["id"])
        self.assertEqual(self.library.save(self.path)["snapshot_id"], snapshot["id"])

    def test_local_only_save_with_connected_workspace_runs_offline(self):
        env = {**os.environ, "GOODWEN_LOCAL_HOME": str(self.library.home), "PATH": ""}
        runner = [sys.executable, str(SKILL / "scripts/run.py")]
        self.library.set_pref("workspace", "connected-personal-workspace")
        subprocess.run(
            [*runner, "local-only", self.snapshot, "on"],
            env=env,
            capture_output=True,
            check=True,
        )
        saved = subprocess.check_output([*runner, "save", str(self.path)], env=env)
        self.assertTrue(json.loads(saved)["local_only"])
        self.assertNotIn("cloud", json.loads(saved))

    def test_two_concurrent_browsers_preview_restart_and_export(self):
        app = Application(self.library)
        thread = threading.Thread(target=app.author.serve_forever)
        thread.start()
        try:
            preview = f"{app.origin}/preview/{self.snapshot}/"
            shared = Browser().call(preview + "share", {})["url"]
            self.assertNotIn("managed_count", Browser().call(shared + "info"))
            with self.assertRaises(HTTPError) as denied:
                Browser().call(shared.split("/q/")[0] + "/control/status")
            self.assertEqual(denied.exception.code, 404)
            rendezvous = threading.Barrier(2, timeout=5)

            def answer(url, choice, note, language, parallel):
                browser = Browser()
                first = browser.call(url + "begin", {"language": language})
                if parallel:
                    rendezvous.wait()
                self.assertEqual(first["spec"]["language"], language)
                self.assertNotIn("rubric", first["spec"]["questions"][0])
                browser.call(url + "answer", {"qid": "Q1", "answer": choice})
                self.assertEqual(browser.call(url + "state")["cursor"], 1)
                browser.call(url + "answer", {"qid": "Q2", "answer": note})
                done = browser.call(url + "submit", {})
                self.assertTrue(done["submitted"])
                after = browser.call(
                    url + "language",
                    {"language": "en" if language == "zh-CN" else "zh-CN"},
                )
                self.assertEqual(after["spec"]["language"], language)
                self.assertEqual(browser.call(url + "submit", {})["id"], done["id"])
                return done["id"]

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = [
                    pool.submit(answer, shared, "A", "第一位", "zh-CN", True),
                    pool.submit(answer, shared, "B", "Second visitor", "en", True),
                ]
                ids = {result.result(timeout=12) for result in results}
            self.assertEqual(len(ids), 2)
            self.assertNotIn(answer(preview, "A", "作者试填", "zh-CN", False), ids)
        finally:
            app.author.shutdown()
            thread.join()
            app.close()
        reopened = Library(self.library.home)
        restored = Application(reopened)
        try:
            self.assertEqual(restored.share(self.snapshot), shared)
            self.assertEqual(Browser().call(shared + "info")["count"], 2)
        finally:
            restored.close()
        rows = reopened.responses(self.snapshot)
        self.assertEqual({row["id"] for row in rows}, ids)
        self.assertEqual(
            {row["answers"]["Q2"] for row in rows}, {"第一位", "Second visitor"}
        )
        report = self.root / "responses.csv"
        self.assertEqual(export(rows, report, "csv")["count"], 2)
        with report.open(encoding="utf-8-sig", newline="") as source:
            self.assertEqual(
                {row["Q2"] for row in csv.DictReader(source)},
                {"第一位", "Second visitor"},
            )
        self.path.write_text(
            self.path.read_text(encoding="utf-8").replace("还可以改进", "尚可"),
            encoding="utf-8",
        )
        latest = reopened.save(self.path)["snapshot_id"]
        self.assertNotEqual(self.snapshot, latest)
        self.assertEqual(reopened.responses(latest), [])


if __name__ == "__main__":
    unittest.main()
