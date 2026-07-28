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
    def test_build_push_ingest_rows_keeps_only_new_or_reactivated_deals(self):
        active_existing = {
            "source": "ppomppu",
            "source_post_id": "100",
            "source_link": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=100",
        }
        deleted_existing = {
            "source": "quasar",
            "source_post_id": "200",
            "source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/200",
            "deleted_at": "2026-07-10T00:00:00Z",
        }
        existing_map = {
            sync.sync_key(active_existing): active_existing,
            sync.sync_key(deleted_existing): deleted_existing,
        }
        new_row = {
            "source": "ruliweb",
            "source_post_id": "300",
            "source_link": "https://bbs.ruliweb.com/market/board/1020/read/300",
        }
        changed_rows = [
            {**active_existing, "title": "updated active deal"},
            {**deleted_existing, "deleted_at": None, "title": "reactivated deal"},
            new_row,
        ]

        result = sync.build_push_ingest_rows(changed_rows, existing_map)

        self.assertEqual(result, [changed_rows[1], new_row])

    def test_send_push_ingest_posts_active_rows_in_batches_and_logs_counts(self):
        changed_rows = [
            {"id": "active-deal-1", "title": "new deal 1", "deleted_at": None},
            {"id": "active-deal-2", "title": "new deal 2", "deleted_at": None},
            {"id": "deleted-deal", "title": "old deal", "deleted_at": "2026-07-10T00:00:00Z"},
        ]
        posted = []

        def fake_post(url, headers=None, json=None, **kwargs):
            posted.append((url, headers, json, kwargs))
            count = len(json["rows"])
            return Mock(
                ok=True,
                status_code=200,
                text=f'{{"ok":true,"processed":{count},"pushed":{count},"skipped":0,"queued":0,"digests":0}}',
                json=lambda: {"ok": True, "processed": count, "pushed": count, "skipped": 0, "queued": 0, "digests": 0},
            )

        with patch.dict(
            os.environ,
            {
                "PUSH_INGEST_URL": "https://gaji.run/api/push/ingest",
                "PUSH_INGEST_SECRET": "test-secret",
                "PUSH_INGEST_BATCH_SIZE": "1",
                "PUSH_INGEST_MAX_ROWS": "10",
            },
        ), patch.object(sync.requests, "post", side_effect=fake_post):
            result = sync.send_push_ingest(changed_rows)

        self.assertEqual(result, "OK rows=2 sent=2 batches=2 processed=2 pushed=2 skipped=0 queued=0 digests=0")
        self.assertEqual(len(posted), 2)
        self.assertEqual(posted[0][0], "https://gaji.run/api/push/ingest")
        self.assertEqual(posted[0][1]["x-ingest-secret"], "test-secret")
        self.assertEqual(posted[0][2]["rows"], [changed_rows[0]])
        self.assertEqual(posted[1][2]["rows"], [changed_rows[1]])

    def test_send_push_ingest_posts_empty_rows_to_flush_due_digests(self):
        posted = []

        def fake_post(url, headers=None, json=None, **kwargs):
            posted.append((url, headers, json, kwargs))
            return Mock(
                ok=True,
                status_code=200,
                text='{"ok":true,"processed":0,"pushed":1,"skipped":0,"queued":0,"digests":1}',
                json=lambda: {"ok": True, "processed": 0, "pushed": 1, "skipped": 0, "queued": 0, "digests": 1},
            )

        with patch.dict(
            os.environ,
            {
                "PUSH_INGEST_URL": "https://gaji.run/api/push/ingest",
                "PUSH_INGEST_SECRET": "test-secret",
            },
        ), patch.object(sync.requests, "post", side_effect=fake_post):
            result = sync.send_push_ingest([])

        self.assertEqual(result, "OK rows=0 sent=0 batches=1 processed=0 pushed=1 skipped=0 queued=0 digests=1")
        self.assertEqual(posted[0][2]["rows"], [])

    def test_send_push_ingest_skips_without_secret(self):
        with patch.dict(os.environ, {"PUSH_INGEST_URL": "", "PUSH_INGEST_SECRET": ""}):
            self.assertEqual(sync.send_push_ingest([{"id": "deal"}]), "SKIP")


if __name__ == "__main__":
    unittest.main()
