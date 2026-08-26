import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomeLatestWindowTests(unittest.TestCase):
    def test_home_uses_latest_popular_and_free_tabs(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('data-tab="latest"', html)
        self.assertNotIn("최근 10시간 이내 올라온 딜이 아직 없습니다.", html)
        self.assertIn('data-tab="all">최신</button>', html)
        self.assertIn('data-tab="popular">인기</button>', html)
        self.assertIn('data-tab="free">무료</button>', html)
        self.assertIn("const TAB_ORDER = ['all','popular','free'];", html)

    def test_free_deals_are_exclusive_to_free_tab(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("function parseDealPriceWon(value)", html)
        self.assertIn("function isFreeDeal(item = {})", html)
        self.assertIn("amount >= 0 && amount <= 100", html)
        self.assertIn("if(state.activeTab === 'free') return state.allItems.filter(isFreeDeal);", html)
        self.assertIn("return state.allItems.filter(item => !isFreeDeal(item));", html)
        self.assertIn("무료 딜이 아직 없습니다.", html)

    def test_home_shows_initial_gaji_loading_before_empty_state(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("initialFeedLoading: true", html)
        self.assertIn("state.initialFeedLoading && !items.length", html)
        self.assertIn("가지치기 중...", html)
        self.assertIn("initial-loading", html)
        self.assertIn("gaji-eggplant-transparent.png", html)
        self.assertIn("state.initialFeedLoading = false;", html)


if __name__ == "__main__":
    unittest.main()
