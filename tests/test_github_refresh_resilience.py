import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = ROOT / ".github" / "workflows" / "hotdeal-refresh-supabase.yml"
WATCHDOG_WORKFLOW = ROOT / ".github" / "workflows" / "hotdeal-refresh-watchdog.yml"
FMKOREA_SCRIPT = ROOT / "scripts" / "update_fmkorea_feed.py"


class GithubRefreshResilienceTests(unittest.TestCase):
    def test_refresh_schedule_uses_offset_minutes_to_avoid_busy_cron_slots(self):
        workflow = REFRESH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('cron: "7,22,37,52 * * * *"', workflow)
        self.assertNotIn('cron: "*/15 * * * *"', workflow)

    def test_refresh_workflow_runs_sources_as_independent_jobs_before_upsert(self):
        workflow = REFRESH_WORKFLOW.read_text(encoding="utf-8")

        for job in ("refresh-ppomppu", "refresh-quasar", "refresh-fmkorea", "refresh-ruliweb"):
            self.assertIn(f"  {job}:", workflow)
        self.assertIn("name: Download refreshed feed artifacts", workflow)
        self.assertIn("name: Remove checkout feed snapshots before artifact merge", workflow)
        self.assertIn("needs.refresh-fmkorea.result == 'success'", workflow)

    def test_github_watchdog_dispatches_refresh_when_site_feed_is_stale(self):
        workflow = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('cron: "13,28,43,58 * * * *"', workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("hotdeal-refresh-supabase.yml", workflow)
        self.assertIn("STALE_THRESHOLD_MINUTES", workflow)
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
