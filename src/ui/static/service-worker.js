/**
 * Service Worker for Open Assistant PWA
 * Provides offline functionality and caching strategies
 *
 * Uses self.registration.scope to derive the base path at runtime,
 * so the same SW file works both at root (/) and under instance
 * prefixes (/i/{slug}/) in managed deployments.
 */

const CACHE_VERSION = 'v3';
const CACHE_NAME = `personal-assistant-${CACHE_VERSION}`;

// Derive base path from the SW's own registration scope.
// Standalone: scope is "https://host/"  →  BASE_PATH = ""
// Managed:    scope is "https://host/i/slug/"  →  BASE_PATH = "/i/slug"
const BASE_PATH = new URL(self.registration.scope).pathname.replace(/\/$/, '');

// Assets to cache immediately on install
const STATIC_ASSETS = [
    BASE_PATH + '/',
    BASE_PATH + '/settings',
    BASE_PATH + '/monitoring',
    BASE_PATH + '/static/css/common.css',
    BASE_PATH + '/static/js/common.js',
    BASE_PATH + '/static/js/chat.js',
    BASE_PATH + '/static/js/settings.js',
    BASE_PATH + '/static/robot-logo.svg',
    BASE_PATH + '/static/favicon.ico'
];

// API routes that should be cached with network-first strategy
const API_ROUTES = [
    BASE_PATH + '/api/conversations',
    BASE_PATH + '/api/settings',
    BASE_PATH + '/health'
];

/**
 * Install event - cache static assets
 */
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing...');

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[Service Worker] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => {
                console.log('[Service Worker] Skip waiting');
                return self.skipWaiting();
            })
            .catch((error) => {
                console.error('[Service Worker] Installation failed:', error);
            })
    );
});

/**
 * Activate event - clean up old caches
 */
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating...');

    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name !== CACHE_NAME)
                        .map((name) => {
                            console.log('[Service Worker] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => {
                console.log('[Service Worker] Claiming clients');
                return self.clients.claim();
            })
    );
});

/**
 * Fetch event - implement caching strategies
 */
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Skip cross-origin requests
    if (url.origin !== location.origin) {
        return;
    }

    // Handle GET API requests with network-first strategy.
    // Non-GET requests (POST, PUT, DELETE) bypass the service worker so that
    // real server errors are surfaced instead of a synthetic "Offline" 503.
    if (url.pathname.startsWith(BASE_PATH + '/api/') && request.method === 'GET') {
        event.respondWith(networkFirst(request));
        return;
    }

    // Handle static assets with cache-first strategy
    if (url.pathname.startsWith(BASE_PATH + '/static/')) {
        event.respondWith(cacheFirst(request));
        return;
    }

    // Handle HTML pages with network-first strategy
    if (request.headers.get('accept')?.includes('text/html')) {
        event.respondWith(networkFirst(request));
        return;
    }

    // Default: try network first, fallback to cache
    event.respondWith(networkFirst(request));
});

/**
 * Cache-first strategy: Check cache first, fallback to network
 */
async function cacheFirst(request) {
    try {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            console.log('[Service Worker] Cache hit:', request.url);
            return cachedResponse;
        }

        console.log('[Service Worker] Cache miss, fetching:', request.url);
        const networkResponse = await fetch(request);

        // Cache successful responses
        if (networkResponse.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }

        return networkResponse;
    } catch (error) {
        console.error('[Service Worker] Cache-first failed:', error);
        return new Response('Offline - Asset not available', {
            status: 503,
            statusText: 'Service Unavailable'
        });
    }
}

/**
 * Network-first strategy: Try network first, fallback to cache
 */
async function networkFirst(request) {
    try {
        const networkResponse = await fetch(request);

        // Cache successful GET requests
        if (networkResponse.ok && request.method === 'GET') {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }

        return networkResponse;
    } catch (error) {
        console.log('[Service Worker] Network failed, trying cache:', request.url);

        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }

        // Return offline page for HTML requests
        if (request.headers.get('accept')?.includes('text/html')) {
            return new Response(
                `<!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Offline - Open Assistant</title>
                    <style>
                        body {
                            font-family: 'Courier New', monospace;
                            background: #0a0a0a;
                            color: #00ff00;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            margin: 0;
                            text-align: center;
                        }
                        .offline-container {
                            padding: 20px;
                        }
                        h1 {
                            font-size: 2rem;
                            margin-bottom: 1rem;
                            text-shadow: 0 0 10px rgba(0, 255, 0, 0.5);
                        }
                        p {
                            font-size: 1.2rem;
                            color: #ffffff;
                        }
                        button {
                            margin-top: 2rem;
                            padding: 12px 24px;
                            background: rgba(0, 255, 0, 0.1);
                            color: #00ff00;
                            border: 2px solid #00ff00;
                            border-radius: 8px;
                            cursor: pointer;
                            font-size: 1rem;
                            font-family: inherit;
                        }
                        button:hover {
                            background: rgba(0, 255, 0, 0.2);
                        }
                    </style>
                </head>
                <body>
                    <div class="offline-container">
                        <h1>📡 You're Offline</h1>
                        <p>No internet connection detected.</p>
                        <p>Some features may not be available.</p>
                        <button onclick="window.location.reload()">Retry</button>
                    </div>
                </body>
                </html>`,
                {
                    headers: { 'Content-Type': 'text/html' },
                    status: 503,
                    statusText: 'Service Unavailable'
                }
            );
        }

        return new Response('Offline', {
            status: 503,
            statusText: 'Service Unavailable'
        });
    }
}

/**
 * Handle messages from clients
 */
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }

    if (event.data && event.data.type === 'CACHE_URLS') {
        event.waitUntil(
            caches.open(CACHE_NAME)
                .then((cache) => cache.addAll(event.data.urls))
        );
    }
});

/**
 * Handle push notifications (optional, for future use)
 */
self.addEventListener('push', (event) => {
    if (!event.data) return;

    const data = event.data.json();
    const options = {
        body: data.body || 'New notification',
        icon: BASE_PATH + '/static/icons/icon-192x192.png',
        badge: BASE_PATH + '/static/icons/icon-72x72.png',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: data.id
        },
        actions: [
            {
                action: 'explore',
                title: 'View',
                icon: BASE_PATH + '/static/icons/icon-72x72.png'
            },
            {
                action: 'close',
                title: 'Dismiss',
                icon: BASE_PATH + '/static/icons/icon-72x72.png'
            }
        ]
    };

    event.waitUntil(
        self.registration.showNotification(data.title || 'Open Assistant', options)
    );
});

/**
 * Handle notification clicks
 */
self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    if (event.action === 'explore') {
        event.waitUntil(
            clients.openWindow(BASE_PATH + '/')
        );
    }
});

console.log('[Service Worker] Loaded successfully');
