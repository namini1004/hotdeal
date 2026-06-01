import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomeLatestWindowTests(unittest.TestCase):
    def test_latest_tab_uses_recent_10_hours(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("state.allItems.filter(item => isWithinHours(item, 10))", html)
        self.assertIn("최근 10시간 이내 올라온 딜이 아직 없습니다.", html)


if __name__ == "__main__":
    unittest.main()
