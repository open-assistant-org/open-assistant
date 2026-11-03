/**
 * Service Worker for Open Assistant PWA
 * Provides offline functionality and caching strategies
 *
 * Uses self.registration.scope to derive the base path at runtime,
 * so the same SW file works both at root (/) and under instance
 * prefixes (/i/{slug}/) in managed deployments.
 */

// v4: components.js nav links now carry the INSTANCE_BASE_PATH prefix
// (managed instances navigated to /settings etc. instead of /i/{slug}/settings).
// v5: light/dark/system theme support - common.css now carries a
// [data-theme="light"] override block and a new static/js/theme.js
// resolves the theme pre-paint. Bump forces stale clients to fetch both.
// v6: Browser integration card gained the "Authenticated sessions" section
// (settings.js + common.css). Bump forces stale clients to fetch both.
// v7: new design system - css/ split into tokens/base/components/common/
// mobile + pages/*, self-hosted Inter in static/fonts, new brand mark and
// icons. Bump forces stale clients to drop the old green theme.
// v8: Lucide icon sprite, Geist Mono for code, calmer (less green) states,
// restyled offline page.
// v9: design feedback pass - trash icon buttons, in-app confirm dialogs,
// right-aligned actions, softer input focus. Bump so clients refetch CSS/JS.
const CACHE_VERSION = 'v9';
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
    BASE_PATH + '/static/css/tokens.css',
    BASE_PATH + '/static/css/base.css',
    BASE_PATH + '/static/css/components.css',
    BASE_PATH + '/static/css/common.css',
    BASE_PATH + '/static/css/mobile.css',
    BASE_PATH + '/static/css/pages/chat.css',
    BASE_PATH + '/static/fonts/inter-latin-wght-normal.woff2',
    BASE_PATH + '/static/js/theme.js',
    BASE_PATH + '/static/js/components.js',
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
                        /* Mirrors css/tokens.css; self-contained because the
                           network (and so every stylesheet) is unavailable. */
                        :root {
                            color-scheme: light dark;
                            --bg: #f7f7f5; --surface: #ffffff; --border: #e1e1dc;
                            --text: #1c1c1a; --text-2: #585853;
                            --accent: #1c1c1a; --on-accent: #ffffff;
                        }
                        @media (prefers-color-scheme: dark) {
                            :root {
                                --bg: #121211; --surface: #1b1b19; --border: #2f2f2c;
                                --text: #ededea; --text-2: #b5b5af;
                                --accent: #ededea; --on-accent: #121211;
                            }
                        }
                        body {
                            font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
                            background: var(--bg);
                            color: var(--text);
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                            margin: 0;
                            padding: 20px;
                            box-sizing: border-box;
                            text-align: center;
                            -webkit-font-smoothing: antialiased;
                        }
                        .offline-container {
                            max-width: 380px;
                            padding: 40px 32px 32px;
                            background: var(--surface);
                            border: 1px solid var(--border);
                            border-radius: 20px;
                        }
                        .offline-icon {
                            display: inline-flex;
                            align-items: center;
                            justify-content: center;
                            width: 48px;
                            height: 48px;
                            margin-bottom: 16px;
                            border-radius: 999px;
                            background: var(--bg);
                            color: var(--text-2);
                        }
                        h1 {
                            font-size: 1.25rem;
                            font-weight: 600;
                            letter-spacing: -0.015em;
                            margin: 0 0 8px;
                        }
                        p {
                            font-size: 0.9375rem;
                            line-height: 1.55;
                            color: var(--text-2);
                            margin: 0;
                        }
                        button {
                            margin-top: 24px;
                            height: 40px;
                            padding: 0 20px;
                            background: var(--accent);
                            color: var(--on-accent);
                            border: none;
                            border-radius: 10px;
                            cursor: pointer;
                            font: inherit;
                            font-size: 0.875rem;
                            font-weight: 500;
                        }
                    </style>
                </head>
                <body>
                    <div class="offline-container">
                        <span class="offline-icon">
                            <!-- Lucide "wifi-off" (ISC) -->
                            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h.01"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/><path d="M5 12.859a10 10 0 0 1 5.17-2.69"/><path d="M19 12.859a10 10 0 0 0-2.007-1.523"/><path d="M2 8.82a15 15 0 0 1 4.177-2.643"/><path d="M22 8.82a15 15 0 0 0-11.288-3.764"/><path d="m2 2 20 20"/></svg>
                        </span>
                        <h1>You're offline</h1>
                        <p>We can't reach your assistant right now. Check your connection and try again.</p>
                        <button onclick="window.location.reload()">Try again</button>
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
