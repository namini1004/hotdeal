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


if __name__ == "__main__":
    unittest.main()
