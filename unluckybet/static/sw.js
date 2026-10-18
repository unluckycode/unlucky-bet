/* Service worker Unlucky Bet: powłoka aplikacji offline, ostatnio pobrane strony, powiadomienia push. */
const VERSION = 'ub-v3';
const SHELL = [
  '/offline',
  '/static/style.css?v=3',
  '/static/app.js?v=3',
  '/static/vendor/chart.umd.min.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin || url.pathname.startsWith('/api/') || url.pathname === '/login' || url.pathname === '/logout') return;

  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest') {
    // Stale-while-revalidate dla plików statycznych.
    event.respondWith(caches.open(VERSION).then(async (cache) => {
      const cached = await cache.match(req);
      const network = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => cached);
      return cached || network;
    }));
    return;
  }

  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    // Network-first: świeże dane, a bez sieci ostatnio zapisana wersja strony.
    event.respondWith(
      fetch(req).then((res) => {
        if (res.ok && !res.redirected) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(async () => (await caches.match(req)) || (await caches.match('/offline')))
    );
  }
});

self.addEventListener('push', (event) => {
  let data = { title: 'Unlucky Bet', body: 'Nowe zdarzenie', url: '/' };
  try { data = Object.assign(data, event.data ? event.data.json() : {}); } catch (e) { data.body = event.data ? event.data.text() : data.body; }
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/badge-96.png',
    data: { url: data.url || '/' },
    tag: data.url || 'ub',
    renotify: true,
    lang: 'pl',
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
    for (const w of wins) {
      if ('focus' in w) { w.navigate(target); return w.focus(); }
    }
    return self.clients.openWindow(target);
  }));
});
