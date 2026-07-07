import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AuthSessionPersistenceTests(unittest.TestCase):
    def test_google_redirect_uri_defaults_to_current_origin(self):
        auth_js = (ROOT / 'api' / 'auth.js').read_text(encoding='utf-8')
        self.assertIn("return configured || `${getBaseUrl(req)}/api/auth`;", auth_js)
        self.assertNotIn("https://hotdeal-omega.vercel.app/api/auth').trim()", auth_js)

    def test_session_cookie_is_secure_on_non_local_hosts(self):
        auth_lib = (ROOT / 'api' / '_lib' / 'auth.js').read_text(encoding='utf-8')
        self.assertIn("req.headers['x-forwarded-host'] || req.headers.host", auth_lib)
        self.assertIn('const localHost = ', auth_lib)
        self.assertIn('const secure = proto === \'https\' || (host && !localHost);', auth_lib)


if __name__ == '__main__':
    unittest.main()
