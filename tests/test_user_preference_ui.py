import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UserPreferenceUiTests(unittest.TestCase):
    def test_logged_in_account_card_hides_guest_intro_copy(self):
        html = (ROOT / 'my-gaji.html').read_text(encoding='utf-8')

        self.assertIn('id="accountIntro"', html)
        self.assertIn("accountIntro.style.display = 'none';", html)
        self.assertIn("accountIntro.style.display = 'block';", html)

    def test_generated_nickname_has_large_adjective_and_noun_pools(self):
        js = (ROOT / 'assets' / 'anonymous-identity.js').read_text(encoding='utf-8')

        adj_match = re.search(r"const ADJECTIVES = \[(.*?)\];", js, re.S)
        noun_match = re.search(r"const NOUNS = \[(.*?)\];", js, re.S)
        self.assertIsNotNone(adj_match)
        self.assertIsNotNone(noun_match)
        assert adj_match is not None
        assert noun_match is not None
        adjectives = re.findall(r"'([^']+)'", adj_match.group(1))
        nouns = re.findall(r"'([^']+)'", noun_match.group(1))
        self.assertGreaterEqual(len(adjectives), 100)
        self.assertGreaterEqual(len(nouns), 100)

    def test_keywords_page_renders_local_cache_before_server_sync(self):
        html = (ROOT / 'keywords.html').read_text(encoding='utf-8')

        self.assertIn("const KEYWORD_CACHE_KEY = 'gaji_keyword_cache_v1';", html)
        self.assertIn('function loadCachedKeywords(){', html)
        self.assertIn('function saveCachedKeywords(items){', html)
        self.assertRegex(html, r'render\(loadCachedKeywords\(\)\);\s*if\(!await ensureGoogleLogin\(\)\) return;')
        self.assertIn('saveCachedKeywords(data.items || []);', html)

    def test_read_highlight_preference_notifies_home_and_home_rerenders(self):
        my_gaji = (ROOT / 'my-gaji.html').read_text(encoding='utf-8')
        index = (ROOT / 'index.html').read_text(encoding='utf-8')

        self.assertIn("notifyReadHighlightPreferenceChanged();", my_gaji)
        self.assertIn("new BroadcastChannel('gaji_read_highlight_pref_v1')", my_gaji)
        self.assertIn('function bindReadHighlightPreferenceSync(){', index)
        self.assertIn("new BroadcastChannel('gaji_read_highlight_pref_v1')", index)
        self.assertIn("window.addEventListener('pageshow',", index)
        self.assertIn("window.addEventListener('storage',", index)
    def test_gajigaji_hides_category_tabs_and_shows_tips_only(self):
        board = (ROOT / 'board.html').read_text(encoding='utf-8')
        create = (ROOT / 'boardcreate.html').read_text(encoding='utf-8')

        self.assertNotIn('class="board-tabs"', board)
        self.assertNotIn('data-category="mydeals"', board)
        self.assertIn("state.category = 'tips';", board)
        self.assertIn("location.href = 'boardcreate.html?category=tips';", board)
        self.assertIn('class="field category-field"', create)
        self.assertNotIn('<option value="mydeals">', create)
        self.assertIn("const category = 'tips';", create)


if __name__ == '__main__':
    unittest.main()
