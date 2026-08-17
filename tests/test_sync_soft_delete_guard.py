import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
spec = importlib.util.spec_from_file_location("sync_hotdeals_to_supabase", SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncSoftDeleteGuardTests(unittest.TestCase):
    def test_blinded_quasar_rows_are_excluded_and_deleted_by_policy(self):
        blinded = {
            "id": "row-id",
            "source": "quasar",
            "source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/1",
            "title": "블라인드 처리된 글입니다.",
            "deleted_at": None,
        }

        self.assertTrue(sync.is_excluded_feed_item(blinded))
        deleted = sync.build_policy_delete_rows([blinded], "2026-08-17T00:00:00+00:00")
        self.assertEqual([row["id"] for row in deleted], ["row-id"])

    def test_naver_default_image_applies_only_when_image_is_missing(self):
        rows = [
            {"title": "[네이버페이] 일일 적립", "img": "", "detail_img": ""},
            {"title": "[네이버] 상품", "img": "https://example.test/product.jpg"},
            {"title": "[지마켓] 상품", "img": ""},
        ]

        changed = sync.apply_curated_default_images(rows, "https://example.supabase.co")

        self.assertEqual(changed, 1)
        self.assertIn("/defaults/naver-thumb-v1.webp", rows[0]["img"])
        self.assertIn("/defaults/naver-detail640-v1.webp", rows[0]["detail_img"])
        self.assertEqual(rows[1]["img"], "https://example.test/product.jpg")
        self.assertEqual(rows[2]["img"], "")

    def test_row_changed_treats_equivalent_timestamp_offsets_as_equal(self):
        new_row = {"registered_at": "2026-08-17T09:00:00+09:00"}
        old_row = {"registered_at": "2026-08-17T00:00:00+00:00"}

        self.assertFalse(sync.row_changed(new_row, old_row))

    def test_partial_snapshot_marks_source_as_delete_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "quasar.json"
            feed.write_text(
                json.dumps(
                    {
                        "sourceKey": "quasar",
                        "partialSnapshot": True,
                        "items": [{"source": "quasar", "sourceLink": "https://example.test/1"}],
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(sync, "FEED_FILES", [feed]):
                rows, protected_sources = sync.load_feed_data()

        self.assertEqual(len(rows), 1)
        self.assertEqual(protected_sources, {"quasar"})

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

    def test_sparse_current_source_does_not_soft_delete_existing_rows(self):
        rows = [
            {
                "source": "fmkorea",
                "source_post_id": str(idx),
                "source_link": f"https://m.fmkorea.com/?mid=hotdeal&document_srl={idx}",
                "title": f"existing fmkorea {idx}",
                "img": "",
                "detail_img": "",
                "registered_at": "2026-05-29T00:00:00+00:00",
            }
            for idx in (100, 101)
        ]
        existing_map = {
            f"fmkorea::post::{idx}": {
                "id": idx,
                "source": "fmkorea",
                "source_post_id": str(idx),
                "source_link": f"https://m.fmkorea.com/?mid=hotdeal&document_srl={idx}",
                "title": f"existing fmkorea {idx}",
                "img": "",
                "detail_img": "",
                "registered_at": "2026-05-29T00:00:00+00:00",
                "deleted_at": None,
            }
            for idx in range(100, 130)
        }

        changed_rows, deleted_rows, skipped_sources = sync.build_sync_plan(
            rows,
            existing_map,
            "2026-05-29T01:00:00+00:00",
            prune_before=sync.datetime(2026, 5, 27, 0, 0, tzinfo=sync.timezone.utc),
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

    def test_future_delete_rows_remove_active_feed_rows(self):
        rows = [
            {
                "id": 10,
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=10200694703",
                "registered_at": "2026-10-17T00:00:00+09:00",
                "deleted_at": None,
            },
            {
                "id": 11,
                "source": "fmkorea",
                "source_link": "https://m.fmkorea.com/?mid=hotdeal&document_srl=10200694704",
                "registered_at": "2026-08-16T02:55:00+00:00",
                "deleted_at": None,
            },
        ]

        deleted_rows = sync.build_future_delete_rows(
            rows,
            "2026-08-16T03:00:00+00:00",
            sync.datetime(2026, 8, 16, 3, 10, tzinfo=sync.timezone.utc),
        )

        self.assertEqual([row["id"] for row in deleted_rows], [10])

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
