/* ==========================================================================
   Campus Bus Gate Monitoring System - Service Worker (sw.js)
   PWA offline caching, install lifecycle, and live stream pass-through
   ========================================================================== */

const CACHE_NAME = 'bus-monitor-v1';
const STATIC_ASSETS = [
    '/',
    '/login',
    '/static/css/style.css',
    '/static/js/script.js',
    '/static/manifest.json',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/static/icons/favicon-32.png',
    '/static/icons/apple-touch-icon.png'
];

// Install event - precache core app shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        }).then(() => self.skipWaiting())
    );
});

// Activate event - purge outdated caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch event
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Bypass caching for live MJPEG video feeds, snapshot uploads, or dynamic APIs
    if (
        url.pathname.includes('/video_feed') ||
        url.pathname.startsWith('/api/') ||
        event.request.method !== 'GET'
    ) {
        return;
    }

    // Network-first strategy with cache fallback for HTML and assets
    event.respondWith(
        fetch(event.request)
            .then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const responseClone = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }
                return networkResponse;
            })
            .catch(() => {
                return caches.match(event.request).then((cachedResponse) => {
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    if (event.request.headers.get('accept')?.includes('text/html')) {
                        return caches.match('/');
                    }
                });
            })
    );
});
