import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
DEALS_MODULE = ROOT / "api" / "_lib" / "deals.js"
NODE = shutil.which("node") or str(ROOT / ".tools" / "node-v24.14.0-win-x64" / "node.exe")

spec = importlib.util.spec_from_file_location("sync_hotdeals_to_supabase", SYNC_SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class QuasarImageDeliveryTests(unittest.TestCase):
    def test_hybrid_image_fetch_uses_direct_response_without_starting_browser(self):
        response = Mock(
            ok=True,
            status_code=200,
            content=b"image" * 120,
            headers={"content-type": "image/jpeg"},
        )
        row = {"source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/1"}

        with patch.dict(os.environ, {"HOTDEAL_QUASAR_IMAGE_FETCH_MODE": "hybrid"}), patch.object(
            sync.requests, "get", return_value=response
        ), patch.object(sync, "get_quasar_browser_fetcher") as browser_mock:
            content, content_type = sync.download_feed_image(
                row,
                "quasar",
                "https://img2.quasarzone.com/product.jpg",
            )

        self.assertEqual(content, response.content)
        self.assertEqual(content_type, "image/jpeg")
        browser_mock.assert_not_called()

    def test_hybrid_image_fetch_starts_browser_only_after_direct_failure(self):
        response = Mock(ok=False, status_code=403, content=b"", headers={})
        fetcher = Mock()
        fetcher.capture_image.return_value = b"png" * 200
        row = {"source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/1"}

        with patch.dict(os.environ, {"HOTDEAL_QUASAR_IMAGE_FETCH_MODE": "hybrid"}), patch.object(
            sync.requests, "get", return_value=response
        ), patch.object(sync, "get_quasar_browser_fetcher", return_value=fetcher):
            content, content_type = sync.download_feed_image(
                row,
                "quasar",
                "https://img2.quasarzone.com/product.jpg",
            )

        self.assertEqual(content, b"png" * 200)
        self.assertEqual(content_type, "image/png")
        fetcher.capture_image.assert_called_once()

    def test_quasar_images_are_mirrored_with_source_referer(self):
        headers = sync.IMAGE_HEADERS_BY_SOURCE["quasar"]

        self.assertEqual(headers["Referer"], "https://quasarzone.com/bbs/qb_saleinfo")
        self.assertIn("Mozilla/5.0", headers["User-Agent"])
        self.assertIn("image/", headers["Accept"])

    def test_public_supabase_images_bypass_external_proxy(self):
        module_path = json.dumps(str(DEALS_MODULE))
        storage_url = (
            "https://example.supabase.co/storage/v1/object/public/"
            "deal-images/quasar/1978877-thumb-a1b2c3.webp"
        )
        script = f"""
          const deals = require({module_path});
          console.log(deals.normalizeUserImageUrl({json.dumps(storage_url)}));
        """

        output = subprocess.check_output([NODE, "-e", script], cwd=ROOT, text=True).strip()

        self.assertEqual(output, storage_url)

    def test_recent_external_quasar_image_is_repaired_from_existing_database_row(self):
        now = datetime.now(timezone.utc)
        source_link = "https://quasarzone.com/bbs/qb_saleinfo/views/1978877"
        external_image = "https://img2.quasarzone.com/editor/2026/08/17/product.jpg"
        storage_image = (
            "https://example.supabase.co/storage/v1/object/public/"
            "deal-images/quasar/1978877-thumb-a1b2c3.webp"
        )
        storage_detail = storage_image.replace("-thumb-", "-detail640-")
        existing = {
            "id": "database-id",
            "source": "quasar",
            "source_post_id": "1978877",
            "source_link": source_link,
            "img": external_image,
            "detail_img": external_image,
            "title": "sample",
            "registered_at": (now - timedelta(hours=1)).isoformat(),
            "deleted_at": None,
        }

        repairs = sync.build_existing_image_repair_rows(
            [existing],
            "https://example.supabase.co",
            prune_before=now - timedelta(hours=48),
            future_after=now + timedelta(minutes=10),
        )

        self.assertEqual(len(repairs), 1)
        self.assertNotIn("id", repairs[0])
        repairs[0]["img"] = storage_image
        repairs[0]["detail_img"] = storage_detail
        existing_map = {sync.sync_key(existing): existing}
        changed_rows = []

        appended = sync.append_image_repair_changes(
            changed_rows,
            repairs,
            existing_map,
            now.isoformat(),
            use_source_post_id=True,
        )

        self.assertEqual(appended, 1)
        self.assertEqual(changed_rows[0]["img"], storage_image)
        self.assertEqual(changed_rows[0]["detail_img"], storage_detail)
        self.assertIsNone(changed_rows[0]["deleted_at"])

    def test_source_scoped_sync_does_not_repair_quasar_images(self):
        now = datetime.now(timezone.utc)
        existing = {
            "source": "quasar",
            "source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/1978877",
            "img": "https://img2.quasarzone.com/editor/product.jpg",
            "detail_img": "https://img2.quasarzone.com/editor/product.jpg",
            "registered_at": (now - timedelta(hours=1)).isoformat(),
            "deleted_at": None,
        }

        with patch.object(sync, "EXPECTED_FEED_SOURCES", {"ppomppu", "fmkorea", "ruliweb"}):
            repairs = sync.build_existing_image_repair_rows(
                [existing],
                "https://example.supabase.co",
                prune_before=now - timedelta(hours=48),
                future_after=now + timedelta(minutes=10),
            )

        self.assertEqual(repairs, [])

if __name__ == "__main__":
    unittest.main()
