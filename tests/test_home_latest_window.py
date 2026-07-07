import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomeLatestWindowTests(unittest.TestCase):
    def test_latest_tab_is_removed_from_home(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('data-tab="latest"', html)
        self.assertNotIn("최근 10시간 이내 올라온 딜이 아직 없습니다.", html)
        self.assertIn('data-tab="all">전체순</button>', html)
        self.assertIn('data-tab="popular">인기순</button>', html)

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
