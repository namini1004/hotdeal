import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INGEST_SCRIPT = ROOT / "scripts" / "local_ppomppu_ingest.py"

spec = importlib.util.spec_from_file_location("local_ppomppu_ingest", INGEST_SCRIPT)
assert spec and spec.loader
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


class LocalPpomppuIngestTests(unittest.TestCase):
    def test_validate_feed_requires_nonempty_ppomppu_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            path.write_text(json.dumps({"items": []}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "no items"):
                ingest.validate_feed(path)

            path.write_text(json.dumps({"items": [{"source": "ppomppu"}]}), encoding="utf-8")
            self.assertEqual(ingest.validate_feed(path), 1)

    def test_ppomppu_updater_accepts_untracked_partial_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "ppomppu.json"
            env = os.environ.copy()
            env["HOTDEAL_PPOMPPU_JSON_PATH"] = str(output_path)
            env["HOTDEAL_PPOMPPU_PARTIAL_SNAPSHOT"] = "1"

            path_script = "from scripts.update_ppomppu_feed import JSON_PATH; print(JSON_PATH)"
            actual = subprocess.check_output(
                [sys.executable, "-c", path_script],
                cwd=ROOT,
                env=env,
                text=True,
            ).strip()

            self.assertEqual(Path(actual), output_path)
            updater = (ROOT / "scripts" / "update_ppomppu_feed.py").read_text(encoding="utf-8")
            self.assertIn('"partialSnapshot"', updater)


if __name__ == "__main__":
    unittest.main()
