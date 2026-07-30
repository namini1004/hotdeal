import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
spec = importlib.util.spec_from_file_location("sync_hotdeals_to_supabase_storage_gc", SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class StorageGarbageCollectionTests(unittest.TestCase):
    def test_extracts_direct_and_wsrv_storage_paths(self):
        supabase_url = "https://example.supabase.co"
        direct = (
            "https://example.supabase.co/storage/v1/object/public/deal-images/"
            "ppomppu/123-thumb-abc.webp"
        )
        proxied = (
            "https://wsrv.nl/?url=example.supabase.co%2Fstorage%2Fv1%2Fobject%2Fpublic%2F"
            "deal-images%2Fppomppu%2F123-thumb-abc.webp&w=640"
        )

        self.assertEqual(
            sync.storage_object_path_from_url(direct, supabase_url),
            "ppomppu/123-thumb-abc.webp",
        )
        self.assertEqual(
            sync.storage_object_path_from_url(proxied, supabase_url),
            "ppomppu/123-thumb-abc.webp",
        )

    def test_only_old_unreferenced_objects_are_orphans(self):
        cutoff = datetime(2026, 7, 29, tzinfo=timezone.utc)
        objects = [
            {"path": "ppomppu/kept.webp", "updated_at": "2026-07-01T00:00:00Z"},
            {"path": "ppomppu/old.webp", "updated_at": "2026-07-01T00:00:00Z"},
            {"path": "ppomppu/new.webp", "updated_at": "2026-07-30T00:00:00Z"},
        ]

        result = sync.orphan_storage_objects(objects, {"ppomppu/kept.webp"}, cutoff)

        self.assertEqual([item["path"] for item in result], ["ppomppu/old.webp"])

    def test_cleanup_dry_run_never_deletes(self):
        rows = [
            {
                "img": (
                    "https://example.supabase.co/storage/v1/object/public/deal-images/"
                    "ppomppu/kept.webp"
                ),
                "detail_img": "",
            }
        ]
        objects = [
            {
                "path": "ppomppu/kept.webp",
                "updated_at": "2026-07-01T00:00:00Z",
                "metadata": {"size": 100},
            },
            {
                "path": "ppomppu/orphan.webp",
                "updated_at": "2026-07-01T00:00:00Z",
                "metadata": {"size": 200},
            },
        ]

        with patch.object(sync, "list_feed_storage_objects", return_value=objects), patch.object(
            sync, "delete_storage_objects"
        ) as delete_mock, patch.object(
            sync,
            "datetime",
            wraps=sync.datetime,
        ) as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 7, 30, tzinfo=timezone.utc)
            stats = sync.cleanup_orphaned_feed_images(
                "https://example.supabase.co",
                "service-key",
                rows,
                dry_run=True,
                grace_hours=24,
            )

        delete_mock.assert_not_called()
        self.assertEqual(stats["orphans"], 1)
        self.assertEqual(stats["orphan_bytes"], 200)
        self.assertEqual(stats["storage_bytes"], 300)
        self.assertEqual(stats["deleted"], 0)
        self.assertEqual(stats["missing_references"], 0)

    def test_cleanup_stops_when_database_references_a_missing_object(self):
        rows = [
            {
                "img": (
                    "https://example.supabase.co/storage/v1/object/public/deal-images/"
                    "ppomppu/missing.webp"
                ),
                "detail_img": "",
            }
        ]

        with patch.object(sync, "list_feed_storage_objects", return_value=[]), patch.object(
            sync, "delete_storage_objects"
        ) as delete_mock:
            with self.assertRaisesRegex(RuntimeError, "missing=1"):
                sync.cleanup_orphaned_feed_images(
                    "https://example.supabase.co",
                    "service-key",
                    rows,
                )

        delete_mock.assert_not_called()

    def test_bulk_delete_uses_storage_remove_endpoint(self):
        response = Mock(ok=True, status_code=200, text="{}")
        objects = [{"path": f"ppomppu/{index}.webp"} for index in range(3)]

        with patch.object(sync.requests, "delete", return_value=response) as delete_mock:
            deleted = sync.delete_storage_objects(
                objects,
                "https://example.supabase.co",
                "service-key",
            )

        self.assertEqual(deleted, 3)
        delete_mock.assert_called_once()
        self.assertEqual(
            delete_mock.call_args.kwargs["json"],
            {"prefixes": ["ppomppu/0.webp", "ppomppu/1.webp", "ppomppu/2.webp"]},
        )


if __name__ == "__main__":
    unittest.main()
