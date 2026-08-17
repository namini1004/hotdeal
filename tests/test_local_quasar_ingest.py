import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INGEST_SCRIPT = ROOT / "scripts" / "local_quasar_ingest.py"

spec = importlib.util.spec_from_file_location("local_quasar_ingest", INGEST_SCRIPT)
assert spec and spec.loader
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


class LocalQuasarIngestTests(unittest.TestCase):
    def test_validate_feed_requires_nonempty_quasar_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            path.write_text(json.dumps({"items": []}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "no items"):
                ingest.validate_feed(path)

            path.write_text(json.dumps({"items": [{"source": "quasar"}]}), encoding="utf-8")
            self.assertEqual(ingest.validate_feed(path), 1)

    def test_quasar_updater_accepts_untracked_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "quasar.json"
            env = os.environ.copy()
            env["HOTDEAL_QUASAR_JSON_PATH"] = str(output_path)
            script = "from scripts.update_quasar_feed import JSON_PATH; print(JSON_PATH)"

            actual = subprocess.check_output([sys.executable, "-c", script], cwd=ROOT, env=env, text=True).strip()

            self.assertEqual(Path(actual), output_path)


if __name__ == "__main__":
    unittest.main()
