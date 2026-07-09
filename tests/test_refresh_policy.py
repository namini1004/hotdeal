import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RefreshPolicyTests(unittest.TestCase):
    def test_manual_pull_refresh_forces_full_refresh(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("await refreshFeed({ mode: 'manual' });", html)
        self.assertIn("if(mode === 'manual') return false;", html)
        self.assertIn("const sinceQuery = (!append && shouldUseDeltaRefresh(mode) && state.lastFeedSyncAt)", html)
        self.assertIn("const FEED_PAGE_SIZE = 100;", html)
        self.assertIn("?scope=feed&limit=${FEED_PAGE_SIZE}${offsetQuery}${sinceQuery}", html)
        self.assertIn("async function loadMoreFeed()", html)
        self.assertIn("loadMoreFeed();", html)

    def test_init_entry_full_refreshes_only_after_24_hours(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("const FULL_REFRESH_INTERVAL_MS = 24 * 60 * 60 * 1000;", html)
        self.assertIn("function shouldUseDeltaRefresh(mode = 'auto')", html)
        self.assertIn("function feedTemperatureLooksIncomplete(items = state.feedItems)", html)
        self.assertIn("if(feedTemperatureLooksIncomplete()) return false;", html)
        self.assertIn("if(mode === 'entry') return !isFeedSyncExpired();", html)
        self.assertIn("const needsFreshTemperature = feedTemperatureLooksIncomplete(state.feedItems);", html)
        self.assertIn("await refreshFeed({ silent: true, mode: needsFreshTemperature ? 'manual' : 'entry' });", html)

    def test_client_dedupes_ppomppu_by_canonical_no(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("function canonicalDealKey(item = {})", html)
        self.assertIn("if(source === 'ppomppu')", html)
        self.assertIn("return `${source}::no:${noMatch[1]}`;", html)

    def test_home_tabs_have_fixed_sort_modes(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("if(state.activeTab === 'popular')", html)
        self.assertIn("if(db !== da) return db - da;", html)
        self.assertNotIn("state.sortMode", html)
        self.assertNotIn("data-tab=\"latest\"", html)

    def test_client_prunes_stale_cached_feed_items(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("const FEED_LOOKBACK_MS = 48 * 60 * 60 * 1000;", html)
        self.assertIn("function filterStaleFeedItems(items)", html)
        self.assertIn("const cleaned = filterStaleFeedItems(filterDeleted(dedupeItems(items)));", html)

    def test_feed_api_fetches_each_source_independently(self):
        js = (ROOT / "api" / "_lib" / "deals.js").read_text(encoding="utf-8")

        self.assertIn("const FEED_SOURCES = ['ppomppu', 'quasar', 'fmkorea', 'ruliweb'];", js)
        self.assertIn("source=eq.${encodeURIComponent(source)}", js)
        self.assertIn("const FEED_LOOKBACK_HOURS = 48;", js)
        self.assertIn("registered_at=gte.${encodeURIComponent(cutoffIso)}", js)
        self.assertIn("Promise.all(FEED_SOURCES.map", js)
        self.assertNotIn("deals?source=neq.user&deleted_at=is.null&select=*&order=registered_at.desc&limit=3000", js)

    def test_deals_api_applies_response_limit(self):
        js = (ROOT / "api" / "deals.js").read_text(encoding="utf-8")

        self.assertIn("function parseLimit(value, fallback = 400, max = 600)", js)
        self.assertIn("function parseOffset(value)", js)
        self.assertIn("const limit = parseLimit(url.searchParams.get('limit') || req.query?.limit);", js)
        self.assertIn("const offset = parseOffset(url.searchParams.get('offset') || req.query?.offset);", js)
        self.assertIn(".slice(0, limit)", js)
        self.assertIn("hasMore", js)
        self.assertIn("nextOffset", js)

    def test_refresh_watchdog_monitors_workflow_cadence(self):
        workflow = (ROOT / ".github" / "workflows" / "hotdeal-refresh-watchdog.yml").read_text(encoding="utf-8")

        self.assertIn("REFRESH_WORKFLOW: hotdeal-refresh-supabase.yml", workflow)
        self.assertIn('STALE_THRESHOLD_MINUTES: "35"', workflow)
        self.assertIn("actions/workflows/{workflow}/runs?per_page=20", workflow)
        self.assertIn('active_statuses = {"queued", "in_progress", "waiting", "requested", "pending"}', workflow)
        self.assertIn('stale = (not active) and age_minutes > threshold', workflow)
        self.assertIn("Refresh workflow last succeeded", workflow)
        self.assertIn("gh workflow run hotdeal-refresh-supabase.yml", workflow)


if __name__ == "__main__":
    unittest.main()
