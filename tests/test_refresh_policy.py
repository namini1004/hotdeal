import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RefreshPolicyTests(unittest.TestCase):
    def test_manual_pull_refresh_forces_full_refresh(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("await refreshFeed({ mode: 'manual' });", html)
        self.assertIn("if(mode === 'manual') return false;", html)
        self.assertIn("const sinceQuery = shouldUseDeltaRefresh(mode) && state.lastFeedSyncAt", html)

    def test_init_entry_full_refreshes_only_after_24_hours(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("const FULL_REFRESH_INTERVAL_MS = 24 * 60 * 60 * 1000;", html)
        self.assertIn("function shouldUseDeltaRefresh(mode = 'auto')", html)
        self.assertIn("if(mode === 'entry') return !isFeedSyncExpired();", html)
        self.assertIn("await refreshFeed({ silent: true, mode: 'entry' });", html)

    def test_client_dedupes_ppomppu_by_canonical_no(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("function canonicalDealKey(item = {})", html)
        self.assertIn("if(source === 'ppomppu')", html)
        self.assertIn("return `${source}::no:${noMatch[1]}`;", html)

    def test_latest_tab_ignores_temperature_sort(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("if(state.activeTab !== 'latest' && state.sortMode === 'temperature')", html)


if __name__ == "__main__":
    unittest.main()
