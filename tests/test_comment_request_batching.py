import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CommentRequestBatchingTests(unittest.TestCase):
    def test_detail_loads_all_legacy_comment_keys_with_one_browser_request(self):
        html = (ROOT / "indexdetail.html").read_text(encoding="utf-8")

        self.assertIn("const dealKeys = getCommentDealKeys(item);", html)
        self.assertIn("dealKeys=${encodeURIComponent(JSON.stringify(dealKeys))}", html)
        self.assertNotIn("fetch(`${COMMENT_API}&dealKey=${encodeURIComponent(key)}`", html)

    def test_api_accepts_and_deduplicates_batched_comment_keys(self):
        js = (ROOT / "api" / "deals.js").read_text(encoding="utf-8")

        self.assertIn("function parseCommentDealKeys(req)", js)
        self.assertIn("Promise.all(dealKeys.map", js)
        self.assertIn("const seen = new Set();", js)


if __name__ == "__main__":
    unittest.main()
