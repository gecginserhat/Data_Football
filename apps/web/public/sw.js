/* Kurgu hizmet çalışanı (PWA, SPEC §13.1: canlı kayıt çevrimdışı çalışır).
 *
 * - /_next/static ve simgeler: önce önbellek (dosya adları içerik özetiyle değişir).
 * - /live sayfaları: önce ağ, ağ yoksa son kaydedilen sayfa. Kayıtlar IndexedDB'de durur.
 * - /api/* ve diğer istekler önbelleğe alınmaz (veri her zaman sunucudan gelir).
 */
const VERSION = "kurgu-v1";
const STATIC_CACHE = `${VERSION}-static`;
const PAGE_CACHE = `${VERSION}-pages`;
const OFFLINE_PAGES = ["/live"];
const PRECACHE = ["/icons/icon-192.png", "/icons/icon-512.png", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

function isStatic(url) {
  return url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/");
}

function isOfflinePage(url) {
  return OFFLINE_PAGES.some((p) => url.pathname === p || url.pathname.startsWith(`${p}/`));
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(STATIC_CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}

async function savePage(url, response) {
  if (!response.ok || response.redirected || response.type !== "basic") return;
  const cache = await caches.open(PAGE_CACHE);
  await cache.put(url, response);
}

function pageKey(url) {
  return new URL(url.pathname, url.origin).toString();
}

async function networkFirstPage(request, url) {
  try {
    const response = await fetch(request);
    await savePage(pageKey(url), response.clone());
    return response;
  } catch {
    const cached = await caches.match(pageKey(url));
    if (cached) return cached;
    return new Response(
      '<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Çevrimdışı · Kurgu</title><body style="font-family:system-ui;padding:24px;background:#F2F4F1;color:#0F1B16"><h1>Çevrimdışısınız</h1><p>Bu sayfa bu cihazda daha önce açılmadığı için çevrimdışı gösterilemiyor. Canlı kayıt için maç sayfasını bağlantı varken bir kez açın.</p></body></html>',
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (isStatic(url)) {
    event.respondWith(cacheFirst(request));
  } else if (request.mode === "navigate" && isOfflinePage(url)) {
    event.respondWith(networkFirstPage(request, url));
  }
});

/* Sayfa, ilk açılışta (çalışan henüz denetlemiyorken) yüklediği dosyaları bildirir; böylece
 * ilk ziyaretten sonra da çevrimdışı açılabilir. */
self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type !== "warm" || !Array.isArray(data.urls)) return;
  event.waitUntil(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      for (const raw of data.urls.slice(0, 200)) {
        try {
          const url = new URL(raw, self.location.origin);
          if (url.origin !== self.location.origin) continue;
          if (isStatic(url)) {
            if (!(await cache.match(url))) await cache.add(url);
          } else if (isOfflinePage(url)) {
            await savePage(pageKey(url), await fetch(url, { credentials: "same-origin" }));
          }
        } catch {
          // Bir dosya alınamazsa diğerleri yine önbelleğe girer.
        }
      }
    })(),
  );
});
