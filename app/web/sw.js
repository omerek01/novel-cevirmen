// SHELL_CACHE: statik kabuk, sürümle değişir → activate'te eskisi silinir.
// DATA_CACHE: /api yanıtları (bölümler dahil), SABİT isim → sürüm artışı
// çevrimdışı indirilen bölümleri asla silmez.
const SHELL_CACHE = "novellink-shell-v55"; // tür-bazlı raflar (Noveller/Mangalar/Kitaplar) + SVG ikon + focus/hover cilası
const DATA_CACHE = "novellink-data";
const SHELL = [
  "/",
  "/index.html",
  "/style.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icon.svg",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  // cache: "reload" → kabuk HTTP önbelleğini ATLAYARAK ağdan indirilir. Aksi
  // halde addAll bayat app.js/style.css'i "yeni sürüm" diye paketleyebiliyordu
  // (QA bulgusu: kabuk güncellenmiyor / eskiye dönüyor).
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "reload" }))))
  );
  self.skipWaiting();
});

// Eski birleşik önbelleklerden (novellink-v*) /api girişlerini DATA_CACHE'e taşı,
// sonra sil — bu güncelleme indirilen bölümleri yok etmesin.
async function migrateOldCaches() {
  const keys = await caches.keys();
  const data = await caches.open(DATA_CACHE);
  for (const key of keys) {
    if (key === SHELL_CACHE || key === DATA_CACHE) continue;
    const old = await caches.open(key);
    for (const req of await old.keys()) {
      if (!new URL(req.url).pathname.startsWith("/api/")) continue;
      if (await data.match(req)) continue; // yenisi varsa üzerine yazma
      const res = await old.match(req);
      if (res) await data.put(req, res);
    }
    await caches.delete(key);
  }
}

self.addEventListener("activate", (event) => {
  event.waitUntil(migrateOldCaches());
  self.clients.claim();
});

// Tailscale kapalıyken ts.net adresine giden istekler hata vermek yerine dakikalarca
// askıda kalır (kara delik) → önbelleğe düşüş hiç tetiklenmez. Zaman aşımı bunu keser.
async function fetchWithTimeout(request, ms) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(request, { signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

// Çevrilmiş bölüm kalıcıdır → önce önbellek (çevrimdışı okunur), yoksa ağdan al + sakla.
// refresh=1 ise ağa git ve aynı bölümün önbelleğini güncelle.
// Zaman aşımı YOK: ilk çeviri / yeniden çeviri sunucuda 30-60 sn sürebilir.
async function chapterFirst(request, cacheKey, forceNetwork) {
  const cache = await caches.open(DATA_CACHE);
  if (!forceNetwork) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
  }
  try {
    const res = await fetch(request);
    // "translating" gibi GEÇİCİ yanıtları (no-store) ASLA cache'leme: anahtardan
    // track silindiği için poll aynı anahtara düşer, bayat placeholder'a kilitlenir
    // ve sayfa asla html'e dönmezdi. Nihai bölüm (html/çeviri) normalce saklanır.
    if (res.ok && res.headers.get("Cache-Control") !== "no-store") {
      cache.put(cacheKey, res.clone());
    }
    return res;
  } catch (err) {
    const hit = await cache.match(cacheKey); // refresh çevrimdışıysa eskiye düş
    if (hit) return hit;
    throw err;
  }
}

// Liste/sözlük (GET): çevrimiçiyken taze, sunucuya ulaşılamıyorsa (hata VEYA 4 sn
// yanıtsızlık) son kayıt.
async function networkFirst(request) {
  const cache = await caches.open(DATA_CACHE);
  try {
    const res = await fetchWithTimeout(request, 4000);
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
    key.searchParams.delete("track"); // track (konum ilerlet) da aynı bölüm = aynı anahtar
    event.respondWith(chapterFirst(request, key.toString(), refresh));
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(request)); // /api/books, /chapters, /glossary (GET)
    return;
  }

  event.respondWith(cacheFirst(request));
});
