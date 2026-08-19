import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = ROOT / ".github" / "workflows" / "hotdeal-refresh-supabase.yml"
WATCHDOG_WORKFLOW = ROOT / ".github" / "workflows" / "hotdeal-refresh-watchdog.yml"
FMKOREA_SCRIPT = ROOT / "scripts" / "update_fmkorea_feed.py"


class GithubRefreshResilienceTests(unittest.TestCase):
    def test_refresh_schedule_uses_offset_minutes_to_avoid_busy_cron_slots(self):
        workflow = REFRESH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertNotIn('cron: "*/15 * * * *"', workflow)

    def test_refresh_workflow_leaves_quasar_to_the_local_collector(self):
        workflow = REFRESH_WORKFLOW.read_text(encoding="utf-8")
        ppomppu_job = workflow.split("  refresh-ppomppu:", 1)[1].split("  refresh-fmkorea:", 1)[0]

        for job in ("refresh-ppomppu", "refresh-fmkorea", "refresh-ruliweb"):
            self.assertIn(f"  {job}:", workflow)
        self.assertNotIn("  refresh-quasar:", workflow)
        self.assertNotIn("needs.refresh-quasar.result", workflow)
        self.assertNotIn("name: feed-quasar", workflow)
        self.assertIn('HOTDEAL_EXPECTED_FEED_SOURCES: "ppomppu,fmkorea,ruliweb"', workflow)
        self.assertIn('HOTDEAL_FMKOREA_INCREMENTAL_MAX_PAGES: "1"', workflow)
        self.assertIn('HOTDEAL_FMKOREA_BROWSER_FALLBACK_MAX_PAGES: "1"', workflow)
        self.assertIn('HOTDEAL_PPOMPPU_MAX_PAGES: "1"', ppomppu_job)
        self.assertIn('HOTDEAL_PPOMPPU_MAX_NEW_DETAILS: "15"', ppomppu_job)
        self.assertIn("python -u scripts/update_ppomppu_feed.py", ppomppu_job)
        self.assertNotIn("playwright", ppomppu_job.lower())
        self.assertIn("name: Download refreshed feed artifacts", workflow)
        self.assertIn("name: Remove checkout feed snapshots before artifact merge", workflow)
        self.assertIn("name: Copy downloaded feed artifacts into assets", workflow)
        self.assertIn("cp .downloaded-feeds/*hotdeals*.json assets/", workflow)
        self.assertIn("needs.refresh-fmkorea.result", workflow)
        self.assertIn("PUSH_INGEST_URL: https://gaji.run/api/push/ingest", workflow)
        self.assertIn("PUSH_INGEST_SECRET: ${{ secrets.PUSH_INGEST_SECRET }}", workflow)
        self.assertIn('PUSH_INGEST_BATCH_SIZE: "10"', workflow)
        self.assertIn('PUSH_INGEST_MAX_ROWS: "50"', workflow)

    def test_fmkorea_ingest_is_split_to_local_hermes_runner(self):
        script = (ROOT / "scripts" / "hermes_fmkorea_ingest.py").read_text(encoding="utf-8")

        self.assertIn("scripts/update_fmkorea_feed.py", script)
        self.assertIn("scripts/sync_hotdeals_to_supabase.py", script)
        self.assertIn("FMKOREA_BACKOFF_SKIP", script)
        self.assertIn("FMKOREA_BACKOFF_SET", script)
        self.assertIn("HERMES_FMKOREA_INGEST_SKIPPED", script)
        self.assertIn("HOTDEAL_FEED_FILES", script)
        self.assertIn("fmkorea_hotdeals_2days.json", script)
        self.assertIn("HOTDEAL_EXPECTED_FEED_SOURCES", script)
        self.assertIn("fmkorea", script)

    def test_github_watchdog_dispatches_refresh_when_refresh_workflow_is_stale(self):
        workflow = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('cron: "22,52 * * * *"', workflow)
        self.assertIn('STALE_THRESHOLD_MINUTES: "35"', workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("REFRESH_WORKFLOW: hotdeal-refresh-supabase.yml", workflow)
        self.assertIn("actions/workflows/{workflow}/runs?per_page=20", workflow)
        self.assertIn("latest_success", workflow)
        self.assertIn("stale = (not active) and age_minutes > threshold", workflow)
        self.assertIn("gh workflow run", workflow)

    def test_fmkorea_parser_has_actions_diagnostics_and_desktop_fallback(self):
        script = FMKOREA_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("LIST_URL_CANDIDATES", script)
        self.assertIn("https://www.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine", script)
        self.assertIn("write_fmkorea_diagnostics", script)
        self.assertIn("WARN_FMKOREA_ZERO_ITEMS_DIAGNOSTIC", script)
        self.assertIn("FMKOREA_DIAGNOSTIC_DIR", script)


if __name__ == "__main__":
    unittest.main()
