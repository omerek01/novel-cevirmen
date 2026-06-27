const CACHE = "novellink-v13";
const SHELL = [
  "/",
  "/index.html",
  "/style.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Çevrilmiş bölüm kalıcıdır → önce önbellek (çevrimdışı okunur), yoksa ağdan al + sakla.
// refresh=1 ise ağa git ve aynı bölümün önbelleğini güncelle.
async function chapterFirst(request, cacheKey, forceNetwork) {
  const cache = await caches.open(CACHE);
  if (!forceNetwork) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
  }
  try {
    const res = await fetch(request);
    if (res.ok) cache.put(cacheKey, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(cacheKey); // refresh çevrimdışıysa eskiye düş
    if (hit) return hit;
    throw err;
  }
}

// Liste/sözlük (GET): çevrimiçiyken taze, çevrimdışıyken son kayıt.
async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(request);
    if (res.ok) cache.put(request, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(request);
    if (hit) return hit;
    throw err;
  }
}

// Kabuk/statik dosyalar: önce önbellek.
async function cacheFirst(request) {
  const hit = await caches.match(request);
  return hit || fetch(request);
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  // POST/DELETE (sözlük yazma) → asla önbelleğe alma, doğrudan ağa.
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname === "/api/chapter") {
    const refresh = url.searchParams.get("refresh") === "1";
    const key = new URL(url);
    key.searchParams.delete("refresh"); // refresh'li/refresh'siz aynı bölüm = aynı anahtar
    event.respondWith(chapterFirst(request, key.toString(), refresh));
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(request)); // /api/books, /chapters, /glossary (GET)
    return;
  }

  event.respondWith(cacheFirst(request));
});
