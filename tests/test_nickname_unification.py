import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_JS = ROOT / 'assets' / 'anonymous-identity.js'


class NicknameUnificationTests(unittest.TestCase):
    def test_identity_get_nickname_ignores_cached_account_nickname(self):
        js = IDENTITY_JS.read_text(encoding='utf-8')
        self.assertNotIn('function readAccountNickname(){', js)
        self.assertNotIn('const accountNickname = readAccountNickname();', js)
        self.assertNotIn('if(accountNickname) return accountNickname;', js)

    def test_google_account_cache_is_not_mutated_by_activity_nickname(self):
        js = IDENTITY_JS.read_text(encoding='utf-8')
        self.assertIn('if(cached && cached.anonymous === false) return cached;', js)
        self.assertNotIn('return writeCachedUser({ ...cached, nickname: clean });', js)

    def test_api_identity_headers_use_activity_nickname(self):
        js = IDENTITY_JS.read_text(encoding='utf-8')
        self.assertIn("headers.set('X-Gaji-Nickname', headerSafe(getNickname()));", js)
        self.assertIn('parsed.nickname = parsed.nickname || getNickname();', js)
        self.assertIn('parsed.author = parsed.author || getNickname();', js)


if __name__ == '__main__':
    unittest.main()
