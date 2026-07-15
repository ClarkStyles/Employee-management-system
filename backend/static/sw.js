const CACHE_NAME = 'srs-cache-v2';
const API_QUEUE = 'srs-api-queue';

const APP_SHELL = [
    '/',
    '/static/index.html',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/ws.js',
    '/static/js/api.js',
    '/static/js/employee.js',
    '/static/js/manager.js',
    '/static/manifest.json',
    'https://cdn.jsdelivr.net/npm/idb@7/build/umd.js'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
        .then(cache => cache.addAll(APP_SHELL))
        .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    
    // For API calls, try network first, then cache (for GET)
    if (url.pathname.startsWith('/api/')) {
        if (event.request.method === 'GET') {
            event.respondWith(
                fetch(event.request)
                .then(res => {
                    const resClone = res.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, resClone));
                    return res;
                })
                .catch(() => caches.match(event.request))
            );
        }
        return; // Don't intercept POST/PUT here; let app handle queue
    }

    // For static files (app shell), cache first
    event.respondWith(
        caches.match(event.request).then(res => {
            return res || fetch(event.request);
        })
    );
});

// Background sync for offline queue
self.addEventListener('sync', event => {
    if (event.tag === 'sync-api') {
        event.waitUntil(processQueue());
    }
});

async function processQueue() {
    // Open DB via idb wrapper (assuming it's loaded, but in SW we might need to importScripts or handle raw indexedDB)
    // To keep it simple without importing idb in SW, we'll let the app.js handle retries when it comes back online via 'online' event.
    // Full background sync API is not universally supported anyway. 
    // The api.js will listen for 'online' and drain the queue itself.
    console.log("Sync event triggered, but letting main thread handle it for simplicity.");
}
