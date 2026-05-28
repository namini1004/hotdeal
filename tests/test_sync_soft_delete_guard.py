import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
spec = importlib.util.spec_from_file_location("sync_hotdeals_to_supabase", SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncSoftDeleteGuardTests(unittest.TestCase):
    def test_zero_item_source_does_not_soft_delete_existing_rows(self):
        rows = [
            {
                "source": "ppomppu",
                "source_link": "https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&no=1",
                "title": "existing ppomppu",
                "img": "",
                "detail_img": "",
            }
        ]
        existing_map = {
            "ppomppu::https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&no=1": {
                "source": "ppomppu",
                "source_link": "https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&no=1",
                "title": "existing ppomppu",
                "img": "",
                "detail_img": "",
                "deleted_at": None,
            },
            "fmkorea::https://m.fmkorea.com/?mid=hotdeal&document_srl=123": {
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123",
                "title": "old fmkorea",
                "img": "",
                "detail_img": "",
                "deleted_at": None,
            },
        }

        changed_rows, deleted_rows, skipped_sources = sync.build_sync_plan(rows, existing_map, "2026-05-29T00:00:00+00:00")

        self.assertEqual(changed_rows, [])
        self.assertEqual(deleted_rows, [])
        self.assertIn("fmkorea", skipped_sources)

    def test_source_with_current_rows_still_soft_deletes_missing_rows(self):
        rows = [
            {
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=456",
                "title": "new fmkorea",
                "img": "",
                "detail_img": "",
            }
        ]
        existing_map = {
            "fmkorea::https://m.fmkorea.com/?mid=hotdeal&document_srl=123": {
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123",
                "title": "old fmkorea",
                "img": "",
                "detail_img": "",
                "deleted_at": None,
            }
        }

        changed_rows, deleted_rows, skipped_sources = sync.build_sync_plan(rows, existing_map, "2026-05-29T00:00:00+00:00")

        self.assertEqual(len(changed_rows), 1)
        self.assertEqual(len(deleted_rows), 1)
        self.assertEqual(deleted_rows[0]["source"], "fmkorea")
        self.assertNotIn("fmkorea", skipped_sources)


if __name__ == "__main__":
    unittest.main()
