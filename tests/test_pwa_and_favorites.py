import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PwaAndFavoritePersistenceTests(unittest.TestCase):
    def test_manifest_and_service_worker_are_registered_on_core_pages(self):
        manifest = json.loads((ROOT / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'], '가지')
        self.assertEqual(manifest['short_name'], '가지')
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['scope'], '/')
        icon_srcs = [icon['src'] for icon in manifest['icons']]
        self.assertIn('/assets/hotdeal-android-icon.svg', icon_srcs)
        self.assertIn('/assets/pwa-icon-192.png', icon_srcs)
        self.assertIn('/assets/pwa-icon-512.png', icon_srcs)

        service_worker = (ROOT / 'service-worker.js').read_text(encoding='utf-8')
        self.assertIn("if (url.pathname.startsWith('/api/')) return;", service_worker)
        self.assertIn("caches.open(CACHE_NAME)", service_worker)
        self.assertIn("self.addEventListener('push'", service_worker)
        self.assertIn('showNotification', service_worker)
        self.assertIn("self.addEventListener('notificationclick'", service_worker)

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

    def test_pwa_web_push_extends_android_push_without_replacing_it(self):
        package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
        self.assertIn('web-push', package['dependencies'])

        register_device = (ROOT / 'api' / 'push' / 'register-device.js').read_text(encoding='utf-8')
        self.assertIn('fcmToken', register_device)
        self.assertIn('webPushSubscription', register_device)
        self.assertIn("platform = webPushSubscription ? 'web' : 'android'", register_device)
        self.assertIn('getVapidPublicKey', register_device)
        self.assertIn('webPushDeviceId(webPushSubscription)', register_device)
        self.assertIn("req.method === 'DELETE'", register_device)
        self.assertIn('standalone_pwa_registered', register_device)
        self.assertIn('disabledBrowserWebPush', register_device)

        ingest = (ROOT / 'api' / 'push' / 'ingest.js').read_text(encoding='utf-8')
        self.assertIn('sendEachForMulticast', ingest)
        self.assertIn('sendWebPushNotification', ingest)
        self.assertIn('webPushCount', ingest)
        self.assertIn('webPushConfigMissing', ingest)
        self.assertIn('suppressedBrowserWebPushCount', ingest)
        self.assertIn('hasStandaloneWebPush', ingest)
        self.assertIn('KEYWORD_ALERT_WINDOW_MS = 30 * 60 * 1000', ingest)
        self.assertIn('keyword_alert_windows', ingest)
        self.assertIn("status: 'queued'", ingest)
        self.assertIn("reason: 'keyword_throttle'", ingest)
        self.assertIn('buildKeywordDigestPayload', ingest)
        self.assertIn('androidBody: payload.body', ingest)
        self.assertNotIn('androidBody: `${primaryTerm}', ingest)

        self.assertIn('standalone_pwa_active', register_device)
        self.assertIn('suppressedByStandalonePwa', register_device)

        keywords = (ROOT / 'keywords.html').read_text(encoding='utf-8')
        self.assertIn('PushManager', keywords)
        self.assertIn('Notification.requestPermission()', keywords)
        self.assertIn('/api/push/register-device?action=vapid-public-key', keywords)
        self.assertIn('webPushSubscription: subscription.toJSON()', keywords)
        self.assertIn('displayMode: getDisplayMode()', keywords)
        self.assertIn("method:'DELETE'", keywords)
        self.assertIn('넓은 키워드라 알림이 많을 수 있어요', keywords)


if __name__ == '__main__':
    unittest.main()
