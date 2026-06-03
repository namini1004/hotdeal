import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RefreshPolicyTests(unittest.TestCase):
    def test_manual_pull_refresh_keeps_delta_since_query(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("await refreshFeed({ mode: 'manual' });", html)
        self.assertIn("const sinceQuery = shouldUseDeltaRefresh(mode) && state.lastFeedSyncAt", html)

    def test_init_entry_full_refreshes_only_after_24_hours(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("const FULL_REFRESH_INTERVAL_MS = 24 * 60 * 60 * 1000;", html)
        self.assertIn("function shouldUseDeltaRefresh(mode = 'auto')", html)
        self.assertIn("if(mode === 'entry') return !isFeedSyncExpired();", html)
        self.assertIn("await refreshFeed({ silent: true, mode: 'entry' });", html)


if __name__ == "__main__":
    unittest.main()
