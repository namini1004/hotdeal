import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL_HTML = ROOT / 'indexdetail.html'
INDEX_HTML = ROOT / 'index.html'


class DetailConversionUxTests(unittest.TestCase):
    def test_detail_cta_uses_real_buy_label_and_single_source_rule(self):
        html = DETAIL_HTML.read_text(encoding='utf-8')

        self.assertIn("function shouldUseSingleSourceCta(item)", html)
        self.assertIn("item.source === 'ruliweb'", html)
        self.assertIn("!item.buyLink", html)
        self.assertIn("buyBottom.textContent = '사러가기';", html)
        self.assertIn("buyBottom.style.display = 'none';", html)
        self.assertIn("sourceBottom.style.gridColumn = '2 / 4';", html)

        # 구매 CTA가 원문 링크로 대체되어 사용자를 헷갈리게 하지 않도록 보호
        self.assertNotIn("buyBottom.href = item.buyLink || item.sourceLink || '#'", html)
        self.assertNotIn('>가지고싶다</a>', html)

    def test_detail_hero_image_is_prioritized_without_extra_lazy_load(self):
        html = DETAIL_HTML.read_text(encoding='utf-8')
        self.assertRegex(
            html,
            r'<img id="img" alt="상품 이미지" decoding="async" fetchpriority="high">',
        )

    def test_list_first_view_images_are_eager_and_rest_lazy(self):
        html = INDEX_HTML.read_text(encoding='utf-8')

        self.assertIn('items.map((item, idx) =>', html)
        self.assertIn("const imageLoading = idx < 4 ? 'eager' : 'lazy';", html)
        self.assertIn("const imageFetchPriority = idx === 0 ? 'high' : 'auto';", html)
        self.assertIn('loading="${imageLoading}"', html)
        self.assertIn('fetchpriority="${imageFetchPriority}"', html)


if __name__ == '__main__':
    unittest.main()
