import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BoardCacheReconciliationTests(unittest.TestCase):
    def test_remote_board_list_replaces_stale_local_cache(self):
        html = (ROOT / "board.html").read_text(encoding="utf-8")

        self.assertIn("const STORAGE_KEY = 'gaji_board_posts_v2';", html)
        self.assertIn("const LEGACY_STORAGE_KEY = 'gaji_board_posts_v1';", html)
        self.assertIn("localStorage.removeItem(LEGACY_STORAGE_KEY);", html)
        self.assertIn("state.posts = remote;", html)
        self.assertIn("saveLocalPosts(remote);", html)
        self.assertNotIn("mergePosts(remote, local)", html)
        self.assertNotIn("state.posts = local;\n      renderList();\n      try", html)

    def test_deleted_detail_is_removed_from_local_cache(self):
        for page in ("board.html", "boarddetail.html"):
            html = (ROOT / page).read_text(encoding="utf-8")

            self.assertIn("if(res.status === 404)", html)
            self.assertIn(
                "saveLocalPosts(readLocalPosts().filter(post => String(post.id) !== String(id)));",
                html,
            )


if __name__ == "__main__":
    unittest.main()
