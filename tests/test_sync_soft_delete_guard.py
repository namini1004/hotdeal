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
    def test_source_post_id_extraction_supports_all_feed_sources(self):
        cases = [
            ("ppomppu", "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=6&no=708770", "708770"),
            ("quasar", "https://quasarzone.com/bbs/qb_saleinfo/views/1960291?page=2", "1960291"),
            ("fmkorea", "https://m.fmkorea.com/?mid=hotdeal&document_srl=9941127608", "9941127608"),
            ("fmkorea", "https://www.fmkorea.com/9941127608", "9941127608"),
            ("ruliweb", "https://m.ruliweb.com/market/board/1020/read/104541", "104541"),
        ]

        for source, link, expected in cases:
            self.assertEqual(sync.extract_source_post_id(source, link), expected)

    def test_normalize_sets_source_post_id_and_canonical_source_link(self):
        row = sync.normalize(
            {
                "source": "fmkorea",
                "sourceLink": "https://www.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine&document_srl=9941127608&page=2",
                "title": "deal",
            }
        )

        self.assertEqual(row["source_post_id"], "9941127608")
        self.assertEqual(row["source_link"], "https://m.fmkorea.com/?mid=hotdeal&document_srl=9941127608")

    def test_sync_key_uses_source_post_id_over_source_link_variants(self):
        first = sync.normalize(
            {
                "source": "ppomppu",
                "sourceLink": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=1&no=710000",
                "title": "deal",
            }
        )
        second = sync.normalize(
            {
                "source": "ppomppu",
                "sourceLink": "https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&page=6&no=710000",
                "title": "deal",
            }
        )

        self.assertEqual(sync.sync_key(first), "ppomppu::post::710000")
        self.assertEqual(sync.sync_key(first), sync.sync_key(second))

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

    def test_stale_fallback_source_does_not_soft_delete_newer_database_rows(self):
        rows = [
            {
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123",
                "title": "committed stale fmkorea fallback",
                "img": "",
                "detail_img": "",
            }
        ]
        existing_map = {
            "fmkorea::https://m.fmkorea.com/?mid=hotdeal&document_srl=123": {
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123",
                "title": "committed stale fmkorea fallback",
                "img": "",
                "detail_img": "",
                "deleted_at": None,
            },
            "fmkorea::https://m.fmkorea.com/?mid=hotdeal&document_srl=456": {
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=456",
                "title": "newer database fmkorea row",
                "img": "",
                "detail_img": "",
                "deleted_at": None,
            },
        }

        changed_rows, deleted_rows, skipped_sources = sync.build_sync_plan(
            rows,
            existing_map,
            "2026-05-29T00:00:00+00:00",
            stale_fallback_sources={"fmkorea"},
        )

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

    def test_rows_older_than_prune_window_are_soft_deleted_even_when_source_is_stale(self):
        rows = [
            {
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123",
                "title": "stale fallback fmkorea",
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
                "registered_at": "2026-05-26T00:00:00+00:00",
                "deleted_at": None,
            },
        }

        changed_rows, deleted_rows, skipped_sources = sync.build_sync_plan(
            rows,
            existing_map,
            "2026-05-29T00:00:00+00:00",
            stale_fallback_sources={"fmkorea"},
            prune_before=sync.datetime(2026, 5, 27, 0, 0, tzinfo=sync.timezone.utc),
        )

        self.assertEqual(changed_rows, [])
        self.assertEqual(len(deleted_rows), 1)
        self.assertEqual(deleted_rows[0]["source"], "fmkorea")
        self.assertIn("fmkorea", skipped_sources)

    def test_fmkorea_only_sync_does_not_soft_delete_other_sources(self):
        original_expected = sync.EXPECTED_FEED_SOURCES
        sync.EXPECTED_FEED_SOURCES = {"fmkorea"}
        try:
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

            changed_rows, deleted_rows, skipped_sources = sync.build_sync_plan(
                rows,
                existing_map,
                "2026-05-29T00:00:00+00:00",
            )

            self.assertEqual(len(changed_rows), 1)
            self.assertEqual(len(deleted_rows), 1)
            self.assertEqual(deleted_rows[0]["source"], "fmkorea")
            self.assertNotIn("ppomppu", {row["source"] for row in deleted_rows})
            self.assertEqual(skipped_sources, set())
        finally:
            sync.EXPECTED_FEED_SOURCES = original_expected

    def test_duplicate_active_rows_are_soft_deleted_by_id(self):
        rows = [
            {
                "id": 1,
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123",
                "title": "without image",
                "img": "",
                "detail_img": "",
                "updated_at": "2026-05-29T00:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": 2,
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123",
                "title": "with image",
                "img": "https://example.com/thumb.webp",
                "detail_img": "",
                "updated_at": "2026-05-28T00:00:00+00:00",
                "deleted_at": None,
            },
        ]

        deleted_rows = sync.build_duplicate_delete_rows(rows, "2026-05-29T01:00:00+00:00")

        self.assertEqual(len(deleted_rows), 1)
        self.assertEqual(deleted_rows[0]["id"], 1)
        self.assertEqual(deleted_rows[0]["source"], "fmkorea")

    def test_ppomppu_page_variants_are_soft_deleted_by_canonical_no(self):
        rows = [
            {
                "id": 1,
                "source": "ppomppu",
                "source_link": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=1&no=710000",
                "img": "",
                "detail_img": "",
                "updated_at": "2026-05-29T00:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": 2,
                "source": "ppomppu",
                "source_link": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=6&no=710000",
                "img": "https://example.com/thumb.webp",
                "detail_img": "",
                "updated_at": "2026-05-28T00:00:00+00:00",
                "deleted_at": None,
            },
        ]

        deleted_rows = sync.build_duplicate_delete_rows(rows, "2026-05-29T01:00:00+00:00")

        self.assertEqual(len(deleted_rows), 1)
        self.assertEqual(deleted_rows[0]["id"], 1)

    def test_prune_delete_rows_include_all_old_active_duplicate_ids(self):
        rows = [
            {
                "id": 1,
                "source": "quasar",
                "source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/1",
                "registered_at": "2026-05-26T00:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": 2,
                "source": "quasar",
                "source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/1",
                "registered_at": "2026-05-26T01:00:00+00:00",
                "deleted_at": None,
            },
        ]

        deleted_rows = sync.build_prune_delete_rows(
            rows,
            "2026-05-29T01:00:00+00:00",
            sync.datetime(2026, 5, 27, 0, 0, tzinfo=sync.timezone.utc),
        )

        self.assertEqual({row["id"] for row in deleted_rows}, {1, 2})

    def test_append_id_delete_rows_dedupes_by_id_only(self):
        deleted_rows = [{"id": 1, "source": "ppomppu", "source_link": "same"}]

        sync.append_id_delete_rows(
            deleted_rows,
            [
                {"id": 1, "source": "ppomppu", "source_link": "same"},
                {"id": 2, "source": "ppomppu", "source_link": "same"},
            ],
        )

        self.assertEqual([row["id"] for row in deleted_rows], [1, 2])

    def test_existing_map_prefers_active_row_over_deleted_newer_row(self):
        rows = [
            {
                "id": 1,
                "source": "ppomppu",
                "source_link": "https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&no=1",
                "title": "active older",
                "updated_at": "2026-05-28T00:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": 2,
                "source": "ppomppu",
                "source_link": "https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&no=1",
                "title": "deleted newer",
                "updated_at": "2026-05-29T00:00:00+00:00",
                "deleted_at": "2026-05-29T00:00:00+00:00",
            },
        ]

        existing_map = sync.build_existing_map(rows)

        self.assertEqual(existing_map["ppomppu::post::1"]["id"], 1)


if __name__ == "__main__":
    unittest.main()
