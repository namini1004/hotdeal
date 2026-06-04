import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PwaAndFavoritePersistenceTests(unittest.TestCase):
    def test_manifest_and_service_worker_are_registered_on_core_pages(self):
        manifest = json.loads((ROOT / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['scope'], '/')
        icon_srcs = [icon['src'] for icon in manifest['icons']]
        self.assertIn('/assets/favicon.svg', icon_srcs)
        self.assertIn('/assets/pwa-icon-192.png', icon_srcs)
        self.assertIn('/assets/pwa-icon-512.png', icon_srcs)

        service_worker = (ROOT / 'service-worker.js').read_text(encoding='utf-8')
        self.assertIn("if (url.pathname.startsWith('/api/')) return;", service_worker)
        self.assertIn("caches.open(CACHE_NAME)", service_worker)

        for page in ['index.html', 'indexdetail.html', 'my-gaji.html', 'favorites.html']:
            html = (ROOT / page).read_text(encoding='utf-8')
            self.assertIn('<link rel="manifest" href="/manifest.webmanifest" />', html)
            self.assertIn("navigator.serviceWorker.register('/service-worker.js')", html)

        index = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="pwaInstallCard"', index)
        self.assertIn("beforeinstallprompt", index)
        self.assertIn("bindPwaInstallPrompt()", index)
        self.assertIn("gaji_pwa_install_dismissed_at_v1", index)

    def test_favorites_are_persisted_through_existing_deals_api(self):
        deals_api = (ROOT / 'api' / 'deals.js').read_text(encoding='utf-8')
        self.assertIn("action === 'favorites'", deals_api)
        self.assertIn("action === 'favorite'", deals_api)
        self.assertIn('favorite_deals?user_id=eq.', deals_api)
        self.assertIn('on_conflict=user_id,deal_key', deals_api)

        detail = (ROOT / 'indexdetail.html').read_text(encoding='utf-8')
        self.assertIn('async function loadRemoteFavorites()', detail)
        self.assertIn('async function syncFavorite(item, on)', detail)
        self.assertIn('!data.remoteDisabled', detail)

        favorites = (ROOT / 'favorites.html').read_text(encoding='utf-8')
        self.assertIn('/api/deals?action=favorites', favorites)
        self.assertIn("fetch('/api/deals?scope=all'", favorites)
        self.assertIn('!d.remoteDisabled', favorites)


if __name__ == '__main__':
    unittest.main()
