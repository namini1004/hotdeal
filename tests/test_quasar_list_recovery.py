from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import update_quasar_feed as quasar


FIXTURES = Path(__file__).parent / "fixtures"
LIST_HTML = (FIXTURES / "quasar_v2_list.html").read_text(encoding="utf-8")
DETAIL_HTML = (FIXTURES / "quasar_v2_detail.html").read_text(encoding="utf-8")
BLOCKED_JINA = (FIXTURES / "quasar_jina_block.md").read_text(encoding="utf-8")


def response(text, status=200):
    result = MagicMock(text=text, status_code=status)
    return result


class QuasarListRecoveryTests(unittest.TestCase):
    def test_actual_v2_rows_exclude_notice_and_keep_product_fields(self):
        rows = quasar.parse_list_items(LIST_HTML)
        self.assertEqual([row["id"] for row in rows], ["1988768", "1988723"])
        self.assertEqual(rows[0]["price"], "9,900")
        self.assertEqual(rows[0]["category"], "생활/식품")
        self.assertEqual(rows[0]["views"], 159)
        self.assertEqual(rows[0]["time"], "22분 전")
        self.assertEqual(rows[1]["views"], 2900)
        self.assertEqual(rows[1]["comments"], 13)
        self.assertIn("/editor/2024/03/17/", rows[1]["img"])
        self.assertEqual(rows[1]["sourceLink"], "https://quasarzone.com/bbs/qb_saleinfo/views/1988723")

    def test_legacy_table_and_nested_comment_remain_supported(self):
        page = '''<table><tr class="row"><td>
          <a class="subject-link" href="/bbs/qb_saleinfo/views/123?page=2">Product
            <span class="board-list-comment"><span class="ctn-count ">3</span></span>
          </a><span class="category">PC</span><span class="text-orange">1,000 (KRW)</span>
          <span class="count">5</span><span class="count">1.2k</span><span class="date">09-26</span>
          <img src="https://img2.quasarzone.com/editor/product.jpg" class="maxImg">
        </td></tr></table>'''
        row = quasar.parse_list_items(page)[0]
        self.assertEqual((row["title"], row["comments"], row["views"]), ("Product", 3, 1200))
        self.assertEqual(row["sourceLink"], "https://quasarzone.com/bbs/qb_saleinfo/views/123")
        self.assertTrue(row["img"].endswith("product.jpg"))

    def test_blind_and_incomplete_rows_do_not_poison_fallback_seen_ids(self):
        seen = set()
        invalid = LIST_HTML.replace("22분 전", "").replace(
            "[네이버] 네이버페이 적립 29원/쇼핑라이브/12원 종합 차트 (26.9.27)", "블라인드 처리된 글입니다.")
        self.assertEqual(quasar.parse_list_items(invalid, seen), [])
        self.assertEqual(len(quasar.parse_list_items(LIST_HTML, seen)), 2)
        self.assertEqual(quasar.parse_list_items(LIST_HTML, seen), [])

    def test_localized_counts(self):
        for value, expected in [("159", 159), ("1,234", 1234), ("2.9천", 2900), ("1만", 10000), ("1.25K", 1250)]:
            with self.subTest(value=value):
                self.assertEqual(quasar.parse_count(value), expected)

    def test_date_formats_and_unknown_time(self):
        now = datetime(2026, 9, 27, 12, tzinfo=quasar.KST)
        for value in ("09.26", "09-26", "26.09.26", "2026-09-26"):
            self.assertEqual(quasar.parse_time_to_datetime(value, now), now.replace(day=26, hour=0))
        self.assertEqual(quasar.parse_time_to_datetime("1일 전", now), now - timedelta(days=1))
        self.assertEqual(quasar.parse_time_to_datetime("12.31", now.replace(month=1, day=1)).year, 2025)
        for value in ("", "unknown", "02.30"):
            with self.assertRaises(ValueError):
                quasar.parse_time_to_datetime(value, now)

    def test_detail_uses_original_iso_publication_and_offer(self):
        now = datetime(2026, 9, 27, 12, tzinfo=quasar.KST)
        self.assertEqual(quasar.extract_registered_at_from_detail(DETAIL_HTML, "2026-09-27", now=now), "2026-09-27T10:56:06+09:00")
        self.assertEqual(quasar.extract_buy_link_from_detail(DETAIL_HTML), "https://www.11st.co.kr/products/8369421713")
        self.assertIn("/editor/2026/09/27/", quasar.extract_body_image_from_detail(DETAIL_HTML))
        self.assertIn("보습용", quasar.extract_body_text_from_detail(DETAIL_HTML))

    def test_unavailable_detail_retains_relative_list_time_not_midnight(self):
        now = datetime(2026, 9, 27, 12, tzinfo=quasar.KST)
        fallback = now - timedelta(minutes=22)
        self.assertEqual(quasar.extract_registered_at_from_detail("", "2026-09-27", now=now, fallback_datetime=fallback), fallback.isoformat())

    def test_successful_image_only_detail_is_reusable(self):
        item = {"id": "123", "registeredAt": datetime.now(quasar.KST).isoformat(),
                "buyLink": "https://shop.example/product", "desc": "", "detailParsed": True}
        row = {"id": "123", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/123"}
        self.assertTrue(quasar.apply_cached_detail_fields(row, quasar.build_previous_detail_lookup([item])))
        self.assertTrue(row["detailParsed"])
        self.assertTrue(quasar.has_reusable_detail_fields(row))

    def run_collector(self, first_response, browser_result=None, jina_response=None, fails=False, expired=False):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            path = Path(tmp) / "feed.json"
            cached = quasar.parse_list_items(LIST_HTML)
            for row in cached:
                row.update(registeredAt=datetime.now(quasar.KST).isoformat(), buyLink=row["sourceLink"], desc="Cached body")
            original = json.dumps({"items": cached, "expiredPostIds": ["999"] if expired else []})
            path.write_text(original, encoding="utf-8")
            for name, value in {"JSON_PATH": path, "MAX_PAGES": 1, "FETCH_MODE": "hybrid", "NEW_DETAIL_DELAY_SECONDS": 0}.items():
                stack.enter_context(patch.object(quasar, name, value))
            session = stack.enter_context(patch.object(quasar.requests, "Session")).return_value
            session.get.side_effect = [first_response] + ([jina_response] if jina_response else [])
            start = stack.enter_context(patch("scripts.quasar_browser_fetch.QuasarBrowserFetcher.start"))
            browser = start.return_value
            if isinstance(browser_result, Exception):
                browser.get_html.side_effect = browser_result
            else:
                browser.get_html.return_value = browser_result
            with redirect_stdout(io.StringIO()) as output:
                if fails:
                    with self.assertRaisesRegex(RuntimeError, "previous feed preserved"):
                        quasar.main()
                    self.assertEqual(path.read_text(encoding="utf-8"), original)
                else:
                    quasar.main()
                    self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["items"]), 2)
            self.assertEqual(session.get.call_count, 2 if jina_response else 1)
            if browser_result is None:
                start.assert_not_called()
            else:
                browser.get_html.assert_called_once()
                browser.close.assert_called_once()
            self.assertIn("QUASAR_FETCH_SUMMARY", output.getvalue())
            if not fails:
                self.assertIn("details=0 cached=2", output.getvalue())

    def test_valid_http_list_reuses_cache_without_browser_or_detail_requests(self):
        self.run_collector(response(LIST_HTML))

    def test_empty_http_list_falls_back_to_browser(self):
        self.run_collector(response("<html>unrecognized layout</html>"), LIST_HTML)

    def test_http_block_falls_back_to_browser(self):
        self.run_collector(response("Forbidden", 403), LIST_HTML)

    def test_all_transports_blocked_preserve_previous_feed_and_log_failure(self):
        self.run_collector(response("Forbidden", 403), RuntimeError("browser blocked (403)"), response(BLOCKED_JINA), fails=True)

    def test_entirely_expired_list_preserves_previous_feed(self):
        page = LIST_HTML.replace("22분 전", "2020-01-01").replace("11시간 전", "2020-01-01")
        self.run_collector(response(page), fails=True)

    def test_expired_date_only_post_does_not_trigger_another_detail_request(self):
        page = LIST_HTML + '''<div class="v2-list"><div class="v2-list-row">
            <a class="subject-link" href="/bbs/qb_saleinfo/views/999">Old product</a>
            <span class="v2-list-row__time">09.25</span>
        </div></div>'''
        self.run_collector(response(page), expired=True)


if __name__ == "__main__":
    unittest.main()
