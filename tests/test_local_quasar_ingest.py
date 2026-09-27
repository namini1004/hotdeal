import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
INGEST_SCRIPT = ROOT / "scripts" / "local_quasar_ingest.py"

spec = importlib.util.spec_from_file_location("local_quasar_ingest", INGEST_SCRIPT)
assert spec and spec.loader
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


class LocalQuasarIngestTests(unittest.TestCase):
    def row(self, registered_at=None, **overrides):
        return {
            "source": "quasar", "title": "Product",
            "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/12345",
            "registeredAt": registered_at or datetime.now(timezone.utc).isoformat(),
            **overrides,
        }

    def test_local_collector_uses_requests_first_hybrid_mode(self):
        source = INGEST_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('HOTDEAL_QUASAR_FETCH_MODE", "hybrid"', source)
        self.assertIn('HOTDEAL_QUASAR_IMAGE_FETCH_MODE", "hybrid"', source)

    def test_validate_feed_requires_nonempty_quasar_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            path.write_text(json.dumps({"items": []}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "no items"):
                ingest.validate_feed(path)

            path.write_text(json.dumps({"items": [self.row()]}), encoding="utf-8")
            self.assertEqual(ingest.validate_feed(path), 1)

    def test_validate_feed_rejects_all_expired_future_or_invalid_rows(self):
        now = datetime(2026, 9, 27, 2, tzinfo=timezone.utc)
        rows = [
            self.row((now - timedelta(hours=48, seconds=1)).isoformat()),
            self.row((now + timedelta(minutes=10, seconds=1)).isoformat()),
            self.row("invalid"), self.row("2026-09-27T02:00:00"),
            self.row(now.isoformat(), sourceLink=""),
            self.row(now.isoformat(), title="블라인드 처리된 글입니다."),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            for row in rows:
                with self.subTest(row=row):
                    path.write_text(json.dumps({"items": [row]}), encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, "no valid recent rows"):
                        ingest.validate_feed(path, now)

    def test_validate_feed_counts_only_recent_rows_at_sync_boundaries(self):
        now = datetime(2026, 9, 27, 2, tzinfo=timezone.utc)
        rows = [self.row((now - timedelta(hours=48)).isoformat()),
                self.row((now + timedelta(minutes=10)).isoformat()),
                self.row((now - timedelta(days=4)).isoformat())]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            path.write_text(json.dumps({"items": rows}), encoding="utf-8")
            self.assertEqual(ingest.validate_feed(path, now), 2)

    def test_validate_feed_rejects_wrong_source_and_malformed_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            for row in (self.row(source="ppomppu"), None, "invalid"):
                path.write_text(json.dumps({"items": [row]}), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "another source"):
                    ingest.validate_feed(path)

    def test_valid_row_does_not_allow_missing_timestamps_to_slip_into_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            rows = [self.row(), self.row(registeredAt=None)]
            path.write_text(json.dumps({"items": rows}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "malformed rows"):
                ingest.validate_feed(path)

    def test_main_never_syncs_stale_feed_even_when_parser_exits_successfully(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.test", "SUPABASE_SERVICE_ROLE_KEY": "test",
        }), patch.object(ingest, "load_environment"), patch.object(ingest, "append_log"), patch.object(ingest, "run_step", return_value="") as run:
            path = Path(tmp) / "feed.json"
            path.write_text(json.dumps({"items": [self.row("2026-01-01T00:00:00Z")]}), encoding="utf-8")
            with patch.object(ingest, "FEED_PATH", path), patch.object(ingest, "LOCK_PATH", Path(tmp) / "lock"):
                with self.assertRaisesRegex(RuntimeError, "no valid recent rows"):
                    ingest.main()
            self.assertEqual(run.call_count, 1)
            self.assertIn("scripts/update_quasar_feed.py", run.call_args.args[0])

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
