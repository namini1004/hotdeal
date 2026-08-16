import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync_hotdeals_to_supabase.py"
DEALS_MODULE = ROOT / "api" / "_lib" / "deals.js"
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


if __name__ == "__main__":
    unittest.main()
