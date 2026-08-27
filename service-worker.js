const CACHE_NAME = 'gaji-shell-v18';
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/indexdetail.html',
  '/indexcreate.html',
  '/my-gaji.html',
  '/keywords.html',
  '/favorites.html',
  '/assets/favicon.svg',
  '/assets/hotdeal-android-icon.svg',
  '/assets/gaji-eggplant.jpg',
  '/assets/gaji-eggplant-transparent.png',
  '/assets/pwa-icon-192.png',
  '/assets/pwa-icon-512.png',
  '/assets/time-format.js',
  '/assets/text-format.js',
  '/assets/anonymous-identity.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => undefined);
          return res;
        })
        .catch(() => caches.match(req).then((cached) => cached || caches.match('/index.html')))
    );
    return;
  }

  if (req.destination === 'script') {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => undefined);
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).then((res) => {
      if (res.ok && ['style', 'image', 'font'].includes(req.destination)) {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => undefined);
      }
      return res;
    }))
  );
});

function normalizeNotificationUrl(value) {
  try {
    const url = new URL(value || '/index.html', self.location.origin);
    if (url.origin === self.location.origin || url.origin === 'https://gaji.run') return url.href;
  } catch (_) {
    // fall through to home
  }
  return new URL('/index.html', self.location.origin).href;
}

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = {};
  }

  const title = String(data.title || '가지딜 알림');
  const body = String(data.body || '새 딜이 등록됐어요.');
  const url = normalizeNotificationUrl(data.url);

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: data.icon || '/assets/pwa-icon-192.png',
      badge: data.badge || '/assets/pwa-icon-192.png',
      tag: data.tag || data.dealId || 'gaji-keyword-alert',
      renotify: true,
      data: {
        url,
        dealId: data.dealId || '',
        source: data.source || '',
      },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = normalizeNotificationUrl(event.notification?.data?.url);

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          try {
            const clientUrl = new URL(client.url);
            const target = new URL(targetUrl);
            if (clientUrl.origin === target.origin && 'focus' in client) {
              if ('navigate' in client) return client.navigate(targetUrl).then(() => client.focus());
              return client.focus();
            }
          } catch (_) {
            // keep searching
          }
        }
        return self.clients.openWindow(targetUrl);
      })
  );
});
