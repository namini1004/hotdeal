import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
spec = importlib.util.spec_from_file_location("sync_hotdeals_to_supabase", SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class PushIngestSyncTests(unittest.TestCase):
    def test_send_push_ingest_posts_active_rows_and_logs_response(self):
        changed_rows = [
            {"id": "active-deal", "title": "new deal", "deleted_at": None},
            {"id": "deleted-deal", "title": "old deal", "deleted_at": "2026-07-10T00:00:00Z"},
        ]
        posted = []

        def fake_post(url, headers=None, json=None, **kwargs):
            posted.append((url, headers, json, kwargs))
            return Mock(ok=True, status_code=200, text='{"ok":true,"processed":1,"pushed":1}')

        with patch.dict(
            os.environ,
            {
                "PUSH_INGEST_URL": "https://gaji.run/api/push/ingest",
                "PUSH_INGEST_SECRET": "test-secret",
            },
        ), patch.object(sync.requests, "post", side_effect=fake_post):
            result = sync.send_push_ingest(changed_rows)

        self.assertEqual(result, 'OK {"ok":true,"processed":1,"pushed":1}')
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0][0], "https://gaji.run/api/push/ingest")
        self.assertEqual(posted[0][1]["x-ingest-secret"], "test-secret")
        self.assertEqual(posted[0][2]["rows"], [changed_rows[0]])

    def test_send_push_ingest_skips_without_rows_or_secret(self):
        with patch.dict(os.environ, {"PUSH_INGEST_URL": "", "PUSH_INGEST_SECRET": ""}):
            self.assertEqual(sync.send_push_ingest([{"id": "deal"}]), "SKIP")

        with patch.dict(
            os.environ,
            {
                "PUSH_INGEST_URL": "https://gaji.run/api/push/ingest",
                "PUSH_INGEST_SECRET": "test-secret",
            },
        ):
            self.assertEqual(sync.send_push_ingest([]), "SKIP")


if __name__ == "__main__":
    unittest.main()
