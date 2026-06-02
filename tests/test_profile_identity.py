import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProfileIdentityTests(unittest.TestCase):
    def test_my_gaji_account_card_uses_real_login_name(self):
        html = (ROOT / 'my-gaji.html').read_text(encoding='utf-8')
        self.assertIn('function accountDisplayName(user)', html)
        self.assertIn('const realName = String(user.name || \'\').trim();', html)
        self.assertIn('if(realName) return realName;', html)
        self.assertIn('updateNicknameSurfaces(user);', html)

    def test_nickname_sync_preserves_google_account_identity(self):
        html = (ROOT / 'nickname.html').read_text(encoding='utf-8')
        self.assertIn('localStorage.setItem(\'gaji_auth_user_cache_v1\', JSON.stringify({ ...cached, nickname:value }));', html)
        self.assertNotIn('nickname:value, name:value, avatar:\'\'', html)
        self.assertIn('localStorage.removeItem(\'gaji_profile_updated_at_v1\');', html)

    def test_pending_nickname_is_account_scoped_not_device_global(self):
        for page in ['my-gaji.html', 'nickname.html']:
            html = (ROOT / page).read_text(encoding='utf-8')
            self.assertIn('gaji_profile_pending_nickname_v1', html)
            self.assertIn('function userAccountKey(user)', html)
            self.assertNotIn('return Boolean(localStorage.getItem(\'gaji_profile_updated_at_v1\'));', html)


if __name__ == '__main__':
    unittest.main()
