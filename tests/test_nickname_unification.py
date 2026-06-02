import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_JS = ROOT / 'assets' / 'anonymous-identity.js'


class NicknameUnificationTests(unittest.TestCase):
    def test_identity_get_nickname_prefers_cached_account_nickname(self):
        js = IDENTITY_JS.read_text(encoding='utf-8')
        self.assertIn('function readAccountNickname(){', js)
        self.assertIn('const accountNickname = readAccountNickname();', js)
        self.assertIn('if(accountNickname) return accountNickname;', js)

    def test_api_identity_headers_use_unified_account_nickname(self):
        js = IDENTITY_JS.read_text(encoding='utf-8')
        self.assertIn("headers.set('X-Gaji-Nickname', headerSafe(getNickname()));", js)
        self.assertIn('parsed.nickname = parsed.nickname || getNickname();', js)
        self.assertIn('parsed.author = parsed.author || getNickname();', js)


if __name__ == '__main__':
    unittest.main()
