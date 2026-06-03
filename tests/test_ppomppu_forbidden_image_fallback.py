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


def jpeg_bytes(width, height, color=(240, 240, 240), target_size=None):
    image = Image.new("RGB", (width, height), color)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    data = out.getvalue()
    if target_size and len(data) < target_size:
        data += b"\0" * (target_size - len(data))
    return data


class PpomppuForbiddenImageFallbackTests(unittest.TestCase):
    def test_detects_ppomppu_forbidden_warning_by_exact_dimension_and_24_to_26kb_size(self):
        warning = jpeg_bytes(355, 138, target_size=25_534)
        self.assertTrue(sync.is_ppomppu_forbidden_warning_image(warning))

    def test_does_not_treat_normal_product_image_as_forbidden_warning(self):
        normal = jpeg_bytes(1080, 720, target_size=25_534)
        self.assertFalse(sync.is_ppomppu_forbidden_warning_image(normal))

    def test_warning_image_reuses_existing_storage_image_instead_of_cdn_url(self):
        row = {
            "source": "ppomppu",
            "source_link": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708868",
            "img": "https://cdn3.ppomppu.co.kr/zboard/data3/2026/0603/warning.jpg",
            "detail_img": "https://cdn3.ppomppu.co.kr/zboard/data3/2026/0603/warning.jpg",
        }
        prev = {
            "img": "https://example.supabase.co/storage/v1/object/public/deal-images/ppomppu/708868-thumb-old.webp",
            "detail_img": "https://example.supabase.co/storage/v1/object/public/deal-images/ppomppu/708868-detail640-old.webp",
        }

        def fake_get(url, *args, **kwargs):
            if "/storage/v1/bucket/" in url:
                return Mock(ok=True, status_code=200, text="{}")
            return Mock(ok=True, status_code=200, headers={"content-type": "image/jpeg"}, content=jpeg_bytes(355, 138, target_size=25_534))

        with patch.object(sync.requests, "get", side_effect=fake_get):
            result = sync.mirror_feed_image(row, prev, "https://example.supabase.co", "service-key")

        self.assertEqual(result, prev)

    def test_warning_image_without_existing_storage_falls_back_to_default_empty_image(self):
        row = {
            "source": "ppomppu",
            "source_link": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708868",
            "img": "https://cdn3.ppomppu.co.kr/zboard/data3/2026/0603/warning.jpg",
            "detail_img": "https://cdn3.ppomppu.co.kr/zboard/data3/2026/0603/warning.jpg",
        }

        def fake_get(url, *args, **kwargs):
            if "/storage/v1/bucket/" in url:
                return Mock(ok=True, status_code=200, text="{}")
            return Mock(ok=True, status_code=200, headers={"content-type": "image/jpeg"}, content=jpeg_bytes(355, 138, target_size=25_534))

        with patch.object(sync.requests, "get", side_effect=fake_get):
            result = sync.mirror_feed_image(row, None, "https://example.supabase.co", "service-key")

        self.assertEqual(result, {"img": "", "detail_img": ""})


if __name__ == "__main__":
    unittest.main()
