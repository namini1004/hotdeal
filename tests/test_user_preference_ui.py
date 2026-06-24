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

    def test_home_settings_sheet_is_compact_menu_without_sort_row(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')

        self.assertNotIn('id="profileChip"', html)
        self.assertIn('id="settingsToggle"', html)
        self.assertIn('id="settingsSheet"', html)
        self.assertNotIn('id="settingsSortButton"', html)
        self.assertIn('id="settingsReadToggle"', html)
        self.assertIn('id="settingsDarkToggle"', html)
        self.assertIn('id="settingsPageLink"', html)
        self.assertIn('function bindSettingsSheet()', html)
        self.assertIn("window.GajiTheme?.apply?.(event.target.checked ? 'dark' : 'light');", html)

    def test_home_sort_control_is_removed_from_header(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        actions_start = html.index('<div class="top-actions">')
        actions_end = html.index('</div>', actions_start)
        actions = html[actions_start:actions_end]

        self.assertNotIn('id="sortToggle"', actions)
        self.assertNotIn('id="sortIconWrap"', actions)
        self.assertNotIn('id="sortSheet"', html)
        self.assertIn('id="searchToggle"', actions)

    def test_theme_script_is_loaded_on_html_pages(self):
        for path in ROOT.glob('*.html'):
            html = path.read_text(encoding='utf-8')
            self.assertIn('assets/theme.js', html, path.name)

        theme = (ROOT / 'assets' / 'theme.js').read_text(encoding='utf-8')
        self.assertIn("const KEY = 'gaji_theme_mode_v1';", theme)
        self.assertIn('window.GajiTheme', theme)
        self.assertIn('html[data-theme="dark"]', theme)

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

    def test_hotdeal_create_has_manual_temperature_field(self):
        html = (ROOT / 'indexcreate.html').read_text(encoding='utf-8')

        self.assertIn('id="temperature"', html)
        self.assertIn('value="100"', html)
        self.assertIn('id="temperatureRange"', html)
        self.assertIn('const temperature = Math.max(0, Math.min(100', html)
        self.assertIn('manualTemperature: temperature', html)
        self.assertIn('temperature,', html)

    def test_hotdeal_create_has_short_desc_hint_and_misc_category(self):
        html = (ROOT / 'indexcreate.html').read_text(encoding='utf-8')

        self.assertIn('허위 과장 정보는 제한될 수 있습니다.<br>마크다운 문법을 지원합니다.', html)
        self.assertIn('data-cat="기타">기타</button>', html)
        self.assertNotIn('줄바꿈/링크/마크다운 지원', html)
        self.assertNotIn('/n 은 줄바꿈으로 처리되지 않으며', html)

    def test_hotdeal_create_category_chips_wrap_between_items_not_inside_text(self):
        html = (ROOT / 'indexcreate.html').read_text(encoding='utf-8')

        self.assertIn('.row{display:flex;flex-wrap:wrap;gap:8px}', html)
        self.assertIn('white-space:nowrap;word-break:keep-all', html)
        for category in ('식품', '뷰티', '육아', '스포츠'):
            self.assertIn(f'data-cat="{category}">{category}</button>', html)


    def test_web_header_actions_align_to_upper_right(self):
        index = (ROOT / 'index.html').read_text(encoding='utf-8')
        board = (ROOT / 'board.html').read_text(encoding='utf-8')

        desktop_index = index[index.index('@media (min-width:768px)'):index.index('@media (min-width:1180px)')]
        desktop_board = board[board.index('@media (min-width:768px)'):]

        self.assertIn('.row{display:flex;align-items:center;justify-content:space-between;gap:18px}', desktop_index)
        self.assertIn('.top-actions{margin-left:auto;justify-content:flex-end;gap:3px}', desktop_index)
        self.assertNotIn('grid-template-columns:minmax(190px,1fr) auto minmax(190px,1fr)', desktop_index)

        self.assertIn('.top-row{display:flex;align-items:center;justify-content:space-between;gap:18px}', desktop_board)
        self.assertIn('.top-actions{margin-left:auto;justify-content:flex-end;gap:3px}', desktop_board)
        self.assertNotIn('grid-template-columns:minmax(190px,1fr) auto minmax(190px,1fr)', desktop_board)


if __name__ == '__main__':
    unittest.main()
