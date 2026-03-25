/**
 * Service Worker for Lumira PWA
 *
 * Provides offline support, caching, and background sync.
 */

const CACHE_VERSION = 'lumira-v1.0.1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const IMAGE_CACHE = `${CACHE_VERSION}-images`;

// Files to cache on install
const STATIC_FILES = [
  '/',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  '/static/images/logo.png',
  '/manifest.json',
  '/offline.html',
];

// Cache limits
const CACHE_LIMITS = {
  images: 50,      // Max 50 images in cache
  dynamic: 30,     // Max 30 dynamic pages
};

/**
 * Install event - cache static assets
 */
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');

  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_FILES);
      })
      .then(() => self.skipWaiting())
      .catch((error) => {
        console.error('[SW] Install failed:', error);
      })
  );
});

/**
 * Activate event - clean up old caches
 */
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');

  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name.startsWith('lumira-') && name !== STATIC_CACHE && name !== DYNAMIC_CACHE && name !== IMAGE_CACHE)
            .map((name) => {
              console.log('[SW] Deleting old cache:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => self.clients.claim())
  );
});

/**
 * Fetch event - serve from cache, fallback to network
 */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip chrome-extension and other schemes
  if (!url.protocol.startsWith('http')) {
    return;
  }

  // Handle API requests - network first, cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Handle images - cache first, network fallback
  if (url.pathname.startsWith('/gallery/') || url.pathname.match(/\.(jpg|jpeg|png|gif|webp)$/)) {
    event.respondWith(cacheFirst(request, IMAGE_CACHE));
    return;
  }

  // Handle static assets - cache first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Default - network first, cache fallback
  event.respondWith(networkFirst(request));
});

/**
 * Cache first strategy
 */
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  if (cached) {
    console.log('[SW] Serving from cache:', request.url);
    return cached;
  }

  try {
    const response = await fetch(request);

    if (response.ok) {
      console.log('[SW] Caching new resource:', request.url);
      cache.put(request, response.clone());

      // Limit cache size
      if (cacheName === IMAGE_CACHE) {
        limitCacheSize(cacheName, CACHE_LIMITS.images);
      }
    }

    return response;
  } catch (error) {
    console.error('[SW] Fetch failed:', error);

    // Return offline page for navigation requests
    if (request.mode === 'navigate') {
      const offlineResponse = await cache.match('/offline.html');
      if (offlineResponse) {
        return offlineResponse;
      }
    }

    throw error;
  }
}

/**
 * Network first strategy
 */
async function networkFirst(request) {
  const cache = await caches.open(DYNAMIC_CACHE);

  try {
    const response = await fetch(request);

    if (response.ok) {
      console.log('[SW] Caching dynamic resource:', request.url);
      cache.put(request, response.clone());
      limitCacheSize(DYNAMIC_CACHE, CACHE_LIMITS.dynamic);
    }

    return response;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);
    const cached = await cache.match(request);

    if (cached) {
      return cached;
    }

    throw error;
  }
}

/**
 * Limit cache size by deleting oldest entries
 */
async function limitCacheSize(cacheName, maxItems) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();

  if (keys.length > maxItems) {
    console.log(`[SW] Cache ${cacheName} exceeded limit, cleaning up...`);
    // Delete oldest entries (first in = first out)
    await cache.delete(keys[0]);
    limitCacheSize(cacheName, maxItems); // Recursive until under limit
  }
}

/**
 * Background sync for failed requests
 */
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);

  if (event.tag === 'sync-artworks') {
    event.waitUntil(syncArtworks());
  }
});

/**
 * Sync artworks in background
 */
async function syncArtworks() {
  try {
    console.log('[SW] Syncing artworks...');
    // Refresh gallery images cache
    const response = await fetch('/api/images?limit=50');

    if (response.ok) {
      console.log('[SW] Artworks synced successfully');
    }
  } catch (error) {
    console.error('[SW] Sync failed:', error);
    throw error; // Retry sync
  }
}

/**
 * Push notification handler
 */
self.addEventListener('push', (event) => {
  console.log('[SW] Push notification received');

  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Lumira - New Artwork';
  const options = {
    body: data.body || 'A new artwork has been created',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    tag: data.tag || 'lumira-notification',
    data: data.url || '/',
    actions: [
      { action: 'view', title: 'View' },
      { action: 'close', title: 'Close' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

/**
 * Notification click handler
 */
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked:', event.action);

  event.notification.close();

  if (event.action === 'view' || !event.action) {
    const url = event.notification.data || '/';

    event.waitUntil(
      clients.openWindow(url)
    );
  }
});

console.log('[SW] Service worker loaded');
