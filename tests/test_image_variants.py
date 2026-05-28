import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
spec = importlib.util.spec_from_file_location("sync_hotdeals_to_supabase", SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def sample_image_bytes(width=1200, height=900):
    image = Image.new("RGB", (width, height), (120, 80, 200))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


class ImageVariantTests(unittest.TestCase):
    def test_make_webp_image_respects_requested_max_size(self):
        content = sample_image_bytes()

        thumb = sync.make_webp_image(content, 320)
        detail = sync.make_webp_image(content, sync.DETAIL_IMAGE_MAX_SIZE)

        with Image.open(io.BytesIO(thumb)) as thumb_image:
            self.assertEqual(thumb_image.format, "WEBP")
            self.assertLessEqual(max(thumb_image.size), 320)
        with Image.open(io.BytesIO(detail)) as detail_image:
            self.assertEqual(detail_image.format, "WEBP")
            self.assertEqual(sync.DETAIL_IMAGE_MAX_SIZE, 640)
            self.assertLessEqual(max(detail_image.size), 640)
            self.assertGreater(max(detail_image.size), 320)

    def test_mirror_feed_image_uploads_thumb_and_detail_variants(self):
        row = {
            "source": "ppomppu",
            "source_link": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=707448",
            "img": "https://cdn3.ppomppu.co.kr/zboard/data3/2026/0529/sample.jpg",
        }
        uploaded = []

        def fake_get(url, *args, **kwargs):
            if "/storage/v1/bucket/" in url:
                return Mock(ok=True, status_code=200, text="{}")
            return Mock(ok=True, status_code=200, headers={"content-type": "image/jpeg"}, content=sample_image_bytes())

        def fake_post(url, headers=None, data=None, **kwargs):
            uploaded.append((url, headers, data))
            return Mock(ok=True, status_code=200, text="{}")

        with patch.object(sync.requests, "get", side_effect=fake_get), patch.object(sync.requests, "post", side_effect=fake_post):
            result = sync.mirror_feed_image(row, None, "https://example.supabase.co", "service-key")

        self.assertEqual(result["img"], "https://example.supabase.co/storage/v1/object/public/deal-images/ppomppu/707448-thumb-d46d478d2f62.webp")
        self.assertEqual(result["detail_img"], "https://example.supabase.co/storage/v1/object/public/deal-images/ppomppu/707448-detail640-d46d478d2f62.webp")
        self.assertEqual(len(uploaded), 2)
        self.assertTrue(uploaded[0][0].endswith("/ppomppu/707448-thumb-d46d478d2f62.webp"))
        self.assertTrue(uploaded[1][0].endswith("/ppomppu/707448-detail640-d46d478d2f62.webp"))
        self.assertEqual(uploaded[0][1]["Content-Type"], "image/webp")
        self.assertEqual(uploaded[1][1]["Content-Type"], "image/webp")

    def test_existing_480_detail_variant_is_not_reused_for_640_upgrade(self):
        row = {
            "source": "ppomppu",
            "source_link": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=707448",
            "img": "https://cdn3.ppomppu.co.kr/zboard/data3/2026/0529/sample.jpg",
        }
        prev = {
            "img": "https://example.supabase.co/storage/v1/object/public/deal-images/ppomppu/707448-thumb-d46d478d2f62.webp",
            "detail_img": "https://example.supabase.co/storage/v1/object/public/deal-images/ppomppu/707448-detail-d46d478d2f62.webp",
        }
        uploaded = []

        def fake_get(url, *args, **kwargs):
            if "/storage/v1/bucket/" in url:
                return Mock(ok=True, status_code=200, text="{}")
            return Mock(ok=True, status_code=200, headers={"content-type": "image/jpeg"}, content=sample_image_bytes())

        def fake_post(url, headers=None, data=None, **kwargs):
            uploaded.append((url, headers, data))
            return Mock(ok=True, status_code=200, text="{}")

        with patch.object(sync.requests, "get", side_effect=fake_get), patch.object(sync.requests, "post", side_effect=fake_post):
            result = sync.mirror_feed_image(row, prev, "https://example.supabase.co", "service-key")

        self.assertEqual(result["img"], prev["img"])
        self.assertEqual(result["detail_img"], "https://example.supabase.co/storage/v1/object/public/deal-images/ppomppu/707448-detail640-d46d478d2f62.webp")
        self.assertEqual(len(uploaded), 1)
        self.assertTrue(uploaded[0][0].endswith("/ppomppu/707448-detail640-d46d478d2f62.webp"))

    def test_tracked_fields_include_detail_image(self):
        self.assertIn("detail_img", sync.TRACKED_FIELDS)


if __name__ == "__main__":
    unittest.main()
