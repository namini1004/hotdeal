import unittest

from scripts import update_quasar_feed as quasar


class QuasarImageParsingTests(unittest.TestCase):
    def test_uses_large_body_image_after_price_area(self):
        html = """
        <html><body>
          <img src="https://img2.quasarzone.com/profile/user_80x80.png" width="80" height="80">
          <table>
            <tr><th>가격</th><td>879,000원</td></tr>
            <tr><th>배송비/직배</th><td>3,000</td></tr>
          </table>
          <div class="board-view-content">
            <img src="https://img2.quasarzone.com/profile/small_64x64.jpg" width="64" height="64">
            <img src="https://img2.quasarzone.com/editor/2026/06/product_740x620.jpg" width="740" height="620">
          </div>
        </body></html>
        """

        self.assertEqual(
            quasar.extract_body_image_from_detail(html),
            "https://img2.quasarzone.com/editor/2026/06/product_740x620.jpg",
        )

    def test_rejects_small_image_size_from_url(self):
        html = """
        | 가격 | 10,000원 |
        | 배송비 | 무료 |
        ![](https://img2.quasarzone.com/profile/avatar_80x80.png)
        ![](https://img2.quasarzone.com/editor/product_640x480.jpg)
        """

        self.assertEqual(
            quasar.extract_body_image_from_detail(html),
            "https://img2.quasarzone.com/editor/product_640x480.jpg",
        )

    def test_jina_list_rejects_theme_fallback_images(self):
        line = (
            "진행중[테스트 딜](https://quasarzone.com/bbs/qb_saleinfo/views/12345) "
            "PC/하드웨어 가격 10,000원 배송비 무료 "
            "![](https://img2.quasarzone.com/homepage/real/themes/quasarzone/images/sub/tangerine.png) "
            "1424 1시간 전"
        )

        item = quasar.parse_jina_list_items(line)[0]

        self.assertEqual(item["img"], "")

    def test_repeated_cached_list_thumbnail_is_not_reused_for_detail_image(self):
        repeated_thumb = "https://img2.quasarzone.com/editor/2026/06/03/thumb_bad.png"
        previous = [
            {
                "id": "1",
                "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/1",
                "img": repeated_thumb,
                "buyLink": "https://a.example/1",
                "desc": "cached",
                "registeredAt": "2026-06-03T10:00:00+09:00",
            },
            {
                "id": "2",
                "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/2",
                "img": repeated_thumb,
                "buyLink": "https://a.example/2",
                "desc": "cached",
                "registeredAt": "2026-06-03T10:00:00+09:00",
            },
            {
                "id": "3",
                "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/3",
                "img": repeated_thumb,
                "buyLink": "https://a.example/3",
                "desc": "cached",
                "registeredAt": "2026-06-03T10:00:00+09:00",
            },
        ]
        lookup = quasar.build_previous_detail_lookup(previous)
        row = {
            "id": "1",
            "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/1",
            "img": repeated_thumb,
        }

        self.assertFalse(quasar.apply_cached_detail_fields(row, lookup))


if __name__ == "__main__":
    unittest.main()
