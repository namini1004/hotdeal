import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
DEALS_MODULE = ROOT / "api" / "_lib" / "deals.js"
IMAGE_PROXY_MODULE = ROOT / "api" / "image-proxy.js"
NODE = shutil.which("node") or str(ROOT / ".tools" / "node-v24.14.0-win-x64" / "node.exe")

spec = importlib.util.spec_from_file_location("sync_hotdeals_to_supabase", SYNC_SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class QuasarImageDeliveryTests(unittest.TestCase):
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

    def test_image_proxy_allows_only_supported_source_hosts_with_correct_referer(self):
        module_path = json.dumps(str(IMAGE_PROXY_MODULE))
        script = f"""
          const proxy = require({module_path});
          console.log(JSON.stringify({{
            quasar: proxy.sourceHeadersForHost('img2.quasarzone.com'),
            ruliweb: proxy.sourceHeadersForHost('i2.ruliweb.com'),
            blocked: proxy.sourceHeadersForHost('example.com')
          }}));
        """

        output = subprocess.check_output([NODE, "-e", script], cwd=ROOT, text=True).strip()
        data = json.loads(output)

        self.assertEqual(data["quasar"]["referer"], "https://quasarzone.com/bbs/qb_saleinfo")
        self.assertEqual(data["ruliweb"]["referer"], "https://www.ruliweb.com/")
        self.assertIsNone(data["blocked"])

    def test_quasar_mirror_retries_through_gaji_relay_after_direct_403(self):
        source_image = "https://img2.quasarzone.com/editor/2026/08/17/product.jpg"
        row = {
            "source": "quasar",
            "source_post_id": "1978877",
            "source_link": "https://quasarzone.com/bbs/qb_saleinfo/views/1978877",
            "img": source_image,
        }
        image = Image.new("RGB", (640, 480), (120, 80, 200))
        image_buffer = io.BytesIO()
        image.save(image_buffer, format="JPEG")
        relay_calls = []

        def fake_get(url, *args, **kwargs):
            if "/storage/v1/bucket/" in url:
                return Mock(ok=True, status_code=200, text="{}")
            if url == source_image:
                return Mock(ok=False, status_code=403, text="forbidden")
            if url == sync.IMAGE_RELAY_URL:
                relay_calls.append(kwargs.get("params"))
                return Mock(
                    ok=True,
                    status_code=200,
                    headers={"content-type": "image/jpeg"},
                    content=image_buffer.getvalue(),
                )
            raise AssertionError(f"unexpected GET: {url}")

        with patch.object(sync.requests, "get", side_effect=fake_get), patch.object(
            sync.requests,
            "post",
            return_value=Mock(ok=True, status_code=200, text="{}"),
        ):
            result = sync.mirror_feed_image(row, None, "https://example.supabase.co", "service-key")

        self.assertEqual(relay_calls, [{"url": source_image}])
        self.assertIn("/deal-images/quasar/1978877-thumb-", result["img"])
        self.assertIn("/deal-images/quasar/1978877-detail640-", result["detail_img"])


if __name__ == "__main__":
    unittest.main()
