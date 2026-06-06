import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL_HTML = ROOT / 'indexdetail.html'
INDEX_HTML = ROOT / 'index.html'
MY_GAJI_HTML = ROOT / 'my-gaji.html'
NICKNAME_HTML = ROOT / 'nickname.html'


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

    def test_detail_comments_use_remote_api_not_local_fallback(self):
        html = DETAIL_HTML.read_text(encoding='utf-8')

        self.assertIn("const COMMENT_API = '/api/deals?action=comments';", html)
        self.assertIn('fetch(`${COMMENT_API}&dealKey=${encodeURIComponent(key)}`', html)
        self.assertNotIn('function readLocalComments', html)
        self.assertNotIn('function saveLocalComments', html)
        self.assertNotIn('localStorage.setItem(commentStorageKey', html)

    def test_list_click_passes_bootstrap_item_to_detail_page(self):
        html = INDEX_HTML.read_text(encoding='utf-8')

        self.assertIn("const DETAIL_BOOTSTRAP_KEY = 'hotdeal_detail_bootstrap_v1';", html)
        self.assertIn('function saveDetailBootstrapItem(item)', html)
        self.assertIn('sessionStorage.setItem(DETAIL_BOOTSTRAP_KEY, JSON.stringify({', html)
        self.assertIn('saveDetailBootstrapItem(item);', html)

    def test_detail_renders_bootstrap_before_loading_full_detail(self):
        html = DETAIL_HTML.read_text(encoding='utf-8')

        self.assertIn("const DETAIL_BOOTSTRAP_KEY = 'hotdeal_detail_bootstrap_v1';", html)
        self.assertIn('function readDetailBootstrap(id)', html)
        self.assertIn('let item = cachedDetail || bootstrapItem || cachedItems.find', html)
        self.assertIn('renderItem(item, { loadComments: false, renderDesc: !isBootstrapOnly, saveCache: !isBootstrapOnly });', html)
        self.assertIn('requestAnimationFrame(() => loadComments(item));', html)
        self.assertIn('if(cachedDetail){', html)
        self.assertNotIn('if(item){\n        return;\n      }\n\n      try{', html)
        self.assertIn('renderItem(latest, { loadComments: false, renderDesc: true });', html)
        init_before_id = re.search(r'async function init\(\)\{(.*?)const id = new URLSearchParams', html, re.S)
        self.assertIsNotNone(init_before_id)
        assert init_before_id is not None
        self.assertNotIn('await loadMe();', init_before_id.group(1))
        self.assertIn('const userReady = loadMe()', html)
        self.assertIn('? renderRichText(item.desc)', html)

    def test_list_first_view_images_are_eager_and_rest_lazy(self):
        html = INDEX_HTML.read_text(encoding='utf-8')

        self.assertIn('items.map((item, idx) =>', html)
        self.assertIn("const imageLoading = idx < 4 ? 'eager' : 'lazy';", html)
        self.assertIn("const imageFetchPriority = idx === 0 ? 'high' : 'auto';", html)
        self.assertIn('loading="${imageLoading}"', html)
        self.assertIn('fetchpriority="${imageFetchPriority}"', html)

    def test_mobile_empty_comments_do_not_force_viewport_height(self):
        html = DETAIL_HTML.read_text(encoding='utf-8')

        self.assertIn('@media (max-width:767px)', html)
        self.assertIn('.comments-panel{display:block;min-height:0;', html)
        self.assertIn('.comment-composer{position:relative;bottom:auto;margin-top:8px;', html)
        self.assertNotIn('min-height:calc(100vh - 64px)', html)
        self.assertNotIn('margin-top:auto', html)

    def test_reply_connector_keeps_profile_to_profile_line_without_downward_tail(self):
        html = DETAIL_HTML.read_text(encoding='utf-8')

        self.assertIn('.comment-thread.has-replies::before', html)
        self.assertIn('top:var(--thread-line-top,36px);bottom:var(--thread-line-bottom,15px);border-left:1px solid #d8d5df', html)
        self.assertIn('.comment-item.reply::before{content:"";position:absolute;left:-28px;top:15px;width:27px;height:0;border-bottom:1px solid #d8d5df}', html)
        self.assertIn('requestAnimationFrame(updateReplyConnectors);', html)
        self.assertIn('function updateReplyConnectors()', html)
        self.assertIn('parentRect.bottom - threadRect.top - 1', html)
        self.assertIn('replyRect.top + (replyRect.height / 2) - threadRect.top', html)
        self.assertNotIn('border-bottom-left-radius:10px', html)
        self.assertNotIn('height:18px;border-left:1px solid #d8d5df;border-bottom', html)

    def test_nickname_pages_do_not_reconcile_google_profile_nickname(self):
        nickname_html = NICKNAME_HTML.read_text(encoding='utf-8')
        my_gaji_html = MY_GAJI_HTML.read_text(encoding='utf-8')

        self.assertIn('function loadCurrent()', nickname_html)
        self.assertIn("applyNickname(window.GajiIdentity?.getNickname?.() || '');", nickname_html)
        self.assertNotIn("/api/auth?action=me", nickname_html)
        self.assertNotIn('gaji_profile_pending_nickname_v1', nickname_html)
        self.assertNotIn('/api/profile-nickname', nickname_html)

        self.assertIn('function nicknameForDisplay(){', my_gaji_html)
        self.assertIn("return window.GajiIdentity?.getNickname?.() || '익명 가지';", my_gaji_html)
        self.assertNotIn('async function reconcilePendingNickname(user)', my_gaji_html)
        self.assertNotIn('gaji_profile_pending_nickname_v1', my_gaji_html)


if __name__ == '__main__':
    unittest.main()
