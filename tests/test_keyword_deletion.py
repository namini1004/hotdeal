import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
KEYWORDS_API = ROOT / "api" / "push" / "keywords.js"
INGEST_API = ROOT / "api" / "push" / "ingest.js"
KEYWORDS_PAGE = ROOT / "keywords.html"
NODE = shutil.which("node") or str(ROOT / ".tools" / "node-v24.14.0-win-x64" / "node.exe")


class KeywordDeletionTests(unittest.TestCase):
    def test_keyword_delete_ids_match_subscription_and_pending_window_ids(self):
        script = f"""
          const keywords = require({json.dumps(str(KEYWORDS_API))});
          const ingest = require({json.dumps(str(INGEST_API))});
          const uid = 'google:user-1';
          const term = keywords.normalizeTerm(' Nintendo  Switch ');
          console.log(JSON.stringify({{
            keywordId: keywords.makeId(term),
            indexId: keywords.makeIndexId(uid, term),
            windowId: ingest.keywordWindowId(uid, term),
            enabled: ingest.isEnabledKeywordSubscription({{ exists: true, get: () => true }}),
            deleted: ingest.isEnabledKeywordSubscription({{ exists: false, get: () => true }})
          }}));
        """

        data = json.loads(subprocess.check_output([NODE, "-e", script], cwd=ROOT, text=True))

        self.assertEqual(data["indexId"], data["windowId"])
        self.assertTrue(data["enabled"])
        self.assertFalse(data["deleted"])

    def test_delete_removes_pending_window_and_rechecks_before_push(self):
        keywords_api = KEYWORDS_API.read_text(encoding="utf-8")
        ingest_api = INGEST_API.read_text(encoding="utf-8")
        page = KEYWORDS_PAGE.read_text(encoding="utf-8")

        self.assertIn("collection('keyword_alert_windows').doc(subscriptionId)", keywords_api)
        self.assertIn("indexRef.where('uid', '==', uid)", keywords_api)
        self.assertIn("if (alertPlan.action === 'skip')", ingest_api)
        self.assertIn("data-term=", page)
        self.assertIn("body: JSON.stringify({ id, termNormalized })", page)


if __name__ == "__main__":
    unittest.main()
