"use strict";

const LS_SETTINGS = "novellink:settings";
const LS_SCROLL = "novellink:scroll";
const LS_LASTREAD = "novellink:lastread";
const SCROLL_MAX = 500; // localStorage'da tutulan en fazla bölüm konumu (budama)
const DEFAULT_SETTINGS = {
  theme: "light",
  fontPx: 19,
  font: "serif",
  lineHeight: "normal",
  margin: "normal",
  // Sonsuz okuma: bölüm sonuna gelince sonrakini akışa kendiliğinden ekle. Kapalıyken
  // akış tek bölümdür ve devam elle ("SONRAKİ BÖLÜM →") olur — manga'nın site'den
  // sonraki bölümü çekmesi de aynı anahtara bağlıdır.
  infinite: true,
};
const THEMES = ["light", "sepia", "dark"];
// SVG ikonlar (emoji yerine — temiz çizgi ikon, currentColor). skill kuralı: emoji ikon yok.
const SVG = (p, sz = 22) =>
  `<svg viewBox="0 0 24 24" width="${sz}" height="${sz}" fill="none" stroke="currentColor" ` +
  `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const ICONS = {
  moon: SVG('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
  sun: SVG(
    '<circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6' +
      'M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/>'
  ),
  search: SVG('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.2-4.2"/>'),
  sliders: SVG(
    '<path d="M4 8h11M19 8h1M4 16h4M12 16h8"/><circle cx="16" cy="8" r="2"/><circle cx="9" cy="16" r="2"/>'
  ),
  download: SVG('<path d="M12 3v11M8 11l4 4 4-4M5 20h14"/>', 18),
  // Alt gezinme "Kütüphane" sekmesi: rafta duran iki kitap sırtı + eğik üçüncü —
  // uygulamanın kendi raf metaforunu tekrarlar.
  shelf: SVG('<path d="M4 5h4v14H4zM10 5h4v14h-4zM16.6 5.8l3.4.9-3.1 12.5-3.4-.9z"/>', 18),
};
const THEME_ICON = { light: ICONS.moon, sepia: ICONS.sun, dark: ICONS.sun };
const LINE_HEIGHTS = { sik: "1.5", normal: "1.75", seyrek: "2.1" };
const MARGINS = { dar: "0.8rem", normal: "1.3rem", genis: "2.2rem" };

const el = (id) => document.getElementById(id);
const views = {
  library: el("libraryView"),
  book: el("bookView"),
  glossary: el("glossaryView"),
  reader: el("readerView"),
};

let settings = loadSettings();
let currentUrl = null;
let currentChapterNo = null; // açık bölümün numarası (yerel "son okunan" kaydı + kütüphane etiketi)
let currentChapterTitle = null;
let currentBookSlug = null;
let currentBook = null; // {current_url, current_ratio, ...} — resume için
let currentChapters = []; // açık kitabın tam bölüm listesi (prev türetme + arama)
// --- Sonsuz okuma v2 (D-B9v2): tek-bölüm singleton yerine bölüm AKIŞI ---
// Her bölüm kendi <article data-url> öğesinde; aktif bölüm = reader-bar çizgisini
// geçen SON bölüm (en-çok-görünür değil → titreme önlenir). Konum {url, bölüm-içi
// oran}; aktif değişince history.replaceState (push YOK) → geri jesti okuyucudan çıkar.
let stream = []; // [{url,no,title,paras,source,nextUrl,prevUrl,bookSlug,bookTitle,el,loaded,empty}]
let activeUrl = null; // reader-bar alt çizgisini geçen son bölümün url'i
let streamBusy = false; // append/prepend uçuşta — çift tetiği engelle
let bottomObserver = null; // akış sonu gözlemcisi (sonrakini otomatik ekle)
const loggedReads = new Set(); // bu oturumda reading-log'a yazılmış url'ler
const prefetched = new Set(); // ısıtma (prefetch) tetiklenmiş next url'leri
let sourceLoading = false; // eski bölüm kaynağı yüklenirken çift-istek engeli
let offlineStop = false;
let mangaNextExhausted = false; // manga: site'de sonraki bölüm kalmadı → devam deneme (resetStream'de sıfırlanır)
let isRestoring = false; // programatik scroll sırasında kaydı baskıla
let scrollSaveTimer = null;
let bulkPollTimer = null;
let libraryJobPollTimer = null;
let isNavigating = false;
let failedAttempts = 0;

/* ---------- depolama ---------- */
// null = sunucuya ulaşılamadı (D-PWA-Durum: "boş kütüphane" olarak RENDER EDİLMEZ).
// [] = sunucu cevap verdi ve kütüphane gerçekten boş.
async function fetchBooks() {
  try {
    const res = await fetch("/api/books");
    if (!res.ok) return null;
    const data = await res.json();
    return data.books || [];
  } catch {
    return null;
  }
}

// İstemcinin YEREL günü (YYYY-MM-DD) — "bugün" sayacı gece yarısı UTC'ye kaymaz.
function localDay() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(localStorage.getItem(LS_SETTINGS)) || {}) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}
function saveSettings() {
  localStorage.setItem(LS_SETTINGS, JSON.stringify(settings));
}

/* ---------- kaydırma konumu (oran) ---------- */
function loadScrollMap() {
  try {
    return JSON.parse(localStorage.getItem(LS_SCROLL)) || {};
  } catch {
    return {};
  }
}
// Saf: harita SCROLL_MAX'ı aşarsa en eski eklenenleri at (test edilebilir).
function pruneScrollPositions(map, max) {
  const keys = Object.keys(map);
  if (keys.length <= max) return map;
  for (const k of keys.slice(0, keys.length - max)) delete map[k];
  return map;
}
function saveScrollLocal(url, ratio) {
  const map = loadScrollMap();
  delete map[url]; // yeniden ekle → ekleme sırasında en sona gelsin (LRU benzeri)
  map[url] = ratio;
  pruneScrollPositions(map, SCROLL_MAX);
  try {
    localStorage.setItem(LS_SCROLL, JSON.stringify(map));
  } catch {}
}
function getScrollLocal(url) {
  return loadScrollMap()[url] || 0;
}

/* ---------- son okunan bölüm (kitap başına; çevrimdışı resume için) ----------
   Sunucu "kaldığın yer" işaretini (books.current_url) yalnız çevrimiçiyken günceller.
   Çevrimdışı okurken bölüm SW önbelleğinden gelir, istek sunucuya ulaşmaz → işaret
   ilerlemez. Bu yerel kayıt her bölüm render'ında ilerler; resume iki kaynaktan en
   TAZE olanı seçer, böylece çevrimdışı okunan son bölümden devam edilir. */
function loadLastReadMap() {
  try {
    return JSON.parse(localStorage.getItem(LS_LASTREAD)) || {};
  } catch {
    return {};
  }
}
function saveLastRead(slug, url) {
  if (!slug || !url) return;
  const map = loadLastReadMap();
  // chapter_no/title: kütüphane sırtı "BÖL. N" etiketini çevrimdışı okumaya göre
  // gösterebilmek için (sunucu chapter_no'su yalnız çevrimiçi güncellenir).
  map[slug] = { url, ts: Date.now(), chapter_no: currentChapterNo, title: currentChapterTitle };
  try {
    localStorage.setItem(LS_LASTREAD, JSON.stringify(map));
  } catch {}
}
function getLastRead(slug) {
  return loadLastReadMap()[slug] || null;
}
// Resume hedefi: sunucu konumu (çok-cihaz paylaşımı) ile yerel son-okuma (çevrimdışı)
// arasından en TAZE olanı. Yerel ts sunucunun updated_at'inden yeniyse (çevrimdışı
// okuma) yerel kazanır; değilse sunucu (başka cihazda daha yeni okunmuş olabilir).
function resolveResume(book, slug) {
  let url = (book && book.current_url) || null;
  let ratio = (book && book.current_ratio) || 0;
  let chapterNo = (book && book.chapter_no) || null;
  const local = getLastRead(slug);
  const serverTsMs = ((book && book.updated_at) || 0) * 1000;
  if (local && local.url && local.ts >= serverTsMs) {
    url = local.url;
    ratio = getScrollLocal(url);
    if (local.chapter_no != null) chapterNo = local.chapter_no; // eski kayıtta yoksa sunucu değeri kalır
  }
  return { url, ratio, chapterNo };
}
/* ---------- sonsuz okuma: aktif bölüm + konum ---------- */
function activeEntry() {
  return stream.find((c) => c.url === activeUrl) || null;
}
function entryFor(url) {
  return stream.find((c) => c.url === url) || null;
}
function readerBar() {
  return document.querySelector("#readerView .reader-bar");
}
function readerBarBottom() {
  const b = readerBar();
  return b ? b.getBoundingClientRect().bottom : 0;
}

// Konum = AKTİF bölüm içindeki oran (bölüm-yerel). reader-bar alt çizgisinin, aktif
// bölümün üstünden ne kadar aşağıda olduğu / bölüm yüksekliği. İlerleme çubuğu da bunu
// gösterir (her bölümde 0→1) — sonsuz akışta "bu bölümde ne kadar ilerledim".
function currentRatio() {
  const e = activeEntry();
  if (!e || !e.el) return 0;
  const r = e.el.getBoundingClientRect();
  if (r.height <= 0) return 0;
  return Math.min(1, Math.max(0, (readerBarBottom() - r.top) / r.height));
}

// Aktif bölümü yeniden hesapla: reader-bar çizgisini GEÇEN son bölüm. En-çok-görünür
// yerine "çizgiyi geçen son" seçilir → iki bölüm ekranı paylaşırken titremez (D-B9v2).
function updateActiveChapter() {
  if (views.reader.hidden || !stream.length) return;
  const line = readerBarBottom() + 1;
  let active = stream[0];
  for (const e of stream) {
    if (e.el && e.el.getBoundingClientRect().top <= line) active = e;
    else break;
  }
  if (active && active.url !== activeUrl) setActiveChapter(active);
}

// Aktif bölüm değişince: reader-bar başlığı, "eski" yardımcı global'ler, konum kaydı
// (replaceState — geçmişe YENİ kayıt eklemez) ve son-okuma/okuma-günlüğü güncellenir.
function setActiveChapter(e) {
  activeUrl = e.url;
  currentUrl = e.url;
  currentBookSlug = e.bookSlug || currentBookSlug;
  currentChapterNo = e.no;
  currentChapterTitle = e.title;
  el("readerBook").textContent = e.bookTitle || "";
  el("readerChapter").textContent = e.title || "Bölüm";
  const st = history.state;
  if (st && st.view === "reader") {
    history.replaceState({ view: "reader", url: e.url, ratio: currentRatio() }, "");
  }
  saveLastRead(currentBookSlug, e.url);
  logReadOnce(e);
}

// Okuma günlüğü: bölüm gerçekten aktif olunca, oturum başına bir kez (karar #8 —
// SW cache-first GET sunucuya ulaşmaz; istemci olayı şart; prefetch bu yola girmez).
function logReadOnce(e) {
  if (!e || !e.loaded || !e.bookSlug || loggedReads.has(e.url)) return;
  loggedReads.add(e.url);
  fetch("/api/reading-log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day: localDay(), slug: e.bookSlug, url: e.url }),
  }).catch(() => {});
}

function persistScroll() {
  // Yalnızca başarıyla render edilmiş aktif bölümün konumunu kaydet — aksi halde
  // yarım/hatalı bir bölüm "kaldığın yer" olarak yazılır, sonraki açılış onu yeniden
  // çekmeye çalışır (gereksiz "Yükleniyor").
  if (views.reader.hidden) return;
  const e = activeEntry();
  if (!e || !e.loaded) return;
  const ratio = currentRatio();
  saveScrollLocal(e.url, ratio);
  saveLastRead(currentBookSlug, e.url);
  const st = history.state;
  if (st && st.view === "reader") history.replaceState({ view: "reader", url: e.url, ratio }, "");
  if (currentBookSlug) {
    fetch(`/api/book/${encodeURIComponent(currentBookSlug)}/position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: e.url, ratio }),
    }).catch(() => {});
  }
}
function updateProgress() {
  const bar = el("readProgress");
  if (!bar) return;
  const ratio = currentRatio();
  bar.firstElementChild.style.transform = `scaleX(${ratio})`;
  bar.setAttribute("aria-valuenow", Math.round(ratio * 100));
}
/* OKUYUCU HUD'u (Stitch "Floating HUD: auto-hides on reader scroll").
   Sonsuz okuma akışında ekranın üstü de metindir; sabit duran çubuk hem alan
   yer hem uzun okumada dikkat çeker. Aşağı kaydırırken çekilir, yukarı
   kaydırırken geri gelir.

   Kendi `scroll` dinleyicisini AÇMAZ: okuyucunun zaten tek bir kaydırma girişi
   var (`onReaderScroll`) ve ikinci bir dinleyici aynı olayda iki ayrı yerde iş
   yapardı — bu projede aynı kuralın iki yere yazılması defalarca ayrışmayla
   sonuçlandı. */
let hudSonY = 0;

function hudGuncelle() {
  const bar = readerBar();
  if (!bar) return;
  // Ayar sheet'i ya da arama çubuğu açıkken HUD kaçmaz: kullanıcı o an onlarla
  // uğraşıyor ve dayanak aldığı çubuğun kayması yön kaybettirir.
  if (!el("settingsPanel").hidden || !el("findBar").hidden) {
    bar.classList.remove("hud-gizli");
    return;
  }
  const y = Math.max(0, window.scrollY);
  const fark = y - hudSonY;
  // Titreşim eşiği: parmak titremesi ve lastik-bant sıçraması HUD'u açıp
  // kapatmasın (eşiksiz sürümde çubuk okurken titriyordu).
  if (Math.abs(fark) < 10) return;
  // Sayfanın TEPESİNDE daima görünür: kullanıcı oraya geri dönmek için gelir,
  // orada gizli bir çubuk aramaz.
  if (y < 80) bar.classList.remove("hud-gizli");
  else bar.classList.toggle("hud-gizli", fark > 0);
  hudSonY = y;
}

function hudGoster() {
  const bar = readerBar();
  if (bar) bar.classList.remove("hud-gizli");
  hudSonY = Math.max(0, window.scrollY);
}

function onReaderScroll() {
  updateActiveChapter();
  updateProgress();
  hudGuncelle();
  if (isRestoring) return;
  if (scrollSaveTimer) return;
  scrollSaveTimer = setTimeout(() => {
    scrollSaveTimer = null;
    persistScroll();
  }, 250);
}

// Belirli bir bölümün, bölüm-içi orana denk gelen mutlak konumuna kaydır.
function scrollToChapterRatio(e, ratio) {
  isRestoring = true;
  requestAnimationFrame(() => {
    const rect = e.el.getBoundingClientRect();
    const absTop = rect.top + window.scrollY;
    const barH = readerBar() ? readerBar().getBoundingClientRect().height : 0;
    const target = absTop + (ratio > 0 ? ratio * rect.height : 0) - barH;
    window.scrollTo(0, Math.max(0, Math.round(target)));
    updateActiveChapter();
    updateProgress();
    requestAnimationFrame(() => {
      isRestoring = false;
    });
  });
}

/* ---------- ayarları uygula ---------- */
function applySettings() {
  const root = document.documentElement;
  root.dataset.theme = settings.theme;
  root.style.setProperty("--reading", settings.fontPx + "px");
  root.style.setProperty(
    "--reading-font",
    settings.font === "sans"
      ? 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
      : 'Georgia, "Times New Roman", serif'
  );
  root.style.setProperty(
    "--reading-line-height",
    LINE_HEIGHTS[settings.lineHeight] || LINE_HEIGHTS.normal
  );
  root.style.setProperty("--reading-margin", MARGINS[settings.margin] || MARGINS.normal);
}
function markSegment(group, value, attr) {
  for (const b of document.querySelectorAll(`[${attr}]`)) {
    b.setAttribute("aria-pressed", b.getAttribute(attr) === value ? "true" : "false");
  }
}
function updateSettingsUI() {
  el("fontValue").textContent = settings.fontPx;
  el("fontFamily").textContent = settings.font === "sans" ? "Sans" : "Serif";
  el("libThemeToggle").innerHTML = THEME_ICON[settings.theme] || ICONS.moon;
  markSegment("theme", settings.theme, "data-theme-opt");
  markSegment("lh", settings.lineHeight, "data-lh");
  markSegment("mg", settings.margin, "data-mg");
  markSegment("inf", settings.infinite ? "1" : "0", "data-inf");
}
function setTheme(name) {
  if (!THEMES.includes(name)) return;
  settings.theme = name;
  saveSettings();
  applySettings();
  updateSettingsUI();
}
function cycleTheme() {
  const i = THEMES.indexOf(settings.theme);
  setTheme(THEMES[(i + 1) % THEMES.length]);
}

/* ---------- görünüm ---------- */
function showView(name) {
  for (const [key, node] of Object.entries(views)) node.hidden = key !== name;
  // Alt gezinme OKURKEN gizlenir: sonsuz okuma akışında ekranın altı metindir ve
  // sabit bir çubuk hem alanı yer hem parmağın altında kalır. `body.reading`
  // gövdenin alt boşluğunu da kaldırır (çubuk yokken boşluk anlamsız).
  const nav = el("bottomNav");
  if (nav) {
    nav.hidden = name === "reader";
    document.body.classList.toggle("reading", name === "reader");
  }
  // Okuyucuya her girişte HUD AÇIK başlar: bir önceki bölümden gizli devralınsa
  // kullanıcı başlıksız bir ekrana düşer ve nerede olduğunu göremez.
  if (name === "reader") hudGoster();
  // Okuyucudan çıkarken açık kalmış ayar sheet'i kapansın: body seviyesine
  // taşındığı için artık görünüm değişince kendiliğinden gizlenmiyor.
  if (name !== "reader") el("settingsPanel").hidden = true;
  senkronlaSekme(name);
}

/* ---------- alt gezinme ----------
   ÜÇ sekme: Stitch'in dördüncüsü ("Güncellemeler") bu projede bir ekrana
   karşılık gelmiyor — check-updates yalnız arka plan iş tipi. Boş bir sekme
   koymak, tasarımdan çıkarılan puan/yazar/özet alanlarıyla aynı türden bir boş
   vaat olurdu. */
function senkronlaSekme(name) {
  const acik = !el("settingsPanel").hidden;
  for (const t of document.querySelectorAll(".navtab")) {
    const etkin = acik ? t.dataset.tab === "settings"
                       : t.dataset.tab === "library" && name === "library";
    if (etkin) t.setAttribute("aria-current", "page");
    else t.removeAttribute("aria-current");
  }
}

/* ---------- tarayıcı/telefon geri tuşu = uygulama-içi geri ----------
   Her görünüm geçişi history'ye bir kayıt olarak işlenir (navigate). Geri tuşunda
   (popstate) o kayda karşılık gelen görünüm yeniden çizilir — böylece geri tuşu
   uygulamayı kapatmak yerine bir önceki ekrana döner. Kök (kütüphane) görünümünde
   geri tuşu uygulamadan çıkar (beklenen davranış). */
function applyNavState(state) {
  // Okuyucudan başka görünüme geçerken son konumu ANINDA yaz (uygulama-içi geri'de
  // pagehide/visibilitychange tetiklenmez; throttle'lı son POST kaçarsa kütüphane/
  // liste bir bölüm geride kalırdı).
  if (!views.reader.hidden && state && state.view !== "reader") persistScroll();
  switch (state && state.view) {
    case "book":
      openBook(state.slug);
      break;
    case "glossary":
      openGlossary(state.slug);
      break;
    case "reader":
      // Köken varken KAYITLI KONUM geri yüklenmez: kullanıcı "kaldığın yere"
      // değil, terimin geçtiği cümleye gitmek istedi.
      loadChapter(state.url, {
        restoreRatio: state.ratio,
        koken: state.koken,
      }).then(() => {
        if (!state.koken) return;
        // Konum geri yükleme `requestAnimationFrame` içinde koşuyor; odaklama
        // doğrudan çağrılırsa o kare kaydırmayı EZİYOR. İki kare beklemek,
        // restore bitmiş olsun diye.
        requestAnimationFrame(() =>
          requestAnimationFrame(() => kokeneOdaklan(state.koken, state.url))
        );
      });
      break;
    default:
      renderLibrary();
      showView("library");
  }
}

// Navigasyon. replace=false (varsayılan): seviye geçişi → geçmişe YENİ kayıt (push).
// replace=true: aynı seviyede kalır (bölüm↔bölüm) → üstteki kaydı DEĞİŞTİR, geçmişi
// büyütme. Böylece okuyucu tek history kaydı tutar ve "geri" hep bir üst seviyeye
// (kitap/kütüphane) gider — bölüm bölüm geriye taramaz. Tüm "geri" aksiyonları
// history.back() kullanır (aşağıda), pushState DEĞİL → jest görsel hiyerarşiyle uyumlu.
function navigate(state, replace = false) {
  if (replace) history.replaceState(state, "");
  else history.pushState(state, "");
  applyNavState(state);
}

window.addEventListener("popstate", (e) => {
  applyNavState(e.state || { view: "library" });
});

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// WCAG göreli parlaklık (0..1) — HSL bileşenlerinden (s ve l 0..1).
function hslLuma(hue, s, l) {
  const a = s * Math.min(l, 1 - l);
  const chan = (n) => {
    const k = (n + hue / 30) % 12;
    const c = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * chan(0) + 0.7152 * chan(8) + 0.0722 * chan(4);
}

function spineColor(slug) {
  let h = 0;
  for (const ch of slug) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const hue = h % 360;
  const sat = 48 + (Math.floor(h / 360) % 22);
  let light = 38 + (Math.floor(h / 7920) % 12);
  // QA bulgusu: parlak zeminlerde siyah yazıya geçmek rafı karma (bazısı beyaz
  // bazısı siyah) gösteriyordu. Onun yerine zemin, BEYAZ yazı AA kontrastına
  // (>=4.5:1, luma<=0.179) ulaşana dek koyulaştırılır — yazı HER sırtta beyaz.
  while (light > 24 && hslLuma(hue, sat / 100, light / 100) > 0.179) light -= 3;
  return `hsl(${hue} ${sat}% ${light}%)`;
}

/* ---------- kütüphane ---------- */
// Kitabın türü — slug öneki / şemasından türetilir (backend'e sütun gerekmez).
// manga:// & manga- → manga; pdf/epub → kitap; gerisi (web novel + paste) → novel.
function bookKind(book) {
  const s = book.slug || "";
  const u = book.current_url || "";
  if (s.startsWith("manga-") || u.startsWith("manga://")) return "manga";
  if (s.startsWith("pdf-") || s.startsWith("epub-") || u.startsWith("pdf://") || u.startsWith("epub://"))
    return "kitap";
  return "novel";
}
// Raf sırası + başlıkları (tür-bazlı raflar). Boş tür rafı çizilmez.
const KIND_SHELVES = [
  { kind: "novel", label: "Noveller" },
  { kind: "manga", label: "Mangalar" },
  { kind: "kitap", label: "Kitaplar" },
];

// Raf durum filtresi (D-B2v2: yaşam durumu sırtta görünmez, yalnız filtre).
const LS_FILTER = "novellink:shelfFilter";
let shelfFilter = localStorage.getItem(LS_FILTER) || "all";

function setShelfFilter(value) {
  shelfFilter = value;
  try {
    localStorage.setItem(LS_FILTER, value);
  } catch {}
  document.querySelectorAll("#shelfFilters .chip").forEach((c) => {
    c.setAttribute("aria-pressed", String(c.dataset.filter === value));
  });
  renderLibrary();
}

// Kitabın "tazeliği" (ms): sunucu updated_at'i (çok-cihaz paylaşımı) ile yerel
// son-okuma ts'inin büyüğü. Yerel ts, çevrimdışı okumada veya konum POST'u sessizce
// düştüğünde (persistScroll .catch) sunucudan taze olabilir. Hem devam fişi hem raf
// sırası bunu kullanır → ikisi tutarlı: en son okunan hem fişte hem rafın başında.
function bookFreshness(book) {
  const local = getLastRead(book.slug);
  return Math.max((book.updated_at || 0) * 1000, (local && local.ts) || 0);
}

// Devam fişi hedefi: en TAZE okunan kitap (kitaplar arasında en yenisi kazanır).
function pickResumeBook(books) {
  let best = null;
  let bestTs = -1;
  for (const book of books) {
    const target = resolveResume(book, book.slug);
    if (!target.url) continue;
    const ts = bookFreshness(book);
    if (ts > bestTs) {
      bestTs = ts;
      best = { book, target };
    }
  }
  return best;
}

// D-B11v2: fiş = raftan çekilmiş ayraç. spineColor zemini, sırt tipografisi,
// bölüm no + başlık + ince ilerleme çizgisi. Gölge/gradyan/ikon yok.
function renderResumeFiche(books) {
  const fiche = el("resumeFiche");
  const pick = pickResumeBook(books);
  if (!pick) {
    fiche.hidden = true;
    return;
  }
  const { book, target } = pick;
  const local = getLastRead(book.slug);
  const chTitle =
    (local && local.ts >= (book.updated_at || 0) * 1000 && local.title) ||
    book.current_title || "";
  const pct = Math.round(Math.min(1, Math.max(0, target.ratio || 0)) * 100);
  fiche.style.setProperty("--spine", spineColor(book.slug));
  fiche.innerHTML =
    '<span class="fiche-label">DEVAM ET</span>' +
    `<span class="fiche-title" lang="en">${escapeHtml(book.title)}</span>` +
    `<span class="fiche-chapter">${
      target.chapterNo ? "BÖL. " + target.chapterNo : "SON BÖLÜM"
    }${chTitle ? ' <span class="fiche-chname" lang="en">· ' + escapeHtml(chTitle) + "</span>" : ""}</span>` +
    `<span class="fiche-progress" aria-hidden="true"><span style="width:${pct}%"></span></span>`;
  fiche.onclick = () => {
    currentBookSlug = book.slug; // ilk bölüm hata verirse "metni yapıştır" doğru kitaba yazsın
    navigate({ view: "reader", url: target.url, ratio: target.ratio });
  };
  fiche.hidden = false;
}

// Raf altı sessiz istatistik satırı (D-B3: gün-1 "Bugün 0" gizlenir;
// çevrimdışı/hata → satır tamamen gizli, okuma akışına etkisi yok).
async function renderLibStats() {
  const line = el("libStats");
  try {
    const res = await fetch(`/api/stats?day=${localDay()}`);
    if (!res.ok) throw new Error();
    const s = await res.json();
    if (!s.total) {
      line.hidden = true;
      return;
    }
    line.textContent = s.today
      ? `BUGÜN ${s.today} BÖLÜM · TOPLAM ${s.total}`
      : `TOPLAM ${s.total} BÖLÜM`;
    line.hidden = false;
  } catch {
    line.hidden = true;
  }
}

// Tek kitap sırtı (spine) düğmesi üret.
function makeSpine(book, jobChecks) {
  const spine = document.createElement("button");
  spine.className = "spine";
  spine.dataset.slug = book.slug; // rozet anketi sırtı yerinde bulabilsin
  spine.style.setProperty("--spine", spineColor(book.slug));
  // Etiket, resume ile AYNI merge'i kullanır → çevrimdışı okunan son bölüm de görünür
  // (sunucu chapter_no'su yalnız çevrimiçi güncellenir).
  const chNo = resolveResume(book, book.slug).chapterNo;
  const tag = chNo ? "BÖL. " + chNo : "OKU";
  // KAPAK yalnız kütüphanede kullanılır (kullanıcı kararı 2026-09-10). Kitapların
  // ancak bir kısmında kapak var (kaynak sitesi kapanmış ya da og:image vermeyen
  // kitaplar) — bu yüzden kart BOYUTU her iki durumda da AYNI kalır ve kapaksız
  // kitap renkli zemin + monogramla durur. Boyutu kapağa göre değiştirmek rafı
  // dişli gösterirdi.
  const kapak = (book.cover || "").trim();
  const monogram = book.title.trim().split(/\s+/).slice(0, 2)
    .map((w) => w[0] || "").join("").toUpperCase();
  if (kapak) spine.classList.add("has-cover");
  spine.innerHTML =
    '<span class="spine-art">' +
      (kapak
        // referrerpolicy: bazı kaynak siteler dış referrer'lı isteği reddediyor.
        ? `<img class="spine-cover" alt="" loading="lazy" decoding="async"
             referrerpolicy="no-referrer" src="${escapeHtml(kapak)}">`
        : `<span class="spine-mono" aria-hidden="true">${escapeHtml(monogram)}</span>`) +
      '<span class="spine-job" hidden></span>' +
    '</span>' +
    `<span class="spine-title" lang="en">${escapeHtml(book.title)}</span>` +
    `<span class="spine-tag">${tag}</span>`;
  const img = spine.querySelector(".spine-cover");
  if (img) {
    // Kapak adresi kayıtlı ama görsel gelmiyorsa (site kaldırmış, hotlink
    // engeli) KIRIK RESİM ikonu kalmasın: karta monogram görünümüne dön.
    img.addEventListener("error", () => {
      spine.classList.remove("has-cover");
      img.replaceWith(Object.assign(document.createElement("span"), {
        className: "spine-mono", textContent: monogram,
      }));
    });
  }
  spine.addEventListener("click", () => navigate({ view: "book", slug: book.slug }));
  jobChecks.push(fetchBookJob(book.slug).then((job) => applyJobBadge(spine, job)));
  return spine;
}

// "+ KİTAP EKLE" sırtı (rafın sonundaki boş yuva metaforu).
function makeAddSpine() {
  const add = document.createElement("button");
  add.className = "spine spine-add";
  add.innerHTML =
    '<span class="spine-plus" aria-hidden="true">+</span><span class="spine-addlabel">KİTAP EKLE</span>';
  add.addEventListener("click", openAddModal);
  return add;
}

// Bir tür rafı: başlık (varsa) + sırtlar + raf tahtası. withAdd → ekle sırtı sona.
function buildShelfSection(label, books, withAdd, jobChecks) {
  const section = document.createElement("section");
  section.className = "shelf-section";
  if (label) {
    const head = document.createElement("div");
    head.className = "shelf-heading";
    head.innerHTML =
      `<span class="shelf-heading-name">${escapeHtml(label)}</span>` +
      `<span class="shelf-count">${books.length}</span>`;
    section.appendChild(head);
  }
  const wrap = document.createElement("div");
  wrap.className = "shelf-wrap";
  const shelf = document.createElement("div");
  shelf.className = "shelf";
  for (const book of books) shelf.appendChild(makeSpine(book, jobChecks));
  if (withAdd) shelf.appendChild(makeAddSpine());
  const board = document.createElement("div");
  board.className = "shelf-board";
  wrap.append(shelf, board);
  section.appendChild(wrap);
  return section;
}

async function renderLibrary() {
  clearTimeout(libraryJobPollTimer);
  const books = await fetchBooks();
  const shelves = el("shelves");
  el("libLoading").hidden = true;

  // D-PWA-Durum: sunucuya ulaşılamadı ≠ boş kütüphane. Raf daha önce çizildiyse
  // eldekini koru (anket yenilemesi rafı silmesin); hiç çizilmediyse hata yüzeyi.
  if (books === null) {
    if (!shelves.querySelector(".spine")) {
      el("libError").hidden = false;
      el("emptyState").hidden = true;
      el("filterEmpty").hidden = true;
      el("shelfFilters").hidden = true;
      el("resumeFiche").hidden = true;
    }
    return;
  }
  el("libError").hidden = true;

  shelves.replaceChildren();
  el("emptyState").hidden = books.length > 0;
  el("shelfFilters").hidden = books.length === 0;
  renderResumeFiche(books);
  renderLibStats();
  // Beklemeden: toplu ceviriyle SUNUCUDA hazirlanmis bolumler, "cevrimdisi indir"
  // dugmesine basilmadan telefona insin. Uygulamayi acmak yeter.
  otoIndirmeTur();

  const visible = books.filter(
    (b) => shelfFilter === "all" || (b.status || "okunuyor") === shelfFilter
  );
  // Raf sırası = en son okunan en başta. Sunucu updated_at DESC döner ama yerel
  // son-okuma (çevrimdışı / düşmüş POST) sunucuya yansımamış olabilir; fişle aynı
  // tazelik ölçüsüyle istemcide yeniden sıralarız → devam ettiğin kitap rafın başında.
  visible.sort((a, b) => bookFreshness(b) - bookFreshness(a));
  el("filterEmpty").hidden = !(books.length > 0 && visible.length === 0);

  // Türe göre grupla; boş türün rafı çizilmez. Tek tür varsa başlık gizli (tek raf).
  const groups = { novel: [], manga: [], kitap: [] };
  for (const b of visible) groups[bookKind(b)].push(b);
  const active = KIND_SHELVES.filter((k) => groups[k.kind].length);
  const jobChecks = [];
  if (!active.length) {
    // Kütüphane boş / filtre boş → yalnız ekle sırtı taşıyan tek raf (başlıksız).
    shelves.appendChild(buildShelfSection(null, [], visible.length === 0, jobChecks));
  } else {
    active.forEach((k, i) => {
      const withAdd = i === active.length - 1; // ekle sırtı son rafta
      const label = active.length > 1 ? k.label : null; // tek raf → başlık yok
      shelves.appendChild(buildShelfSection(label, groups[k.kind], withAdd, jobChecks));
    });
  }

  const busy = (await Promise.all(jobChecks)).some(Boolean);
  if (busy && !views.library.hidden) {
    libraryJobPollTimer = setTimeout(refreshShelfBadges, 2500);
  }
}

// Rozeti sırta uygula; iş sürüyorsa true döner (anketin devam sinyali).
// Yalnız süren işin ilerlemesi ve dikkat isteyen hata görünür. Biten iş rozet
// bırakmaz (bölümler zaten hazır); DURDURULAN da bırakmaz — kullanıcının kendi
// kararıdır, dikkat istemez (QA bulgusu: DURDURULDU rafta asılı kalıyordu).
function applyJobBadge(spine, job) {
  const badge = spine.querySelector(".spine-job");
  if (!job || !isRecentJob(job) || (job.state !== "running" && job.state !== "error")) {
    badge.hidden = true;
    spine.classList.remove("has-job");
    return false;
  }
  badge.hidden = false;
  spine.classList.add("has-job"); // başlık rozet bölgesinin üstünde bitsin
  badge.textContent = jobBadgeText(job);
  badge.dataset.state = job.state;
  return job.state === "running";
}

// Rozet anketi rafı YENİDEN KURMAZ: renderLibrary her 2.5 sn'de raf DOM'unu
// baştan çizince rozetler asenkron geldiği anda bir kaybolup bir beliriyordu
// (QA bulgusu: çeviri sürerken raf titriyor). Sadece rozetler yerinde güncellenir.
async function refreshShelfBadges() {
  clearTimeout(libraryJobPollTimer);
  if (views.library.hidden) return;
  const spines = [...document.querySelectorAll("#shelves .spine[data-slug]")];
  const anyRunning = (
    await Promise.all(
      spines.map(async (s) => applyJobBadge(s, await fetchBookJob(s.dataset.slug)))
    )
  ).some(Boolean);
  if (anyRunning && !views.library.hidden) {
    libraryJobPollTimer = setTimeout(refreshShelfBadges, 2500);
  }
}

async function fetchBookJob(slug) {
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/job`);
    if (!res.ok) return null;
    return (await res.json()).job || null;
  } catch {
    return null;
  }
}

function isRecentJob(job) {
  return job.state === "running" || Date.now() / 1000 - (job.updated_at || 0) < 86400;
}

function jobBadgeText(job) {
  if (job.state === "running") return `${job.done}/${job.total} · DEVAM ET`;
  return "! HATA"; // applyJobBadge yalnız running/error gösterir
}

/* ---------- kitap (bölüm listesi) ---------- */
async function openBook(slug) {
  currentBookSlug = slug;
  const books = await fetchBooks();
  currentBook = (books || []).find((b) => b.slug === slug) || null;
  el("bookTitle").textContent = currentBook ? currentBook.title : slug;
  markSegment("status", (currentBook && currentBook.status) || "okunuyor", "data-status-opt");

  const resume = el("resumeBtn");
  const target = resolveResume(currentBook, slug);
  if (target.url) {
    // Liste vurgusu ("current") ve resume aynı bölümü göstersin (çevrimdışı okunan da).
    if (currentBook) currentBook.current_url = target.url;
    resume.hidden = false;
    resume.onclick = () =>
      navigate({ view: "reader", url: target.url, ratio: target.ratio });
  } else {
    resume.hidden = true;
  }

  el("chapterSearch").value = "";
  const list = el("chapterList");
  list.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "loading-row";
  loading.textContent = "Yükleniyor…";
  list.appendChild(loading);
  showView("book");
  window.scrollTo(0, 0);
  discoverBulkJob(slug);

  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/chapters`);
    const data = await res.json();
    currentChapters = data.chapters || [];
    applyChapterFilter();
    // Beklemeden: toplu çeviriyle hazırlanmış bölümler de "çevrimdışı indir"
    // düğmesine basılmadan telefona insin. Toplu iş bitince openBook zaten
    // yeniden çağrılıyor, yani yeni bölümler o turda yakalanır.
    otoCevrimdisiKaydet(slug, currentChapters);
  } catch {
    list.replaceChildren();
    const err = document.createElement("p");
    err.className = "loading-row";
    err.textContent = "Bölümler yüklenemedi.";
    list.appendChild(err);
  }
}

// Saf: başlık veya bölüm numarasına göre filtrele (test edilebilir).
function filterChapters(list, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return list;
  return list.filter(
    (c) =>
      (c.title || "").toLowerCase().includes(q) ||
      String(c.chapter_no || "").includes(q)
  );
}

function applyChapterFilter() {
  const q = el("chapterSearch").value;
  renderChapterList(filterChapters(currentChapters, q), currentBook, q);
}

function renderChapterList(chapters, book, query) {
  const list = el("chapterList");
  list.replaceChildren();
  if (chapters.length === 0) {
    const p = document.createElement("p");
    p.className = "loading-row";
    p.textContent = (query || "").trim()
      ? "Eşleşen bölüm yok."
      : "Henüz çevrilmiş bölüm yok. 'Kaldığın yerden devam et' ile başla.";
    list.appendChild(p);
    return;
  }
  // Ekranda TERS sıra: en son çevrilen bölüm en üstte, 1. bölüm en altta. Tersleme
  // YALNIZ çizim anında yapılır — `currentChapters` mantıksal kaynak olarak ARTAN
  // kalmak zorunda, çünkü akış devamı ondan türetiliyor (`chapterListPrev` idx-1 =
  // önceki, `pickNextTarget` idx+1 = sonraki). Listeyi ters SAKLAMAK sonsuz okumayı
  // sessizce geriye çevirirdi. `slice()` de load-bearing: `filterChapters` boş
  // sorguda dizinin KENDİSİNİ döndürür ve `reverse()` yerinde çalışır — kopyasız
  // tersleme `currentChapters`ı kalıcı olarak bozardı.
  for (const ch of chapters.slice().reverse()) {
    const item = document.createElement("div");
    item.className = "chapter-item";
    const row = document.createElement("button");
    row.className = "chapter-row";
    if (book && ch.url === book.current_url) row.classList.add("current");
    const no = document.createElement("span");
    no.className = "chapter-no";
    no.textContent = ch.chapter_no ? "BÖLÜM " + ch.chapter_no : "BÖLÜM";
    const name = document.createElement("span");
    name.className = "chapter-name";
    name.lang = "en";
    name.textContent = ch.title || "";
    row.append(no, name);
    row.addEventListener("click", () => navigate({ view: "reader", url: ch.url }));
    const del = document.createElement("button");
    del.className = "chapter-del";
    del.setAttribute("aria-label", "Bölümü sil");
    del.textContent = "✕";
    del.addEventListener("click", () => deleteChapter(ch));
    item.append(row, del);
    list.appendChild(item);
  }
}

/* ---------- bölüm silme ---------- */
// SW, /api/chapter yanıtlarını kalıcı önbelleğe alır (çevrimdışı okuma). Sunucudan
// silinen bölümün SW kopyası da kalksın ki listede/okuyucuda hayalet kalmasın.
async function purgeChapterFromSwCache(url) {
  if (!("caches" in window)) return;
  try {
    for (const key of await caches.keys()) {
      const c = await caches.open(key);
      for (const req of await c.keys()) {
        const u = new URL(req.url);
        if (u.pathname === "/api/chapter" && u.searchParams.get("url") === url) {
          await c.delete(req);
        }
      }
    }
  } catch {} // best-effort temizlik: SW önbelleği yoksa/erişilemezse sessiz geç
}

/* ---------- otomatik çevrimdışı kayıt ---------- */
/* SW yalnız GET /api/chapter yanıtlarını DATA_CACHE'e yazar (sw.js: "POST/DELETE →
   asla önbelleğe alma"). Bu doğru bir kural — POST yanıtında saklanacak içerik yok —
   ama iki yolu telefona hiç ulaştırmıyordu: prefetch (POST /api/prefetch) ve toplu
   çeviri bölümü SUNUCUDA hazırlıyor, telefona tek bayt inmiyordu. Kullanıcı bu yüzden
   "çevrimdışı indir" düğmesine basmak zorunda kalıyordu; o düğmenin yaptığı iş de
   zaten eksikleri tek tek GET'lemekten ibaret.

   Isıtma GET'i boşluğu kapatır. İki kural load-bearing:
     * `track=0` — bölüm OKUNMADI; kitabın "kaldığın yer" işareti ilerlemesin, yoksa
       ısıtma okunmamış bölüme konum yazıp aktif bölümün position POST'uyla yarışır.
     * anahtar birliği — SW `track`i cache anahtarından siliyor (sw.js), yani ısıtma
       GET'i okuma GET'iyle AYNI girdiye yazar. Silinmeseydi her bölüm önbellekte iki
       kopya tutar ve çevrimdışı okuma yanlış kopyaya düşebilirdi. */

// Önbellekte hâlihazırda duran bölüm url'leri. TÜM cache'ler gezilir (tek bir ada
// bağlanmak yerine): DATA_CACHE adı sw.js'de tanımlı ve burada kopyalamak, ad
// değişince sessizce boş küme döndüren bir hataya dönerdi. `purgeChapterFromSwCache`
// da aynı deseni kullanıyor.
async function cachedChapterUrls() {
  if (!("caches" in window)) return null;
  try {
    const out = new Set();
    for (const key of await caches.keys()) {
      const c = await caches.open(key);
      for (const req of await c.keys()) {
        const u = new URL(req.url);
        if (u.pathname !== "/api/chapter") continue;
        const v = u.searchParams.get("url");
        if (v) out.add(v);
      }
    }
    return out;
  } catch {
    return null; // caches yoksa/erişilemezse: otomatik kayıt sessizce devre dışı
  }
}

// Tek bölümü önbelleğe çek. Yanıt gövdesi okunmaz — tek amaç SW'nin girdiyi
// yazması. Çevrimdışıysa/sunucu kapalıysa sessiz geç: ısıtma en iyi çabadır.
async function warmOffline(url) {
  try {
    await fetch(`/api/chapter?url=${encodeURIComponent(url)}&track=0`);
  } catch {}
}

// Kitabın ÇEVRİLMİŞ ama telefonda olmayan bölümlerini arka planda, sırayla indir.
// Sıralı: paralel istek sunucudaki tek çekim kapısını (fetch._FETCH_GATE) ve
// okuyucunun canlı isteğini bekletirdi. Liste `/api/book/{slug}/chapters`ten gelir
// ve YALNIZ çevrilmiş bölümleri içerir (cache.list_chapters), yani bu GET'ler
// önbellek isabetidir — hiçbiri yeni çeviri tetiklemez.
async function otoCevrimdisiKaydet(slug, liste) {
  const list = liste || chapterListFor(slug);
  if (!list || !list.length) return;
  const kayitli = await cachedChapterUrls();
  if (!kayitli) return;
  for (const ch of list) {
    if (currentBookSlug !== slug) return; // başka kitaba geçildi: peşine düşme
    if (!ch.url || ch.translated === false || kayitli.has(ch.url)) continue;
    await warmOffline(ch.url);
  }
}

/* ---------- otomatik çevrimdışı TARAMA (kütüphane düzeyinde) ---------- */
/* `otoCevrimdisiKaydet` yalnız `openBook`'tan çağrılıyordu, yani ancak O kitabın
   bölüm listesini AÇARSAN çalışıyordu. Toplu çeviri ise SUNUCUDA koşuyor ve telefona
   tek bayt inmiyor; iş bittiğinde `pollBulk`'ün geri çağrısı da yalnız hâlâ o kitabın
   sayfasındaysan `openBook` çağırıyor. Üç boşluk birden açık kalıyordu: iş sen başka
   yerdeyken biterse, uygulamayı kapatırsan, ya da ertesi gün kütüphaneden açarsan
   hiçbir şey inmiyordu — kullanıcı "çevrimdışı indir" düğmesine basmak zorundaydı
   (gerçek şikâyet, 2026-09-03).

   Tarama kütüphane çizildikçe koşar: uygulamayı açmak, ÇEVRİLMİŞ ama telefonda
   olmayan her bölümü sessizce indirmeye yeter. Zaten önbellekte olanlar atlandığı
   için tekrarlanan turlar ucuzdur — ilk tur dışında genelde hiç istek çıkmaz. */
let otoIndirmeCalisiyor = false;

function otoIndirmeDurum(metin) {
  const satir = el("autoOffline");
  if (!satir) return;
  satir.textContent = metin || "";
  satir.hidden = !metin;
}

async function otoIndirmeTur() {
  // TEK UÇUŞ: kütüphane her yenilendiğinde (anket, filtre, geri dönüş) yeniden
  // başlasaydı aynı bölümler üst üste indirilirdi.
  if (otoIndirmeCalisiyor) return;
  // Elle indirme açıksa karışma: ikisi aynı bölümleri çekip sunucuyu iki katına
  // çıkarır ve ilerleme sayısı yanlış görünürdü.
  if (!el("offlineProgress")?.hidden) return;
  if (navigator.onLine === false) return;

  // GÜVENLİ BAĞLAM ŞART ve bunu SÖYLEMEK de şart (2026-09-10).
  // Service Worker ile Cache API yalnız `https://` ya da `http://localhost`
  // üzerinde vardır. Telefon `http://100.x.x.x:8000` gibi DÜZ BİR IP ile
  // bağlandığında ikisi de yoktur; tarama eskiden burada `caches` bulamayıp
  // SESSİZCE çıkıyordu. Sonuç: kullanıcı toplu çeviriyi başlatıyor, bölümlerin
  // telefona indiğini sanıyor, çevrimdışı kalınca hiçbirini bulamıyor ve arızayı
  // toplu çeviriye yazıyordu — asıl sebep ADRESKEN. Sessiz devre dışı kalmak,
  // çalışmayan bir özelliği çalışıyor göstermenin en pahalı biçimiydi.
  if (!window.isSecureContext || !("caches" in window)) {
    otoIndirmeDurum(
      "Çevrimdışı kayıt bu adreste ÇALIŞMAZ: güvenli bağlantı (https) gerekiyor. " +
      "Telefonda düz IP yerine https://…ts.net adresini kullan."
    );
    return; // uyarı KALICI: 4 sn'lik temizleyici bilerek çalıştırılmıyor
  }

  otoIndirmeCalisiyor = true;
  try {
    const books = await fetchBooks();
    if (!books || !books.length) return;
    const kayitli = await cachedChapterUrls();
    if (!kayitli) return; // caches API yok: otomatik kayıt sessizce devre dışı

    // ÖNCE eksikleri say, sonra indir: "3/48" diyebilmek için toplamı bilmek
    // gerekiyor ve sayım, önbellek isabetleri olduğu için ucuz.
    const eksikler = [];
    for (const b of books) {
      for (const ch of await chaptersOf(b.slug)) {
        // `translated` LOAD-BEARING: cevirisi olmayan bolumu GET'lemek CEVIRI
        // TETIKLER ve ucretli model seciliyken PARA harcar. Otomatik bir tarama
        // bunu asla yapmamali — dugmenin adi da isin adi da "indir".
        if (ch.url && ch.translated !== false && !kayitli.has(ch.url)) {
          eksikler.push(ch.url);
        }
      }
    }
    if (!eksikler.length) return;

    let indi = 0;
    for (const url of eksikler) {
      // Çevrimdışına düşülürse ya da kullanıcı elle indirmeyi başlatırsa BIRAK.
      if (navigator.onLine === false || !el("offlineProgress")?.hidden) break;
      otoIndirmeDurum(`${indi + 1}/${eksikler.length} bölüm çevrimdışına alınıyor…`);
      await warmOffline(url);
      indi++;
    }
    otoIndirmeDurum(indi ? `${indi} bölüm çevrimdışına alındı.` : "");
    setTimeout(() => otoIndirmeDurum(""), 4000);
  } catch {
    otoIndirmeDurum(""); // en iyi çaba: sunucu kapalıysa sessiz geç
  } finally {
    otoIndirmeCalisiyor = false;
  }
}

async function deleteChapter(ch) {
  const label = ch.chapter_no ? `Bölüm ${ch.chapter_no}` : ch.title || "Bu bölüm";
  const ok = window.confirm(
    `${label} silinsin mi?\nÇevirisi önbellekten kalkar; tekrar açarsan yeniden çevrilir.`
  );
  if (!ok) return;
  try {
    const res = await fetch(`/api/chapter?url=${encodeURIComponent(ch.url)}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch {
    window.alert("Bölüm silinemedi. Bağlantını kontrol edip tekrar dene.");
    return;
  }
  await purgeChapterFromSwCache(ch.url);
  currentChapters = currentChapters.filter((c) => c.url !== ch.url);
  // Silinen bölüm "kaldığın yer" ise sunucu işareti temizledi; devam düğmesini gizle.
  if (currentBook && currentBook.current_url === ch.url) {
    currentBook.current_url = null;
    el("resumeBtn").hidden = true;
  }
  applyChapterFilter();
}

/* ---------- sözlük ---------- */
/* Çevrimdışı düzenleme: her ekleme/değiştirme/silme ÖNCE localStorage kuyruğuna
   yazılır, sonra sunucuya gönderilmeye çalışılır. Sunucu (PC) kapalıyken kayıt
   telefonda durur ve bağlantı dönünce kendiliğinden gider. Çevrimiçiyken de aynı
   yol işler — tek kod yolu, "ağ var mı" dallanması yok.
   Biçim: { [slug]: { [source]: string | null } }   null = silinecek. */
const LS_GLOSS_QUEUE = "novellink:glossQueue";

function loadGlossQueue() {
  try {
    return JSON.parse(localStorage.getItem(LS_GLOSS_QUEUE)) || {};
  } catch {
    return {};
  }
}
function saveGlossQueue(queue) {
  try {
    localStorage.setItem(LS_GLOSS_QUEUE, JSON.stringify(queue));
  } catch {}
}
function queueGlossChange(slug, source, target) {
  const queue = loadGlossQueue();
  if (!queue[slug]) queue[slug] = {};
  queue[slug][source] = target; // null = silme
  saveGlossQueue(queue);
}
function dropGlossChange(slug, source) {
  const queue = loadGlossQueue();
  if (!queue[slug]) return;
  delete queue[slug][source];
  if (Object.keys(queue[slug]).length === 0) delete queue[slug];
  saveGlossQueue(queue);
}
function pendingGloss(slug) {
  return loadGlossQueue()[slug] || {};
}
function pendingGlossCount() {
  return Object.values(loadGlossQueue()).reduce(
    (n, terms) => n + Object.keys(terms).length,
    0
  );
}
// Sunucudan (ya da service worker önbelleğinden) gelen listeye bekleyen değişiklikleri
// bindir → ekranda daima son hâl görünür, gönderilmiş gibi.
function overlayGloss(slug, terms) {
  const merged = { ...terms };
  for (const [source, target] of Object.entries(pendingGloss(slug))) {
    if (target === null) delete merged[source];
    else merged[source] = target;
  }
  return Object.fromEntries(
    Object.entries(merged).sort((a, b) =>
      a[0].localeCompare(b[0], "tr", { sensitivity: "base" })
    )
  );
}

/* Yazma istekleri service worker'dan GEÇMEZ (yalnız GET yakalanır) → oradaki zaman
   aşımı korumasından yararlanamazlar. Tailscale kapalıyken ts.net adresi hata
   vermek yerine dakikalarca askıda kalır (kara delik); kendi süremizi koyuyoruz. */
const GLOSS_WRITE_TIMEOUT = 8000;

async function fetchWithTimeout(url, options, timeoutMs = GLOSS_WRITE_TIMEOUT) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function postTermNow(slug, source, target) {
  const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(slug)}/glossary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, target }),
  });
  return res.status;
}
async function deleteTermNow(slug, source) {
  const res = await fetchWithTimeout(
    `/api/book/${encodeURIComponent(slug)}/glossary?source=${encodeURIComponent(source)}`,
    { method: "DELETE" }
  );
  return res.status;
}

let glossFlushing = false;
/* Kuyruğu sunucuya boşalt. Her başarılı istekten SONRA kuyruktan düşer: akış
   ortasında bağlantı giderse gönderilenler tekrar gönderilmez. Ağ hatası =
   sıradakiler beklesin (dur). 4xx = istek bozuk, tekrar denemek düzeltmez → düş.
   Döner: ekranın tazelenmesi gerekip gerekmediği. */
async function flushGlossQueue() {
  if (glossFlushing) return false;
  glossFlushing = true;
  let sent = false;
  try {
    // Kuyruk her turda TAZE okunur: gönderim sürerken eklenen kayıt da aynı turda
    // gider (yoksa bir sonraki tetiklemeye kadar beklerdi). Her tur ya kuyruğu
    // küçültür ya da çıkar → döngü kilitlenmez.
    for (;;) {
      const queue = loadGlossQueue();
      const slug = Object.keys(queue)[0];
      if (!slug) break;
      const source = Object.keys(queue[slug])[0];
      if (source === undefined) {
        delete queue[slug];
        saveGlossQueue(queue);
        continue;
      }
      const target = queue[slug][source];
      let status;
      try {
        status =
          target === null
            ? await deleteTermNow(slug, source)
            : await postTermNow(slug, source, target);
      } catch {
        break; // sunucuya ulaşılamadı → kalanı bir sonraki denemeye bırak
      }
      if (status >= 500) break; // sunucu ayakta ama hasta → bekletmeye devam
      dropGlossChange(slug, source);
      sent = true;
    }
  } finally {
    glossFlushing = false;
  }
  return sent;
}

/* ---------- sözlük süzme + yakın terim uyarısı ----------
   Sözlük 267 satıra çıkabiliyor; telefonda parmakla kaydırarak terim bulmak
   pratik değil. Süzme TAMAMEN istemci tarafında: sunucuya ek istek yok, çevrimdışı
   da çalışır (bekleyen kayıtlar `overlayGloss` ile listeye zaten karışıyor). */
let glossFilter = "all";
let glossQuery = "";
let glossRows = {};       // kaynak -> {origin, created_at, first_chapter}
let glossTermsSonHal = {}; // sunucudan gelen HAM eşleme (süzgeç yerelde yeniden çizer)
let glossWarnPairs = [];  // [[a, b], …] yazım hatası olabilecek çiftler

/* `glossary.fold_term`'ün hafif JS eşi: yazım varyantından bağımsız karşılaştırma
   anahtarı. "İngilizce kalanlar" süzgeci sunucudaki tanımla AYNI olmalı — iki yerde
   iki tanım, aynı kayıt için farklı karar demektir. */
function foldTerim(t) {
  return (t || "").trim().replace(/[\s\-_'’.·]+/g, "").toLocaleLowerCase("tr");
}

function glossIngilizceKorunan(source, target) {
  return foldTerim(source) === foldTerim(target);
}

function glossUyaranlar() {
  const kume = new Set();
  for (const cift of glossWarnPairs) for (const ad of cift) kume.add(ad);
  return kume;
}

function glossSatirGecer(source, target) {
  if (glossQuery) {
    const q = glossQuery.toLocaleLowerCase("tr");
    const alanlar = source + " " + (target || "");
    if (!alanlar.toLocaleLowerCase("tr").includes(q)) return false;
  }
  if (glossFilter === "en") return glossIngilizceKorunan(source, target);
  if (glossFilter === "tr") return !glossIngilizceKorunan(source, target);
  if (glossFilter === "manual") return (glossRows[source] || {}).origin === "manual";
  return true;
}

async function fetchGlossary(slug) {
  let terms = {};
  glossRows = {};
  glossWarnPairs = [];
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/glossary`);
    const data = await res.json();
    terms = data.terms || {};
    for (const satir of data.rows || []) glossRows[satir.source] = satir;
    glossWarnPairs = data.warnings || [];
  } catch {
    terms = {}; // çevrimdışı + hiç önbellek yok: yalnız bekleyen kayıtlar görünsün
  }
  // Süzgeç yeniden çizerken sunucuya GİTMEZ; ham liste burada saklanır.
  glossTermsSonHal = terms;
  return overlayGloss(slug, terms);
}
/* Kayıt ANINDA yereldir; gönderim arka planda. Sunucuyu beklemek, PC kapalıyken
   "Ekle" düğmesini saniyelerce dondururdu — kayıt zaten kuyrukta güvende. */
function saveTerm(slug, source, target) {
  queueGlossChange(slug, source, target);
  updateGlossPendingNote();
  flushGlossQueue().then(refreshGlossPendingUi);
}
function deleteTerm(slug, source) {
  queueGlossChange(slug, source, null);
  updateGlossPendingNote();
  flushGlossQueue().then(refreshGlossPendingUi);
}

// Gönderim bitince satır rozetlerini + bekleyen sayısını yerinde tazele (tam yeniden
// çizim yok: kullanıcı bir alanı düzenliyor olabilir).
function refreshGlossPendingUi() {
  updateGlossPendingNote();
  const pending = pendingGloss(currentBookSlug);
  for (const row of document.querySelectorAll("#glossList .gloss-row")) {
    const src = row.querySelector(".gloss-source");
    if (src) row.classList.toggle("gloss-row-pending", src.textContent in pending);
  }
}

async function openGlossary(slug) {
  currentBookSlug = slug;
  // Süzgeç kitapla birlikte sıfırlanır: başka kitaptan kalan bir süzgeç, bu kitabın
  // listesini sebepsiz boş gösterirdi.
  glossFilter = "all";
  glossQuery = "";
  if (el("glossSearch")) el("glossSearch").value = "";
  markSegment("glossFilter", "all", "data-gloss-filter");
  refreshGlossExportLink(slug);
  setGlossIoState("");
  // fetchBooks() sunucuya ulaşamazsa null döner — sözlük çevrimdışı da açılmalı,
  // başlık slug'a düşer.
  const books = (await fetchBooks()) || [];
  const book = books.find((b) => b.slug === slug) || null;
  el("glossaryTitle").textContent = "SÖZLÜK — " + (book ? book.title : slug);

  const list = el("glossList");
  list.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "loading-row";
  loading.textContent = "Yükleniyor…";
  list.appendChild(loading);
  showView("glossary");
  window.scrollTo(0, 0);

  // Liste ÖNCE çizilir (bekleyen kayıtlar overlay'den gelir), gönderim arka planda:
  // sunucu kapalıyken flush'ın zaman aşımını beklemek ekranı boş bırakırdı.
  renderGlossary(await fetchGlossary(slug));
  flushGlossQueue().then(async (sent) => {
    if (!sent) return;
    // Kuyruk boşaldı: listeyi sunucudan tazele, yoksa gönderim sırasında alınmış
    // eski yanıt yeni terimi eksik gösterebilir.
    if (currentBookSlug === slug && !views.glossary.hidden) {
      renderGlossary(await fetchGlossary(slug));
    } else {
      refreshGlossPendingUi();
    }
  });
}

// Bekleyen (henüz sunucuya gitmemiş) düzenlemeleri sözlük ekranının başında duyur.
function updateGlossPendingNote() {
  const note = el("glossPending");
  if (!note) return;
  const count = pendingGlossCount();
  note.hidden = count === 0;
  note.textContent =
    count === 0
      ? ""
      : `${count} değişiklik telefonda bekliyor — sunucuya bağlanınca kendiliğinden kaydedilecek.`;
}

// Yazım hatası olabilecek çiftleri listenin başında duyur. Otomatik birleştirme
// YOK: `ore` (maden damarı) / `orc` (ırk) örneği tek harf farkının gerçek bir anlam
// farkı olabileceğini gösteriyor — karar kullanıcınındır.
function updateGlossWarnNote() {
  const note = el("glossWarnNote");
  if (!note) return;
  note.hidden = glossWarnPairs.length === 0;
  if (note.hidden) return;
  const ornek = glossWarnPairs
    .slice(0, 3)
    .map((c) => c.join(" / "))
    .join(" · ");
  note.textContent =
    `${glossWarnPairs.length} terim çifti birbirine tek harf uzaklıkta — biri yazım ` +
    `hatası olabilir: ${ornek}${glossWarnPairs.length > 3 ? " …" : ""}`;
}

function updateGlossCount(gosterilen, toplam) {
  const note = el("glossCount");
  if (!note) return;
  const suzuluyor = gosterilen !== toplam;
  note.hidden = toplam === 0;
  note.textContent = suzuluyor
    ? `${toplam} terimden ${gosterilen} tanesi gösteriliyor`
    : `${toplam} terim`;
}

function renderGlossary(terms) {
  const list = el("glossList");
  list.replaceChildren();
  updateGlossPendingNote();
  updateGlossWarnNote();
  const pending = pendingGloss(currentBookSlug);
  const uyaranlar = glossUyaranlar();
  const tumu = Object.entries(terms);
  const entries = tumu.filter(([kaynak, karsilik]) => glossSatirGecer(kaynak, karsilik));
  updateGlossCount(entries.length, tumu.length);
  if (tumu.length === 0) {
    const p = document.createElement("p");
    p.className = "loading-row";
    p.textContent = "Henüz terim yok. Bölüm okudukça karakter isimleri buraya eklenir.";
    list.appendChild(p);
    return;
  }
  if (entries.length === 0) {
    const p = document.createElement("p");
    p.className = "loading-row";
    p.textContent = "Bu süzgeçle eşleşen terim yok.";
    list.appendChild(p);
    return;
  }
  for (const [source, target] of entries) {
    const row = document.createElement("div");
    row.className = "gloss-row";
    if (source in pending) row.classList.add("gloss-row-pending");

    const src = document.createElement("span");
    src.className = "gloss-source";
    src.textContent = source;
    if (uyaranlar.has(source)) {
      // Rozet satırın kendisinde: kullanıcı düzeltirken hangi kayda baktığını
      // görmeli, listenin başındaki özet kaydırınca ekrandan çıkıyor.
      const uyari = document.createElement("span");
      uyari.className = "gloss-warn-chip";
      uyari.textContent = "?";
      uyari.title = "Sözlükte buna tek harf uzaklıkta başka bir terim var";
      src.appendChild(uyari);
    }

    const arrow = document.createElement("span");
    arrow.className = "gloss-arrow";
    arrow.textContent = "→";

    const tgt = document.createElement("input");
    tgt.className = "gloss-target";
    tgt.type = "text";
    tgt.value = target;
    tgt.setAttribute("aria-label", source + " karşılığı");
    tgt.addEventListener("change", () => {
      saveTerm(currentBookSlug, source, tgt.value.trim() || source);
      row.classList.add("gloss-row-pending"); // gönderim bitince kendiliğinden kalkar
      gosterTerimEtkisi(row, source);
    });

    const del = document.createElement("button");
    del.className = "gloss-del";
    del.textContent = "×";
    del.setAttribute("aria-label", source + " sil");
    del.addEventListener("click", () => {
      row.remove();
      deleteTerm(currentBookSlug, source);
    });

    row.append(src, arrow, tgt, del);
    // KOŞUL varsa ikinci satırda görünür. Görünmesi şart: koşul, karşılığın
    // HANGİ BAĞLAMDA geçerli olduğunu belirleyen bir kural ve prompt'a çıkıyor —
    // ekranda saklanırsa terim beklenmedik çevrildiğinde sebebi hiçbir yerde
    // okunamaz. (Düzenleme uçtan yapılır; okuyucunun çevrimdışı kuyruğu yalnız
    // karşılığı taşıyor ve koşulu ASLA silmiyor.)
    const kosul = (glossRows[source] || {}).kosul;
    if (kosul) {
      const not = document.createElement("span");
      not.className = "gloss-kosul";
      not.textContent = "KOŞUL: " + kosul;
      row.appendChild(not);
    }
    // KÖKEN: kayıt hangi bölümden, hangi cümleden çıktı. Sözlük karşılığı
    // prompt'ta KURAL olarak uygulanıyor; garip bir çeviri görüldüğünde
    // "bu nereden geldi" sorusu ancak kaydın çıktığı cümleyle cevaplanabiliyor.
    const kok = glossRows[source] || {};
    if (kok.first_chapter || kok.kaynak_cumle) {
      const koken = document.createElement("div");
      koken.className = "gloss-koken";
      if (kok.first_chapter) {
        const git = document.createElement("button");
        git.className = "gloss-koken-git";
        git.type = "button";
        git.textContent = "BÖLÜM " + kok.first_chapter;
        git.title = "Terimin ilk geçtiği bölümü aç";
        git.addEventListener("click", () =>
          kokeneGit(kok.first_chapter, kok.kaynak_cumle, source,
                    (glossRows[source] || {}).target));
        koken.appendChild(git);
      }
      if (kok.kaynak_cumle) {
        const c = document.createElement("span");
        c.className = "gloss-koken-cumle";
        c.textContent = "“" + kok.kaynak_cumle + "”";
        koken.appendChild(c);
      }
      row.appendChild(koken);
    }
    list.appendChild(row);
  }
}

/* Sözlük kaydının çıktığı bölüme git. Ayrı bir URL sütunu TUTULMUYOR: bölüm
   numarası önbellekteki bölüm listesiyle eşleşiyor ve ikinci bir kaynak, iki
   kaydın zamanla ayrışması demekti (bu projede künye alanları tam böyle
   ayrışmıştı). Bölüm henüz indirilmemişse SESSİZ kalınmaz — kullanıcı düğmeye
   bastığında bir şey olmamasını arıza sanır. */
async function kokeneGit(no, cumle, source, target) {
  const slug = currentBookSlug;
  if (!slug || !no) return;
  let liste = chapterListFor(slug);
  if (!liste || !liste.length) {
    await ensureChapterList(slug);
    liste = chapterListFor(slug);
  }
  const hedef = (liste || []).find((c) => Number(c.chapter_no) === Number(no));
  if (!hedef || !hedef.url) {
    window.alert(
      `Bölüm ${no} bu kitabın indirilmiş bölümleri arasında yok.
` +
      "Terim o bölümde eklenmiş ama bölüm önbellekte değil."
    );
    return;
  }
  // Köken bilgisi state ile TAŞINIR: bölümün başına değil, terimin geçtiği
  // CÜMLEYE gidilecek ve orada vurgulanacak.
  navigate({ view: "reader", url: hedef.url, koken: { cumle, source, target } });
}

/* Sözlükten gelen KÖKEN odağı: cümleye kaydır, vurgula, İngilizce karşılığını aç.

   Cümle `KOKEN_CUMLE_MAX` ile kırpılmış olabilir, o yüzden tam eşleşme aranmaz —
   baştan bir parçası (`ARAMA_ONEK`) yeter. Türkçe tarafta KARŞILIK, İngilizce
   tarafta KAYNAK terim vurgulanır: iki dil arasında cümle-düzeyi hizalama yok
   (işaretçiler PARAGRAF hizalıyor), ama kullanıcı zaten bir TERİMİN kökenine
   bakıyor ve aradığı şey o terimin iki dildeki geçişi. */
const ARAMA_ONEK = 60;

/* Cümle içinde ARANAN TERİMİ ayrıca işaretle.

   Ölçülen gerçek vaka (shadow-slave bölüm 353): tek bölümde 16 terim var ve
   bazıları AYNI cümleden geliyor (nitelik/anı listeleri). Yalnız cümleyi
   vurgulamak o durumda hangi terime baktığını kaybettiriyordu. */
function _terimIsaretle(parca, terim) {
  if (!terim) return escapeHtml(parca);
  const j = parca.toLowerCase().indexOf(String(terim).toLowerCase());
  if (j < 0) return escapeHtml(parca);
  return (
    escapeHtml(parca.slice(0, j)) +
    '<b class="koken-terim">' + escapeHtml(parca.slice(j, j + terim.length)) +
    "</b>" + escapeHtml(parca.slice(j + terim.length))
  );
}

function _vurgula(host, aranan, terim) {
  const metin = host.textContent || "";
  const i = aranan ? metin.indexOf(aranan) : -1;
  if (i < 0) return false;
  host.innerHTML =
    escapeHtml(metin.slice(0, i)) +
    '<mark class="koken-vurgu">' +
    _terimIsaretle(metin.slice(i, i + aranan.length), terim) +
    "</mark>" + escapeHtml(metin.slice(i + aranan.length));
  return true;
}

// Terimi İÇEREN cümleyi bul (İngilizce tarafta kullanılır).
function _terimliCumle(metin, terim) {
  if (!terim) return null;
  const t = terim.toLowerCase();
  for (const c of (metin || "").split(/(?<=[.!?…])\s+/)) {
    if (c.toLowerCase().includes(t)) return c.trim();
  }
  return null;
}

function kokeneOdaklan(koken, url) {
  const { cumle, source, target } = koken || {};
  const onek = (cumle || "").slice(0, ARAMA_ONEK);
  const paragraflar = [...document.querySelectorAll("#readerBody p")];
  let hedef = null;
  let idx = -1;
  paragraflar.forEach((p, i) => {
    if (hedef) return;
    const t = p.textContent || "";
    if ((onek && t.includes(onek)) || (!onek && target && t.includes(target))) {
      hedef = p;
      idx = Number(p.dataset.idx != null ? p.dataset.idx : i);
    }
  });
  if (!hedef) return; // bölüm yeniden çevrilmiş olabilir: sessizce bölüm başında kal
  hedef.scrollIntoView({ block: "center" });
  _vurgula(hedef, onek || target, target);
  // İngilizce karşılığı AÇ (çift-tık ile aynı yol) ve orada kaynak terimin
  // geçtiği cümleyi vurgula.
  const sonra = hedef.nextElementSibling;
  if (!(sonra && sonra.classList.contains("source-line"))) toggleSource(hedef, idx, url);
  setTimeout(() => {
    const kaynak = hedef.nextElementSibling;
    if (kaynak && kaynak.classList.contains("source-line")) {
      _vurgula(kaynak, _terimliCumle(kaynak.textContent, source) || source, source);
    }
  }, 260);
}

/* ---------- kitap ekle ---------- */
/* Kitap Ekle: URL · METİN sekmeleri (D-B4/5/8v2). Paste taslağı localStorage'da
   yaşar — modal kapansa da kaybolmaz; başarılı gönderimde temizlenir. */
const LS_PASTE_DRAFT = "novellink:pasteDraft";
let addTab = "url";

function setAddTab(tab) {
  addTab = tab;
  markSegment("addtab", tab, "data-add-tab");
  el("addTabUrl").hidden = tab !== "url";
  el("addTabPaste").hidden = tab !== "paste";
  el("addTabDosya").hidden = tab !== "dosya";
  el("addConfirm").textContent = tab === "dosya" ? "Yükle ve Oku" : "Ekle ve Oku";
}

// EPUB/PDF dosyasını içe aktar: ham gövde + XHR (yükleme yüzdesi). Başarıda ilk bölüme
// gider (reader sayfayı/bölümü OKUDUKÇA çevirir: PDF sayfa görseli, EPUB yerinde HTML).
// İçe aktarım ÇEVİRMEZ, yalnız sahneler → kota tek dosyayla tükenmez.
function uploadFile() {
  const f = el("fileInput").files[0] || null;
  if (!f) return el("fileInput").focus();
  const isPdf = /\.pdf$/i.test(f.name);
  const isEpub = /\.epub$/i.test(f.name);
  const isManga = /\.(cbz|zip|jpe?g|png|webp)$/i.test(f.name);
  if (!isPdf && !isEpub && !isManga)
    return alert("Yalnız EPUB, PDF veya manga (CBZ/ZIP/görsel) dosyası seçilebilir.");
  if (f.size > 50 * 1024 * 1024) return alert("Dosya 50MB sınırını aşıyor.");
  const path = isPdf ? "/api/import/pdf" : isEpub ? "/api/import/epub" : "/api/import/manga";
  const endpoint = path + `?filename=${encodeURIComponent(f.name)}`;

  const prog = el("uploadProgress");
  const bar = prog.querySelector(".upload-bar span");
  const status = el("uploadStatus");
  const btn = el("addConfirm");
  prog.hidden = false;
  bar.style.width = "0%";
  status.textContent = "Yükleniyor…";
  btn.disabled = true;

  const xhr = new XMLHttpRequest();
  xhr.open("POST", endpoint);
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) bar.style.width = Math.round((e.loaded / e.total) * 100) + "%";
  };
  xhr.upload.onload = () => {
    bar.style.width = "100%";
    status.textContent = "İşleniyor… (bölümler ayıklanıyor)";
  };
  xhr.onload = () => {
    btn.disabled = false;
    if (xhr.status >= 200 && xhr.status < 300) {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        status.textContent = "Geçersiz sunucu yanıtı.";
        return;
      }
      status.textContent = `${data.chapter_count} bölüm eklendi.`;
      el("fileInput").value = "";
      closeAddModal();
      navigate({ view: "reader", url: data.first_url });
    } else {
      let msg = `Hata (${xhr.status})`;
      try {
        msg = JSON.parse(xhr.responseText).detail || msg;
      } catch {}
      status.textContent = "Yüklenemedi: " + msg;
    }
  };
  xhr.onerror = () => {
    btn.disabled = false;
    status.textContent = "Yüklenemedi: ağ hatası.";
  };
  xhr.send(f);
}

function savePasteDraft() {
  try {
    localStorage.setItem(LS_PASTE_DRAFT, JSON.stringify({
      book: el("pasteBookTitle").value,
      title: el("pasteChapterTitle").value,
      no: el("pasteChapterNo").value,
      text: el("pasteText").value,
    }));
  } catch {}
}

function restorePasteDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(LS_PASTE_DRAFT)) || {};
    el("pasteBookTitle").value = d.book || "";
    el("pasteChapterTitle").value = d.title || "";
    el("pasteChapterNo").value = d.no || "";
    el("pasteText").value = d.text || "";
  } catch {}
}

async function fillPasteBookSelect() {
  const sel = el("pasteBookSelect");
  while (sel.options.length > 1) sel.remove(1);
  const books = (await fetchBooks()) || [];
  for (const b of books) {
    if (!b.slug.startsWith("paste-")) continue; // yalnız içe aktarılan kitaplara eklenebilir
    const opt = document.createElement("option");
    opt.value = b.slug;
    opt.textContent = b.title || b.slug;
    sel.appendChild(opt);
  }
}

async function openAddModal() {
  el("addUrlInput").value = "";
  restorePasteDraft();
  // Dosya sekmesini sıfırla (önceki hata/ilerleme kalmasın).
  el("fileInput").value = "";
  el("uploadProgress").hidden = true;
  el("uploadStatus").textContent = "";
  setAddTab(addTab);
  el("addModal").hidden = false;
  fillPasteBookSelect();
  if (addTab === "url") el("addUrlInput").focus();
}
function closeAddModal() {
  savePasteDraft(); // taslak kaybolmasın
  el("addModal").hidden = true;
}

async function submitPaste() {
  const btn = el("addConfirm");
  const text = el("pasteText").value.trim();
  const title = el("pasteChapterTitle").value.trim();
  if (!text) {
    el("pasteText").focus();
    return;
  }
  const slug = el("pasteBookSelect").value || null;
  const no = parseInt(el("pasteChapterNo").value, 10);
  btn.disabled = true;
  try {
    const res = await fetch("/api/import/paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        text,
        book_title: el("pasteBookTitle").value.trim() || null,
        slug,
        chapter_no: Number.isFinite(no) && no > 0 ? no : null,
      }),
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    try {
      localStorage.removeItem(LS_PASTE_DRAFT);
    } catch {}
    ["pasteBookTitle", "pasteChapterTitle", "pasteChapterNo", "pasteText"].forEach(
      (id) => (el(id).value = "")
    );
    el("addModal").hidden = true;
    // Kitap görünümüne git: koşan paste-import işi ilerleme ekranını kendisi açar.
    navigate({ view: "book", slug: data.slug });
  } catch {
    alert("İçe aktarma başarısız — sunucuya ulaşılamadı veya metin reddedildi.");
  } finally {
    btn.disabled = false;
  }
}

/* ---------- okuyucu ---------- */
function setStatus(message) {
  const s = el("status");
  s.replaceChildren();
  if (!message) {
    s.hidden = true;
    return;
  }
  s.hidden = false;
  s.textContent = message;
}

function renderError(err, url, refresh) {
  isRestoring = false;
  
  const msgText = err.message || String(err);
  const errorClass = err.errorClass || null;

  const errorCard = el("readerError");
  errorCard.replaceChildren();
  errorCard.hidden = false;

  const title = document.createElement("div");
  title.className = "error-title";
  title.textContent = "Bir Hata Oluştu";
  errorCard.appendChild(title);

  const desc = document.createElement("p");
  desc.setAttribute("aria-live", "polite");
  errorCard.appendChild(desc);

  const actions = document.createElement("div");
  actions.className = "error-actions";
  errorCard.appendChild(actions);

  const retryBtn = document.createElement("button");
  retryBtn.className = "primary-btn";
  retryBtn.textContent = "Tekrar Dene";
  retryBtn.addEventListener("click", () => {
    errorCard.hidden = true;
    loadChapter(url, { refresh });
  });

  const backToLibBtn = document.createElement("button");
  backToLibBtn.className = "secondary-btn";
  backToLibBtn.textContent = "Kitaplığa Dön";
  backToLibBtn.addEventListener("click", () => {
    errorCard.hidden = true;
    // Hatalı okuyucu kaydını kütüphaneyle DEĞİŞTİR (push değil) → geçmiş kirlenmez,
    // geri jesti bu ölü bölüme dönmez.
    navigate({ view: "library" }, true);
  });

  if (errorClass === "CloudflareChallenge") {
    title.textContent = "Doğrulama Gerekli";
    const isMobile = window.innerWidth < 768;
    if (isMobile) {
      desc.textContent = "Bu bölüm Cloudflare koruması altında ve telefondan doğrudan açılamıyor. Lütfen önce bilgisayardan (doğrulama gerektiren pencereden) doğrulamayı en az bir kere geçin; ardından telefonda okumaya devam edebilirsiniz.";
      
      backToLibBtn.className = "primary-btn";
      retryBtn.className = "secondary-btn";
      actions.append(backToLibBtn, retryBtn);
      backToLibBtn.focus();
    } else {
      desc.textContent = "Cloudflare doğrulaması geçilemedi. Çözmek için sunucuyu kapatıp FETCH_HEADLESS=0 ile başlatarak açılan pencerede doğrulamayı tamamlayın (ya da start_chrome_cdp.py kullanıyorsanız Chrome penceresinde çözün).";
      
      retryBtn.className = "secondary-btn";
      actions.append(retryBtn, backToLibBtn);
      retryBtn.focus();
    }
  } else if (errorClass === "OriginError") {
    title.textContent = "Kaynak Site Hatası";
    desc.textContent = "Romanın yayınlandığı kaynak site şu anda yanıt vermiyor (HTTP 52x). Bu durum sitenin kendi sunucu problemidir. Bir süre bekledikten sonra tekrar deneyebilirsiniz.";
    
    actions.append(retryBtn, backToLibBtn);
    retryBtn.focus();
  } else {
    failedAttempts++;
    if (failedAttempts >= 2) {
      desc.textContent = `Hata (${failedAttempts}. deneme): ${msgText}. Hata devam ediyor. Lütfen internet bağlantınızı veya kaynak sitenin açık olup olmadığını kontrol edin.`;
    } else {
      desc.textContent = `Hata: ${msgText}`;
    }

    actions.append(retryBtn, backToLibBtn);
    retryBtn.focus();
  }
}

// GİRİŞ NOKTASI: yeni bir akış başlat (kütüphane/kitap/devam/geçmiş → tek bölümden).
// Akış sıfırlanır, ilk bölüm çekilip render edilir, alt gözlemci (sonrakini otomatik
// ekle) ve üst "önceki" kartı kurulur, kaldığın orana kaydırılır ve next ısıtılır.
async function loadChapter(url, opts = {}) {
  if (!url) return;
  const { refresh = false, restoreRatio = null, koken = null } = opts;
  isNavigating = true;
  isRestoring = true;
  el("readerError").hidden = true;

  const wasHidden = views.reader.hidden;
  if (wasHidden) showView("reader");
  closeFind();
  el("settingsPanel").hidden = true;
  resetStream();
  setStatus(refresh ? "Yeniden çevriliyor…" : "Yükleniyor…");

  try {
    const data = await fetchChapterData(url, refresh);
    setStatus(null);
    failedAttempts = 0;
    isNavigating = false;
    const entry = buildChapterEntry(url, data);
    stream.push(entry);
    const body = el("readerBody");
    body.classList.toggle("manga-mode", entry.isManga); // webtoon kenardan kenara + kesintisiz
    body.replaceChildren(entry.el);
    body.hidden = false;
    ensureTopCard();
    ensureBottomSentinel();
    setActiveChapter(entry);
    // KÖKEN varken kayıtlı konum HİÇ okunmaz. `restoreRatio: null` yetmiyordu:
    // null "konum yok" değil "yerel kayıttan al" demek ve o kayıt genellikle
    // bölümün SONU (orası okunmuş) — sözlükten gelen kullanıcı bölümün dibinde
    // açılıyordu.
    const ratio = koken ? 0 : (restoreRatio != null ? restoreRatio : getScrollLocal(url));
    scrollToChapterRatio(entry, ratio || 0);
    prefetchNext(entry);
    // Bölüm listesini ısıt: akış devamının zincir KOPTUĞUNDA (kitap ikinci bir
    // siteden sürüyor / çevrimdışı) düşeceği kaynak budur; çevrimiçiyken çekilirse
    // SW önbelleğine girer ve telefon çevrimdışıyken de indirilmiş bölümlere devam eder.
    ensureChapterList(entry.bookSlug);
  } catch (err) {
    isNavigating = false;
    isRestoring = false;
    renderError(err, url, refresh);
  }
}

// /api/chapter → veri ya da tipli hata (error_class ile). loadChapter/append/prepend
// ve yeniden-çevir aynı çekim yolunu paylaşır (DRY).
// track=false: akışa ÖNDEN eklenen (henüz okunmamış) bölümler → kitabın konumunu
// SUNUCUDA ilerletme; konumu yalnız aktif bölümün position POST'u belirlesin. Aksi
// halde önden-ekleme okunmamış bölüme konum yazıp aktif-POST'la yarışır (gerçek
// bulgu: current_url 7'de takılırken cache'te bölüm 8 oluşuyordu).
// refetch=true: sunucuyu SİTEDEN indirmeye zorlar. Varsayılan false — önbellekte
// hizalı İngilizce kaynak varsa "yeniden çevir" web'e hiç gitmez. Yalnız kaynağın
// KENDİSİ bozuk geldiğinde ("Bölüm Boş" kartı) indirmek gerekir.
function fetchChapterData(url, refresh, track = true, refetch = false) {
  const query =
    `/api/chapter?url=${encodeURIComponent(url)}` +
    (refresh ? "&refresh=1" : "") +
    (track ? "" : "&track=0") +
    (refetch ? "&refetch=1" : "");
  return fetch(query).then(async (res) => {
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      throw {
        message: e.detail?.message || e.detail || `Sunucu hatası (${res.status})`,
        errorClass: e.detail?.error_class || null,
      };
    }
    return res.json();
  });
}

function resetStream() {
  stream = [];
  activeUrl = null;
  streamBusy = false;
  mangaNextExhausted = false; // yeni kitap/bölüm → manga devam bayrağını sıfırla
  loggedReads.clear();
  if (bottomObserver) {
    bottomObserver.disconnect();
    bottomObserver = null;
  }
  el("readerBody").replaceChildren();
}

function isSyntheticSlug(slug) {
  return (
    !!slug &&
    (slug.startsWith("paste-") ||
      slug.startsWith("pdf-") ||
      slug.startsWith("manga-") ||
      slug.startsWith("epub-"))
  );
}

// Bölüm listesinden (openBook doldurur) bir önceki bölümün url'i — server prev_url
// yoksa yedek (birleştirilmiş kitaplarda sayfa nav'ı eksik olabilir).
function chapterListPrev(url) {
  if (currentChapters && currentChapters.length) {
    const idx = currentChapters.findIndex((c) => c.url === url);
    if (idx > 0) return currentChapters[idx - 1].url;
  }
  return null;
}

/* ---------- akış devamı: zincir (next_url) + kitabın bölüm listesi ----------
   Zincir TEK kaynak DEĞİLDİR. Aynı kitabı iki ayrı siteden çevirmiş olabilirsin:
   o zaman bölüm 100'ün next_url'ü A sitesinin HİÇ ÇEVRİLMEMİŞ 101'ini gösterir,
   fiilen indirilmiş 101 ise B sitesinden gelmiştir. Zincirin peşine düşmek
   çevrimdışıyken (ya da site engelliyken) akışı öldürüyordu — indirilmiş bölümler
   dururken okuma bölüm listesinden elle devam ettirilmek zorunda kalıyordu.
   Liste bölüm numarasına göre sıralı gelir (cache.list_chapters). */
let streamChapters = { slug: null, list: [] }; // akıştaki kitabın bölüm listesi

function chapterListFor(slug) {
  if (!slug) return [];
  if (slug === currentBookSlug && currentChapters.length) return currentChapters;
  return streamChapters.slug === slug ? streamChapters.list : [];
}

// Listeyi hazırla (yoksa çek). GET olduğu için SW çevrimdışıyken son kaydı verir;
// hiç kaydı yoksa boş liste → davranış eskisi gibi zincire düşer.
async function ensureChapterList(slug) {
  const yerel = chapterListFor(slug);
  if (yerel.length || !slug) return yerel;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/chapters`);
    const data = await res.json();
    streamChapters = { slug, list: data.chapters || [] };
  } catch {
    streamChapters = { slug, list: [] };
  }
  return streamChapters.list;
}

// Akışta sıradaki bölümün url'i: zincirin next'i bu kitapta ÇEVRİLMEMİŞSE ve listede
// indirilmiş bir sonraki bölüm varsa LİSTE kazanır. Zincir listedeyse (normal akış)
// ya da liste yoksa zincir kazanır — web'den ilerleyen okumada davranış değişmez.
function pickNextTarget(last) {
  if (!last) return null;
  const list = chapterListFor(last.bookSlug);
  const idx = list.findIndex((c) => c.url === last.url);
  const listNext = idx >= 0 && idx + 1 < list.length ? list[idx + 1].url : null;
  if (!last.nextUrl) return listNext;
  if (listNext && !list.some((c) => c.url === last.nextUrl)) return listNext;
  return last.nextUrl;
}

// Bir bölüm için akış girdisi + <article data-url> öğesini kur. Ayraç "— Bölüm N —"
// (ritüel dikiş); boş/kısa çeviri → bölüm-yerel "Bölüm Boş" kartı. Render etmez,
// sadece kurar (çağıran DOM'a ekler).
function buildChapterEntry(url, data) {
  // content_type="html": görsel içerik (PDF çevrilmiş sayfa <img> / EPUB yerinde HTML).
  // Paragraf/iki-dilli/arama yok; translation innerHTML olarak basılır.
  const isHtml = data.content_type === "html";
  const paras = isHtml
    ? []
    : (data.translation || "").split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
  const source = !isHtml && data.source ? data.source.split(/\n\n+/).map((p) => p.trim()) : [];
  const entry = {
    url,
    no: data.chapter_no != null ? data.chapter_no : null,
    title: data.title || "",
    html: isHtml ? data.translation || "" : null,
    paras,
    source,
    nextUrl: data.next_url || null,
    prevUrl: data.prev_url || chapterListPrev(url),
    bookSlug: data.book_slug || null,
    bookTitle: data.book_title || "",
    // KÜNYE: hangi motor çevirdi + bu bölümde sözlüğe eklenenler. Eski önbellekteki
    // bölümlerde bu alanlar YOK (sütunlar sonradan eklendi) → rozet hiç çizilmez.
    engine: data.engine || null,
    model: data.model || null, // zincirin fiilen çeviren halkası (eski bölümlerde yok)
    addedTerms: data.added_terms || null,
    // Sözlük uyum bayrağı: karşılığı KAYITLI olduğu hâlde İngilizce kalan terimler.
    // Zincirin alt halkaları sözlük kuralına eşit uymuyor (ölçüm: flash-lite %24,
    // 3.6-flash %0,7) ve çeviri kalıcı önbelleğe yazıldığı için sessizce kalıyordu.
    glossaryLeaks: data.glossary_leaks || null,
    // İngilizce kalıntı bayrağı: onarım turundan SONRA hâlâ çevrilmemiş paragraflar.
    // Sözlük ihlalinden AYRI bir arıza sınıfı — o "terimi yanlış yazdın" der, bu
    // "bu paragrafı hiç çevirmedin" der; ikisini tek sayaçta toplamak, okuyucunun
    // hangisine baktığını belirsizleştirirdi.
    ingilizceKalinti: data.ingilizce_kalinti || null,
    el: null,
    loaded: false,
    empty: false,
  };
  // Manga (webtoon) KESİNTİSİZ akar: sayfa görselleri ayraçsız + boşluksuz üst üste
  // dizilir (kullanıcı: "sayfa sayfa bölme"). PDF/EPUB/metin ayraçlı kalır.
  const isManga = url.startsWith("manga://");
  entry.isManga = isManga;
  const art = document.createElement("article");
  art.className =
    "chapter" + (isHtml ? " chapter-html" : "") + (isManga ? " chapter-manga" : "");
  art.dataset.url = url;
  if (entry.no != null) art.dataset.no = entry.no;
  if (!isManga) {
    const sep = document.createElement("div");
    sep.className = "chapter-sep";
    // Görsel içerikte ayraç başlığı gösterir ("Sayfa 32"); metin bölümde "Bölüm N".
    sep.textContent = isHtml
      ? `— ${entry.title || (entry.no != null ? "Bölüm " + entry.no : "Bölüm")} —`
      : entry.no != null
        ? `— Bölüm ${entry.no} —`
        : `— ${entry.title || "Bölüm"} —`;
    art.appendChild(sep);
  }
  entry.el = art; // renderParagraphs/renderHtml entry.el'e yazar → sep'ten ÖNCE atanmalı
  if (data.content_type === "translating") {
    // Manga: bölüm arka planda çevriliyor, bu sayfa henüz hazır değil → yer tutucu + poll.
    entry.translating = true;
    renderTranslatingPlaceholder(entry, data.done, data.total);
    pollTranslating(entry);
  } else if (isHtml) {
    entry.loaded = true;
    renderHtmlContent(entry);
  } else if (!data.translation || data.translation.trim().length < 50) {
    entry.empty = true;
    art.appendChild(emptyChapterCard(entry));
  } else {
    entry.loaded = true;
    renderParagraphs(entry, "");
  }
  return entry;
}

// Çevriliyor yer tutucu (manga sayfası batch'te sırasını bekliyor).
function renderTranslatingPlaceholder(entry, done, total) {
  const art = entry.el;
  [...art.children].forEach((n) => {
    if (!n.classList.contains("chapter-sep")) n.remove();
  });
  const div = document.createElement("div");
  div.className = "manga-translating";
  const prog = total ? ` (${done}/${total})` : "";
  div.innerHTML =
    `<span class="loading-spinner" aria-hidden="true"></span> Sayfa çevriliyor…${prog}`;
  art.appendChild(div);
}

// Çevriliyor sayfayı poll et: hazır olunca görsele çevir, değilse ilerlemeyi güncelle.
async function pollTranslating(entry) {
  await new Promise((r) => setTimeout(r, 3500));
  if (views.reader.hidden || !stream.includes(entry)) return; // reader kapandı/akış sıfırlandı
  let data;
  try {
    data = await fetchChapterData(entry.url, false, false);
  } catch {
    return pollTranslating(entry); // ağ hatası → tekrar dene
  }
  if (!stream.includes(entry)) return;
  if (data.content_type === "translating") {
    renderTranslatingPlaceholder(entry, data.done, data.total);
    return pollTranslating(entry);
  }
  if (data.content_type === "html") {
    entry.html = data.translation || "";
    entry.translating = false;
    entry.loaded = true;
    entry.nextUrl = data.next_url || entry.nextUrl;
    renderHtmlContent(entry);
    updateActiveChapter();
    updateEndCard();
    maybeAppendNext(); // sıradaki sayfayı da akışa al
  }
}

// Görsel içerik (PDF sayfa görseli / EPUB HTML): translation'ı innerHTML olarak bas.
// EPUB HTML sunucuda temizlenir (script/on* yok); PDF <img> üretilmiştir → güvenli.
function renderHtmlContent(entry) {
  const art = entry.el;
  [...art.children].forEach((n) => {
    if (!n.classList.contains("chapter-sep")) n.remove();
  });
  const div = document.createElement("div");
  div.className = "html-content";
  div.innerHTML = entry.html || "";
  art.appendChild(div);
  appendKunye(entry, art);
}

// Bölümün paragraflarını (arama sorgusu varsa vurgulu) article içine çiz — ayraç
// dışındaki her şeyi (eski p / source-line / boş-kart) temizler, yeniden kurar.
function renderParagraphs(entry, query) {
  const art = entry.el || document.createElement("article");
  [...art.children].forEach((n) => {
    if (!n.classList.contains("chapter-sep")) n.remove();
  });
  const q = (query || "").trim();
  entry.paras.forEach((para, i) => {
    const p = document.createElement("p");
    p.dataset.idx = i;
    if (q) appendHighlighted(p, para, q);
    else p.textContent = para;
    art.appendChild(p);
  });
  appendKunye(entry, art);
}

/* ---------- bölüm künyesi ----------
   Bölümün SONUNA, dokununca açılan küçük bir rozet: hangi motor çevirdi ve bu
   bölümde sözlüğe hangi terimler eklendi. Otomatik sözlük eklemesi sessiz çalışıyor
   ve hatalı bir karşılığı kalıcı kılabiliyor (gerçek bulgu: "Ore Empire" →
   "Ork İmparatorluğu"); okurken görülebilmesi gerekiyor.

   NOT: kart `renderParagraphs`/`renderHtmlContent` SONUNDA çizilir, `buildChapterEntry`
   içinde DEĞİL — iki render fonksiyonu da article'ı `.chapter-sep` dışında temizleyip
   yeniden kuruyor ve bölüm içi arama `renderParagraphs`'ı tekrar çağırıyor. Yukarıda
   eklenseydi ilk aramada sessizce kaybolurdu. */
function appendKunye(entry, art) {
  const kart = kunyeKarti(entry);
  if (kart) art.appendChild(kart);
}

function kunyeKarti(entry) {
  const motor = entry.engine;
  const terimler = entry.addedTerms || {};
  const adlar = Object.keys(terimler);
  // Sözlüğe UYULMAMIŞ terimler. Boş dict ("denetlendi, temiz") ile null ("hiç
  // denetlenmedi", eski satır) arasında okuyucu için fark yok: ikisinde de uyarı yok.
  const ihlaller = entry.glossaryLeaks || {};
  const ihlalAdlari = Object.keys(ihlaller).sort();
  // Çevrilmeden İngilizce kalan paragraflar (onarım turundan SONRA kalanlar).
  const kalinti = entry.ingilizceKalinti || {};
  const kalintiIndeksleri = Object.keys(kalinti);
  // Eski önbellekteki bölümde künye yok: "bilinmiyor" yazmak yanıltıcı olur, sessizce atla.
  if (
    !motor &&
    adlar.length === 0 &&
    ihlalAdlari.length === 0 &&
    kalintiIndeksleri.length === 0
  )
    return null;

  const uyariVar = ihlalAdlari.length > 0 || kalintiIndeksleri.length > 0;
  const kutu = document.createElement("details");
  kutu.className = "kunye" + (uyariVar ? " kunye-uyarili" : "");
  const ozet = document.createElement("summary");
  ozet.className = "kunye-ozet";
  // Uyarı özete ÇIKAR: rozet kapalı duruyor ve açılmazsa bayrak görünmezdi — tek
  // işi zaten sessiz kalan bir bozukluğu görünür kılmak. İki arıza sınıfı AYRI
  // sayılır: biri "terim yanlış", öteki "paragraf hiç çevrilmemiş".
  const uyarilar = [];
  if (kalintiIndeksleri.length)
    uyarilar.push(`${kalintiIndeksleri.length} paragraf İngilizce kaldı`);
  if (ihlalAdlari.length)
    uyarilar.push(`${ihlalAdlari.length} terim sözlüğe uymadı`);
  ozet.textContent = uyarilar.length
    ? `⚠ ${uyarilar.join(" · ")}`
    : adlar.length
      ? `Sözlüğe ${adlar.length} terim eklendi`
      : "Çeviri bilgisi";
  kutu.appendChild(ozet);

  const govde = document.createElement("div");
  govde.className = "kunye-govde";
  if (motor) {
    const rozet = document.createElement("span");
    rozet.className = "style-badge";  // mevcut pill rozet dili
    /* Motor FİİLEN çeviren sağlayıcıdan geliyor. Bugün tek motor var ("gemini")
       ama rozet SABİT YAZMAZ: bir dönem tam olarak öyle yapılmıştı ve ikinci bir
       sağlayıcı zincire girince doğrudan yanlış bilgiye dönüştü — o sağlayıcının
       çevirdiği bölüm "GEMINI ile çevrildi" diyordu. Ad olduğu gibi büyütülür,
       böylece motor bir daha değişirse burada ayrıca bir dal açmak gerekmez.
       DB'de kaldırılmış motorlardan kalma "mistral"/"claude" satırları duruyor ve
       bu yolla doğru etiketlenmeye devam ederler. */
    rozet.textContent = motor
      .split(" + ")
      .map((m) => m.trim().toUpperCase())
      .join(" + ");
    const satir = document.createElement("p");
    satir.className = "gloss-hint kunye-satir";
    satir.append(rozet, document.createTextNode(" ile çevrildi"));
    // Motorun İÇİNDEKİ model: zincir tökezleyince alt halkaya düşülüyor ve üslup
    // farkı oradan geliyor. "gemini-" öneki kırpılır — rozet zaten motoru söylüyor.
    // Parçalar farklı halkalara düştüyse sunucu " + " ile birleştirip gönderir.
    if (entry.model) {
      // Sağlayıcı öneki kırpılır (`mistral:`, `openrouter:`, …). Bugünkü zincirde
      // önekli ad ÜRETİLMİYOR (Gemini-tek) ama önbellekte o dönemden kalma satırlar
      // var ve kırpma onlar için hâlâ gerekli: adı iki kez yazmak
      // "mistral:mistral-medium-latest" gibi okunmaz bir satır üretiyordu.
      // Model adının içindeki `/` korunur ("minimax/minimax-m3:free" gibi).
      const kisa = entry.model
        .split(" + ")
        .map((m) => m.replace(/^[a-z0-9]+:/, "").replace(/^gemini-/, ""))
        .join(" + ");
      satir.append(document.createTextNode(` · ${kisa}`));
    }
    govde.appendChild(satir);
  }
  if (kalintiIndeksleri.length) {
    const uyari = document.createElement("p");
    uyari.className = "gloss-hint kunye-satir kunye-ihlal";
    uyari.textContent =
      "Bu paragraflar çevrilmeden İngilizce kaldı ve hedefli yeniden çeviri de " +
      "düzeltemedi. “Yeniden Çevir” ile tekrar denenebilir (kaynak önbellekte, " +
      "siteye yeniden inilmez).";
    govde.appendChild(uyari);
    const liste = document.createElement("ul");
    liste.className = "kunye-liste kunye-ihlal-liste";
    // Sıra SAYISAL olmalı: anahtarlar JSON'dan string geliyor ve düz sort()
    // "10" < "9" der, yani paragraflar okuma sırasının dışında listelenirdi.
    for (const i of kalintiIndeksleri.sort((a, b) => Number(a) - Number(b))) {
      const li = document.createElement("li");
      li.className = "kunye-ihlal-terim";
      const metin = String(kalinti[i] || "");
      li.textContent = metin.length > 120 ? `${metin.slice(0, 120)}…` : metin;
      liste.appendChild(li);
    }
    govde.appendChild(liste);
  }
  if (ihlalAdlari.length) {
    const uyari = document.createElement("p");
    uyari.className = "gloss-hint kunye-satir kunye-ihlal";
    uyari.textContent =
      "Sözlükte karşılığı olduğu hâlde İngilizce bırakılan terimler. Bu genellikle " +
      "zincirin alt halkası çevirdiğinde olur; “Yeniden Çevir” ile düzelir " +
      "(kaynak önbellekte, siteye yeniden inilmez).";
    govde.appendChild(uyari);
    const liste = document.createElement("ul");
    liste.className = "kunye-liste kunye-ihlal-liste";
    for (const kaynak of ihlalAdlari) {
      // `kunye-terim` DEĞİL: o sınıf sözlük ekranıyla ortak DÜZENLENEBİLİR satır
      // düzenidir (`:has(.kunye-terim)` madde imini kaldırıp satır kenarlığı verir).
      // İhlal satırı düzenlenmez, sade madde kalmalı.
      const li = document.createElement("li");
      li.className = "kunye-ihlal-terim";
      li.textContent = `${kaynak} → ${ihlaller[kaynak]}`;
      liste.appendChild(li);
    }
    govde.appendChild(liste);
  }
  if (adlar.length) {
    const liste = document.createElement("ul");
    liste.className = "kunye-liste";
    for (const kaynak of adlar.sort()) {
      liste.appendChild(kunyeTerimSatiri(entry, kaynak, terimler[kaynak]));
    }
    govde.appendChild(liste);
    const ipucu = document.createElement("p");
    ipucu.className = "gloss-hint kunye-satir";
    ipucu.textContent =
      "Bu terimler sonraki bölümlerde de aynı kalır. Karşılığı burada düzeltebilir " +
      "ya da × ile silebilirsin; değişiklik yeni çevrilen bölümlerde geçerli olur.";
    govde.appendChild(ipucu);
  }
  kutu.appendChild(govde);
  return kutu;
}

/* Künyedeki terim satırı DÜZENLENEBİLİR.

   Neden: otomatik ekleme sessizce yanlış bir karşılığı KALICI kılabiliyor (gerçek
   örnekler, DB'deki `added_terms` kayıtlarından: "Sleeper Center → Uyuyan Merkezi",
   doğrusu "Uyuyanlar Merkezi"; "Star-Moon City → yıldız ay şehri", oysa kardeş
   kayıt "Star-Moon Kingdom → Yıldız-Ay Krallığı"). Rozet eskiden yalnız SÖYLÜYORDU;
   düzeltmek için okumayı bırakıp sözlük ekranında terimi aramak gerekiyordu — yani
   onay anı okuma akışının dışındaydı ve pratikte hiç gelmiyordu.

   Yazma yolu sözlük ekranıyla AYNI kuyruk (`saveTerm`/`deleteTerm`) → sunucu
   kapalıyken de çalışır, bağlanınca gönderilir. */
function kunyeTerimSatiri(entry, kaynak, karsilik) {
  const slug = entry.bookSlug || currentBookSlug;
  const korunuyor = !karsilik || karsilik === kaynak;
  const li = document.createElement("li");
  li.className = "kunye-terim";
  li.title = korunuyor
    ? `${kaynak} İngilizce korunuyor`
    : `${kaynak} → ${karsilik}`;

  const ad = document.createElement("span");
  ad.className = "gloss-source";
  ad.textContent = kaynak;

  const ok = document.createElement("span");
  ok.className = "gloss-arrow";
  ok.textContent = "→";

  const alan = document.createElement("input");
  alan.className = "gloss-target";
  alan.type = "text";
  alan.value = karsilik || kaynak;
  alan.setAttribute("aria-label", kaynak + " karşılığı");
  alan.addEventListener("change", () => {
    if (!slug) return;
    saveTerm(slug, kaynak, alan.value.trim() || kaynak);
    li.classList.add("gloss-row-pending"); // gönderim bitince kalkar
  });

  const sil = document.createElement("button");
  sil.className = "gloss-del";
  sil.textContent = "×";
  sil.setAttribute("aria-label", kaynak + " terimini sözlükten sil");
  sil.addEventListener("click", () => {
    if (!slug) return;
    li.remove();
    deleteTerm(slug, kaynak);
  });

  li.append(ad, ok, alan, sil);
  return li;
}


function emptyChapterCard(entry) {
  const card = document.createElement("div");
  card.className = "empty-card reader-error-card";
  card.style.position = "static";
  card.style.margin = "2rem auto";
  const title = document.createElement("div");
  title.className = "error-title";
  title.textContent = "Bölüm Boş";
  const desc = document.createElement("p");
  desc.textContent = "Bu bölümün çeviri metni boş veya çok kısa geldi. Çeviri başarısız olmuş olabilir.";
  const actions = document.createElement("div");
  actions.className = "error-actions";
  const btn = document.createElement("button");
  btn.className = "primary-btn";
  // Burada sorun ÇEVİRİ değil KAYNAK olabilir (site yarım/bozuk sayfa vermiş) →
  // indirmeyi zorla. Etiket bunu söylüyor: bu yol siteye iner, yavaştır.
  btn.textContent = "Siteden Yeniden Çek";
  btn.addEventListener("click", () => retranslateChapter(entry, true));
  actions.appendChild(btn);
  card.append(title, desc, actions);
  return card;
}

/* ---------- prefetch: sonraki bölümü sessizce ısıt ---------- */
const PREFETCH_YOKLAMA_MS = 5000;
const PREFETCH_YOKLAMA_MAX = 12; // ~60 sn; ölçülen çeviri süresi 15-45 sn

function prefetchNext(entry) {
  const u = entry && entry.nextUrl;
  if (!u || !/^https?:\/\//.test(u) || prefetched.has(u)) return;
  prefetched.add(u);
  isitVeKaydet(u, PREFETCH_YOKLAMA_MAX);
}

// Isıtma POST'u bölümü sunucuda hazırlar ama telefona içerik göndermez; hazır olunca
// bir GET atılır ve SW onu önbelleğe yazar. Sabit gecikme yerine YOKLAMA kullanılır:
// çeviri süresi oynak (ölçüm 2026-08-31: aynı kitapta 45 sn ve 15,7 sn). Erken atılan
// GET, prefetch'in bitmesini beklemek yerine ikinci bir çeviri tetikleyebilirdi.
// Yoklama POST'u güvenle tekrarlanır: uç `_PREFETCH_INFLIGHT` ile aynı url için ikinci
// işi başlatmaz, yalnız "hazır mı" der (DB araması).
async function isitVeKaydet(url, kalanDeneme) {
  let veri;
  try {
    const r = await fetch("/api/prefetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    veri = await r.json();
  } catch {
    return; // çevrimdışı / sunucu kapalı: ısıtma en iyi çabadır
  }
  if (veri && veri.cached) {
    await warmOffline(url);
    return;
  }
  if (kalanDeneme > 0) {
    setTimeout(() => isitVeKaydet(url, kalanDeneme - 1), PREFETCH_YOKLAMA_MS);
  }
}

/* ---------- akış sonu: sonraki bölümü otomatik ekle (IntersectionObserver) ---------- */
function ensureBottomSentinel() {
  let s = el("streamEnd");
  if (!s) {
    s = document.createElement("div");
    s.id = "streamEnd";
    s.className = "stream-end";
  }
  el("readerBody").appendChild(s); // her zaman en sona
  updateEndCard();
  if (bottomObserver) bottomObserver.disconnect();
  bottomObserver = null;
  // Sonsuz okuma kapalıysa gözlemci HİÇ kurulmaz: bölüm sonunda akış büyümez,
  // devam elle olur (updateEndCard "SONRAKİ BÖLÜM →" düğmesini çizer).
  if (!settings.infinite) return;
  bottomObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((en) => en.isIntersecting)) maybeAppendNext();
    },
    { rootMargin: "800px 0px" } // görünmeden ~800px önce hazırla (dikişsiz akış)
  );
  bottomObserver.observe(s);
}

// Ayar değişince (sonsuz okuma aç/kapa) akışın sonunu yeniden kur: gözlemci
// kurulur/kaldırılır ve bitiş kartı doğru düğmeye döner.
function refreshStreamEnd() {
  if (views.reader.hidden || !stream.length) return;
  ensureBottomSentinel();
}

// Akışın sonuna göre uygun kartı göster: next varsa "hazırlanıyor" ipucu (gözlemci
// birazdan ekler); web bölümü ama next yok → "SONRAKINI WEB'DEN GETİR"; sentetik/son
// → "— Son bölüm —".
function updateEndCard() {
  const s = el("streamEnd");
  if (!s || !stream.length) return;
  const last = stream[stream.length - 1];
  // Hedef: zincirin next'i ya da (o kitapta çevrilmemişse) listedeki sıradaki bölüm.
  const target = pickNextTarget(last);
  const mangaContinue = !target && last.isManga && last.bookSlug && !mangaNextExhausted;
  s.replaceChildren();
  s.className = "stream-end";
  if (!settings.infinite && (target || mangaContinue)) {
    // Sonsuz okuma KAPALI: bölüm sonu bir duraktır, devam elle.
    const btn = document.createElement("button");
    btn.className = "primary-btn stream-cta";
    btn.textContent = "SONRAKİ BÖLÜM →";
    btn.addEventListener("click", () => goNextManual(btn));
    s.appendChild(btn);
  } else if (target || mangaContinue) {
    const d = document.createElement("div");
    d.className = "stream-hint";
    d.textContent = "Sonraki bölüm hazırlanıyor…";
    s.appendChild(d);
  } else if (/^https?:\/\//.test(last.url || "")) {
    const btn = document.createElement("button");
    btn.className = "primary-btn stream-cta";
    btn.textContent = "SONRAKINI WEB'DEN GETİR";
    btn.addEventListener("click", () => discoverNextForLast(btn));
    s.appendChild(btn);
  } else {
    const d = document.createElement("div");
    d.className = "stream-end-note";
    d.textContent = "— Son bölüm —";
    s.appendChild(d);
  }
}

async function maybeAppendNext() {
  if (streamBusy || !stream.length || !settings.infinite) return;
  const last = stream[stream.length - 1];
  if (last.translating) return; // sayfa çevriliyorsa sıradakini bekle
  streamBusy = true;
  let ok = false;
  const s = el("streamEnd");
  try {
    // Zincir + bölüm listesi (liste ilk kullanımda çekilir; çevrimdışıysa SW verir).
    await ensureChapterList(last.bookSlug);
    let targetUrl = pickNextTarget(last);
    // Sıradaki bölüm yok ama manga'nın site'de devamı olabilir → otomatik devam.
    const mangaContinue =
      !targetUrl && last.isManga && last.bookSlug && !mangaNextExhausted;
    if (!targetUrl && !mangaContinue) return; // finally streamBusy'yi bırakır
    s.replaceChildren();
    const load = document.createElement("div");
    load.className = "stream-loading";
    load.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span> Sonraki bölüm yükleniyor…`;
    s.appendChild(load);
    if (mangaContinue) {
      // Site'den SONRAKİ bölümü çek + zincire ekle (novel sonsuz okumanın manga karşılığı).
      const cont = await fetch("/api/manga/continue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: last.bookSlug }),
      }).then((r) => r.json());
      if (!cont.available || !cont.first_url) {
        mangaNextExhausted = true; // son bölüm / devam yok → bir daha deneme
        s.replaceChildren();
        updateEndCard();
        return; // finally streamBusy'yi bırakır
      }
      targetUrl = cont.first_url;
      last.nextUrl = targetUrl; // JS zincirini bağla (aynı bölümü tekrar tetikleme)
      if (!cont.has_next) mangaNextExhausted = true; // bu son bölümdü
    }
    // track=false: önden eklenen bölüm okunmuş sayılmaz → konumu ilerletmez.
    const data = await fetchChapterData(targetUrl, false, false);
    const entry = buildChapterEntry(targetUrl, data);
    stream.push(entry);
    el("readerBody").insertBefore(entry.el, s);
    updateEndCard();
    updateActiveChapter();
    prefetchNext(entry);
    ok = true;
  } catch (err) {
    // D-B8: dikiş hatası → tam-ekran kart DEĞİL, ince satır-içi bant + TEKRAR DENE.
    s.replaceChildren();
    const band = document.createElement("div");
    band.className = "stitch-error";
    const msg = document.createElement("span");
    msg.textContent = "Sonraki bölüm yüklenemedi.";
    const retry = document.createElement("button");
    retry.className = "pill";
    retry.textContent = "TEKRAR DENE";
    retry.addEventListener("click", () => {
      updateEndCard();
      maybeAppendNext();
    });
    band.append(msg, retry);
    s.appendChild(band);
  } finally {
    streamBusy = false;
    // Kısa bölümlerde (PDF sayfası) sentinel margin İÇİNDE kalabilir; IntersectionObserver
    // kenar-tetiklemeli olduğundan yeniden ateşlenmez ve akış "hazırlanıyor"da takılır.
    // Yeniden gözlemle → hâlâ görünürdeyse gözlemci tekrar tetikler, sonraki eklenir.
    // Görsel yüksekliği önden ayrıldığından (img width/height) sentinel gerçekten kayar,
    // sonsuz döngü olmaz. Yalnız BAŞARIDA (kalıcı hatada TEKRAR DENE'yi döngüye sokma).
    if (ok && bottomObserver) {
      const sen = el("streamEnd");
      if (sen) {
        bottomObserver.unobserve(sen);
        bottomObserver.observe(sen);
      }
    }
  }
}

/* Sonsuz okuma KAPALIYKEN "SONRAKİ BÖLÜM →": bölümü akışa eklemek yerine TEMİZ bir
   sayfa olarak açar (baştan başlar, bellek şişmez). history'ye replace ile yazılır —
   geri tuşu bölüm bölüm geri sarmaz, okuyucudan çıkar (akış modundaki davranışın
   aynısı). Manga zincir sonundaysa önce site'den sonraki bölümü çekmek gerekir. */
async function goNextManual(btn) {
  if (isNavigating || streamBusy) return;
  const last = stream[stream.length - 1];
  if (!last) return;
  await ensureChapterList(last.bookSlug);
  let target = pickNextTarget(last);
  if (!target) {
    if (!(last.isManga && last.bookSlug && !mangaNextExhausted)) return;
    btn.disabled = true;
    btn.textContent = "Sonraki bölüm getiriliyor…";
    try {
      const cont = await fetch("/api/manga/continue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: last.bookSlug }),
      }).then((r) => r.json());
      if (!cont.available || !cont.first_url) {
        mangaNextExhausted = true;
        updateEndCard();
        return;
      }
      target = cont.first_url;
    } catch {
      btn.disabled = false;
      btn.textContent = "SONRAKİ BÖLÜM →";
      return;
    }
  }
  navigate({ view: "reader", url: target }, true);
}

// "Sonrakini web'den getir": son bölümün sayfasını çekip next'ini öğrenir (çeviri
// yakmaz, E-3); bulursa akışa ekler. Site engelliyse kullanıcıyı bilgilendirir.
async function discoverNextForLast(btn) {
  const last = stream[stream.length - 1];
  if (!last) return;
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Aranıyor…";
  try {
    const res = await fetch("/api/chapter/refresh-nav", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: last.url }),
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (data.next_url) {
      last.nextUrl = data.next_url;
      updateEndCard();
      // Sonsuz okuma kapalıyken akış büyümez: kullanıcı düğmeye bastı, bölümü aç.
      if (settings.infinite) maybeAppendNext();
      else navigate({ view: "reader", url: data.next_url }, true);
    } else {
      btn.disabled = true;
      btn.textContent = "SON BÖLÜM";
    }
  } catch {
    btn.disabled = false;
    btn.textContent = orig;
    alert("Sonraki bölüm bulunamadı — site engelli olabilir. Kitap görünümünden 'BÖLÜM EKLE' ile metni de yapıştırabilirsiniz.");
  }
}

/* ---------- akış başı: önceki bölümü kaydırma-sabitlemeli ekle ---------- */
function ensureTopCard() {
  const first = stream[0];
  const body = el("readerBody");
  let t = el("streamTop");
  if (first && first.prevUrl) {
    if (!t) {
      t = document.createElement("button");
      t.id = "streamTop";
      t.className = "stream-top";
      t.textContent = "↑ ÖNCEKİ BÖLÜM";
      t.addEventListener("click", () => prependPrev(t));
    }
    if (body.firstChild !== t) body.insertBefore(t, body.firstChild);
    t.hidden = false;
    t.disabled = false;
    t.textContent = "↑ ÖNCEKİ BÖLÜM";
  } else if (t) {
    t.remove();
  }
}

async function prependPrev(btn) {
  if (streamBusy) return;
  const first = stream[0];
  if (!first || !first.prevUrl) return;
  streamBusy = true;
  btn.textContent = "Yükleniyor…";
  btn.disabled = true;
  const beforeH = document.documentElement.scrollHeight;
  try {
    // track=false: geri eklenen bölüm de konumu ilerletmez (aktif = okunan).
    const data = await fetchChapterData(first.prevUrl, false, false);
    const entry = buildChapterEntry(first.prevUrl, data);
    stream.unshift(entry);
    // Üst kart ile eski ilk bölüm arasına ekle → yeni ilk bölüm olur.
    el("readerBody").insertBefore(entry.el, btn.nextSibling);
    // Kaydırma sabitleme: eklenen yükseklik kadar aşağı it (görsel sıçrama olmasın).
    const delta = document.documentElement.scrollHeight - beforeH;
    window.scrollTo(0, window.scrollY + delta);
    ensureTopCard();
    prefetchNext(entry);
    updateActiveChapter();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "↑ ÖNCEKİ BÖLÜM";
    alert("Önceki bölüm yüklenemedi.");
  } finally {
    streamBusy = false;
  }
}

// Aktif bölümü yeniden çevir (Ayarlar → "Bu bölüm"). Ayraç korunur, gövde yeniden çizilir.
/* Geçen süreyi SAYARAK göster. Sabit "Yükleniyor…" ile donmuş ekran ayırt
   edilemiyordu: kullanıcı 1-2 dakikalık normal bir işi "takıldı" sandı. Sayaç
   ilerledikçe iş yürüyor demektir — sunucudan ilerleme taşımadan (tek istek/yanıt)
   verilebilecek en dürüst geri bildirim bu. */
function sureliDugmeSayaci(btn, etiket) {
  const bas = Date.now();
  const ciz = () => {
    const sn = Math.round((Date.now() - bas) / 1000);
    btn.innerHTML =
      `<span class="loading-spinner" aria-hidden="true"></span> ${etiket}` +
      (sn >= 3 ? ` ${sn} sn` : "");
  };
  ciz();
  const timer = setInterval(ciz, 1000);
  return () => clearInterval(timer);
}

async function retranslateChapter(entry, refetch = false) {
  const btn = el("retranslate");
  const orig = btn.innerHTML;
  const durdur = sureliDugmeSayaci(
    btn, refetch ? "Siteden çekiliyor…" : "Çevriliyor…"
  );
  btn.disabled = true;
  try {
    const data = await fetchChapterData(entry.url, true, true, refetch);
    entry.nextUrl = data.next_url || entry.nextUrl;
    entry.title = data.title || entry.title;
    if (data.content_type === "html") {
      entry.html = data.translation || "";
      entry.loaded = true;
      renderHtmlContent(entry);
    } else {
      entry.paras = (data.translation || "").split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
      entry.source = data.source ? data.source.split(/\n\n+/).map((p) => p.trim()) : [];
      if (entry.paras.length) {
        entry.empty = false;
        entry.loaded = true;
        renderParagraphs(entry, "");
      }
    }
    if (entry.url === activeUrl) el("readerChapter").textContent = entry.title || "Bölüm";
  } catch (err) {
    alert("Yeniden çevrilemedi: " + (err.message || err));
  } finally {
    durdur();
    btn.innerHTML = orig;
    btn.disabled = false;
  }
}

/* ---------- çift-tık/çift-dokunma: paragrafın İngilizce orijinali ----------
   Tek tık okuyucuda bir şey yapmaz; 350ms içinde aynı paragrafa ikinci tık =
   çift-tık (masaüstü + mobil tek mantık). Açıksa kapatır (toggle). */
let lastTapIdx = -1;
let lastTapUrl = null;
let lastTapAt = 0;

function onParaTap(e) {
  const p = e.target.closest("#readerBody article.chapter p[data-idx]");
  if (!p) return;
  const idx = Number(p.dataset.idx);
  const url = p.closest("article.chapter").dataset.url;
  const now = Date.now();
  if (idx === lastTapIdx && url === lastTapUrl && now - lastTapAt < 350) {
    lastTapIdx = -1;
    lastTapUrl = null;
    lastTapAt = 0;
    toggleSource(p, idx, url);
  } else {
    lastTapIdx = idx;
    lastTapUrl = url;
    lastTapAt = now;
  }
}

// Kaynak (İngilizce orijinal) bölüm-yereldir: dokunulan paragrafın ait olduğu bölümün
// source dizisinden okunur (aktif bölüm değil — akışta hangi paragrafa dokunulduysa o).
function toggleSource(p, idx, url) {
  const sib = p.nextElementSibling;
  if (sib && sib.classList.contains("source-line")) {
    sib.remove(); // ikinci çift-tık → kapat
    return;
  }
  const entry = entryFor(url);
  if (entry && entry.source[idx]) {
    insertSourceLine(p, entry.source[idx], "");
  } else {
    loadSourceForChapter(p, idx, url); // eski bölüm: kaynak yok → bir kez yükselt
  }
}

function insertSourceLine(p, text, extraClass) {
  const div = document.createElement("div");
  div.className = "source-line" + (extraClass ? " " + extraClass : "");
  div.textContent = text;
  p.after(div);
  return div;
}

async function loadSourceForChapter(p, idx, url) {
  if (!url || sourceLoading) return;
  sourceLoading = true;
  const note = insertSourceLine(p, "İngilizce getiriliyor…", "source-loading");
  try {
    const res = await fetch(`/api/chapter?url=${encodeURIComponent(url)}&source=1`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    const src = data.source ? data.source.split(/\n\n+/).map((s) => s.trim()) : [];
    const entry = entryFor(url);
    if (entry) entry.source = src;
    note.remove();
    if (src[idx]) insertSourceLine(p, src[idx], "");
    else insertSourceLine(p, "Bu bölüm için İngilizce kaynak yok.", "source-empty");
  } catch {
    note.textContent = "İngilizce getirilemedi.";
    note.classList.add("source-empty");
  } finally {
    sourceLoading = false;
  }
}

function appendHighlighted(p, text, q) {
  const lower = text.toLowerCase();
  const ql = q.toLowerCase();
  let i = 0;
  let idx;
  while ((idx = lower.indexOf(ql, i)) !== -1) {
    if (idx > i) p.appendChild(document.createTextNode(text.slice(i, idx)));
    const mark = document.createElement("mark");
    mark.textContent = text.slice(idx, idx + q.length);
    p.appendChild(mark);
    i = idx + q.length;
  }
  if (i < text.length) p.appendChild(document.createTextNode(text.slice(i)));
}

/* ---------- bölümde arama ---------- */
let findMatches = [];
let findIndex = -1;
let findTimer = null;

function openFind() {
  el("findBar").hidden = false;
  el("findInput").focus();
}
// Arama AKTİF bölüme kapsanır (D-B9v2) — akıştaki tüm bölümleri taramaz.
function closeFind() {
  el("findBar").hidden = true;
  el("findInput").value = "";
  findMatches = [];
  findIndex = -1;
  el("findCount").textContent = "";
  const e = activeEntry();
  if (e && e.loaded && !e.html) renderParagraphs(e, "");
}
function runFind() {
  const q = el("findInput").value.trim();
  const e = activeEntry();
  if (!e || !e.loaded || e.html) return; // görsel içerikte (PDF/EPUB) arama yok
  renderParagraphs(e, q);
  findMatches = q ? Array.from(e.el.querySelectorAll("mark")) : [];
  findIndex = findMatches.length ? 0 : -1;
  updateFindUI();
  focusMatch();
}
function updateFindUI() {
  if (findMatches.length) {
    el("findCount").textContent = `${findIndex + 1}/${findMatches.length}`;
  } else {
    el("findCount").textContent = el("findInput").value.trim() ? "0" : "";
  }
}
function focusMatch() {
  for (const m of findMatches) m.classList.remove("find-active");
  if (findIndex >= 0 && findMatches[findIndex]) {
    const m = findMatches[findIndex];
    m.classList.add("find-active");
    m.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}
function cycleFind(dir) {
  if (!findMatches.length) return;
  findIndex = (findIndex + dir + findMatches.length) % findMatches.length;
  updateFindUI();
  focusMatch();
}

/* ---------- olaylar: kütüphane yüzeyleri ---------- */
document.querySelectorAll("#shelfFilters .chip").forEach((c) =>
  c.addEventListener("click", () => setShelfFilter(c.dataset.filter))
);
el("filterClear").addEventListener("click", () => setShelfFilter("all"));
el("libRetry").addEventListener("click", () => {
  el("libError").hidden = true;
  el("libLoading").hidden = false;
  renderLibrary();
});
// D-B12: durum düzenleme kitap görünümünde. İyimser güncelle; sunucu reddederse
// eski değere dön (kalıcı yanlış aria-pressed bırakma).
document.querySelectorAll("[data-status-opt]").forEach((b) =>
  b.addEventListener("click", async () => {
    if (!currentBookSlug) return;
    const status = b.getAttribute("data-status-opt");
    const prev = (currentBook && currentBook.status) || "okunuyor";
    if (status === prev) return;
    markSegment("status", status, "data-status-opt");
    try {
      const res = await fetch(
        `/api/book/${encodeURIComponent(currentBookSlug)}/status`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        }
      );
      if (!res.ok) throw new Error();
      if (currentBook) currentBook.status = status;
    } catch {
      markSegment("status", prev, "data-status-opt");
    }
  })
);

/* ---------- olaylar: navigasyon ---------- */
el("libThemeToggle").addEventListener("click", cycleTheme);
// Tüm "geri" düğmeleri = history.back(): geçmiş yığınını POP eder (popstate → önceki
// görünüm). navigate() (push) KULLANMAZ — aksi halde "geri" ileri kayıt iter ve jest
// desenkron olurdu (bu bug'ın kök nedeni). Kök kayıt daima {library} (init'te
// replaceState) olduğundan back güvenli; kütüphanede back = uygulamadan çıkış.
el("backBtn").addEventListener("click", () => history.back());
el("bookBackBtn").addEventListener("click", () => history.back());
el("openGlossaryBtn").addEventListener("click", () => {
  if (currentBookSlug) navigate({ view: "glossary", slug: currentBookSlug });
});
el("glossaryBackBtn").addEventListener("click", () => history.back());
async function addGlossTerm() {
  const source = el("glossSource").value.trim();
  if (!source) return el("glossSource").focus();
  const target = el("glossTarget").value.trim() || source;
  saveTerm(currentBookSlug, source, target); // çevrimdışıysa kuyrukta bekler
  el("glossSource").value = "";
  el("glossTarget").value = "";
  renderGlossary(await fetchGlossary(currentBookSlug));
  el("glossSource").focus();
}
el("glossAddBtn").addEventListener("click", addGlossTerm);

/* ---------- yedek / toplu düzenleme ----------
   Sözlük tek bir PC'deki tek bir SQLite dosyasında yaşıyor; yedeği yoktu. Dışa
   aktarma düz bir indirme bağlantısı (sunucu Content-Disposition ile gönderiyor),
   içe aktarma dosyayı okuyup uca POST ediyor. */
function setGlossIoState(text) {
  const node = el("glossIoState");
  if (node) node.textContent = text || "";
}

function refreshGlossExportLink(slug) {
  const link = el("glossExportBtn");
  if (!link) return;
  link.href = `/api/book/${encodeURIComponent(slug)}/glossary/export`;
}

el("glossImportBtn")?.addEventListener("click", () => el("glossImportFile")?.click());

el("glossImportFile")?.addEventListener("change", async (e) => {
  const dosya = e.target.files && e.target.files[0];
  e.target.value = ""; // aynı dosya ikinci kez seçilebilsin
  if (!dosya || !currentBookSlug) return;
  setGlossIoState("Okunuyor…");
  let terms;
  try {
    const veri = JSON.parse(await dosya.text());
    terms = veri && typeof veri === "object" ? veri.terms || veri : null;
    if (!terms || typeof terms !== "object") throw new Error("terms alanı yok");
  } catch (err) {
    return setGlossIoState("Dosya okunamadı (" + err.message + ").");
  }
  const ezsin = !!el("glossImportOverwrite")?.checked;
  setGlossIoState("Yükleniyor…");
  try {
    const res = await fetch(
      `/api/book/${encodeURIComponent(currentBookSlug)}/glossary/import`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ terms, strateji: ezsin ? "dosya" : "mevcut" }),
      }
    );
    if (!res.ok) throw new Error("sunucu " + res.status);
    const veri = await res.json();
    setGlossIoState(
      `${veri.gelen} terimden ${veri.eklenen} tanesi yazıldı` +
        (ezsin ? "." : " (mevcut kayıtlar korundu).")
    );
    renderGlossary(await fetchGlossary(currentBookSlug));
  } catch (err) {
    setGlossIoState("Yüklenemedi (" + err.message + ") — sunucu açıkken tekrar dene.");
  }
});

/* Terim düzeltildikten SONRA: "bu terim çevrilmiş N bölümde geçiyor".
   Ekranın ipucu satırı "eski bölüm için Yeniden çevir" diyordu ama HANGİ
   bölümler olduğunu söylemiyordu; kullanıcı elle aramak zorundaydı. */
async function gosterTerimEtkisi(row, source) {
  if (!currentBookSlug) return;
  let satir = row.nextElementSibling;
  if (!satir || !satir.classList.contains("gloss-impact")) {
    satir = document.createElement("p");
    satir.className = "gloss-impact";
    row.after(satir);
  }
  satir.textContent = "Etkilenen bölümler aranıyor…";
  try {
    const res = await fetch(
      `/api/book/${encodeURIComponent(currentBookSlug)}/glossary/impact` +
        `?source=${encodeURIComponent(source)}`
    );
    if (!res.ok) throw new Error("sunucu " + res.status);
    const veri = await res.json();
    const [kapsanan, toplam] = veri.kapsama || [0, 0];
    satir.textContent = veri.count
      ? `Bu terim çevrilmiş ${veri.count} bölümde geçiyor — düzeltmenin oralarda ` +
        `görünmesi için o bölümlerde "Yeniden çevir" gerekir.`
      : kapsanan < toplam
        ? `Çevrilmiş bölümlerde bulunamadı (yalnız ${kapsanan}/${toplam} bölümün ` +
          `kaynak metni saklı — kesin değil).`
        : "Çevrilmiş hiçbir bölümde geçmiyor; yalnız yeni bölümleri etkiler.";
  } catch {
    satir.remove(); // sunucu kapalı: sessizce vazgeç, düzenleme zaten kuyrukta
  }
}

/* Arama ve süzgeç YEREL: sunucuya istek atmaz, tazeleme yapmaz — yalnız hâlihazırda
   çizili listeyi yeniden süzer. Sunucudan tazelemek çevrimdışıyken listeyi
   boşaltırdı (bekleyen kayıtlar `overlayGloss` üzerinden geliyor). */
function yenidenSuz() {
  if (!currentBookSlug || views.glossary.hidden) return;
  renderGlossary(overlayGloss(currentBookSlug, glossTermsSonHal));
}
el("glossSearch")?.addEventListener("input", (e) => {
  glossQuery = e.target.value.trim();
  yenidenSuz();
});
for (const btn of document.querySelectorAll("[data-gloss-filter]")) {
  btn.addEventListener("click", () => {
    glossFilter = btn.getAttribute("data-gloss-filter");
    markSegment("glossFilter", glossFilter, "data-gloss-filter");
    yenidenSuz();
  });
}
// Telefonda klavyeden çıkmadan ekleme: iki alanda da Enter = Ekle.
for (const id of ["glossSource", "glossTarget"]) {
  el(id).addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addGlossTerm();
    }
  });
}

// Bağlantı dönünce bekleyen sözlük düzenlemeleri kendiliğinden gitsin; sözlük
// ekranı açıksa liste tazelensin.
window.addEventListener("online", async () => {
  if (!(await flushGlossQueue())) return;
  if (currentBookSlug && !views.glossary.hidden) {
    renderGlossary(await fetchGlossary(currentBookSlug));
  } else {
    updateGlossPendingNote();
  }
});

el("chapterSearch").addEventListener("input", applyChapterFilter);

/* ---------- olaylar: ayarlar (segmented + stepper) ---------- */
document.querySelectorAll("[data-theme-opt]").forEach((b) =>
  b.addEventListener("click", () => setTheme(b.getAttribute("data-theme-opt")))
);
document.querySelectorAll("[data-lh]").forEach((b) =>
  b.addEventListener("click", () => {
    settings.lineHeight = b.getAttribute("data-lh");
    saveSettings();
    applySettings();
    updateSettingsUI();
  })
);
document.querySelectorAll("[data-mg]").forEach((b) =>
  b.addEventListener("click", () => {
    settings.margin = b.getAttribute("data-mg");
    saveSettings();
    applySettings();
    updateSettingsUI();
  })
);
// Sonsuz okuma aç/kapa: açıkken bölüm sonunda sonraki kendiliğinden eklenir, kapalıyken
// akış tek bölümde durur ve "SONRAKİ BÖLÜM →" düğmesiyle devam edilir. Anahtar okuyucu
// açıkken de çevrilebilir → akışın sonu (gözlemci + bitiş kartı) hemen yeniden kurulur.
document.querySelectorAll("[data-inf]").forEach((b) =>
  b.addEventListener("click", () => {
    settings.infinite = b.getAttribute("data-inf") === "1";
    saveSettings();
    updateSettingsUI();
    refreshStreamEnd();
  })
);
/* ---------- çeviri modeli seçimi ---------- */
/* Ayar SUNUCUDA durur (`/api/settings/model`), okuyucunun localStorage'ında değil.
   Üç sebep: çeviriyi sunucu yapıyor · telefon ve PC aynı seçimi görmeli · okumanın
   gövdesi PREFETCH'ten ve toplu çeviriden geliyor, onlar istemci olmadan koşuyor ve
   istemci-taraflı bir ayarı okuyamazlardı. */
let modelSecenekleri = [];

function cizModelSecim(secili) {
  const kutu = el("modelSecim");
  if (!kutu) return;
  kutu.innerHTML = "";
  for (const m of modelSecenekleri) {
    const b = document.createElement("button");
    b.className = "seg";
    b.dataset.model = m.ad;
    b.textContent = m.etiket;
    b.title = m.not || m.ad;
    b.setAttribute("aria-pressed", m.ad === secili ? "true" : "false");
    kutu.appendChild(b);
  }
  const notu = el("modelNotu");
  if (notu) {
    const bulunan = modelSecenekleri.find((m) => m.ad === secili);
    /* Ölçüm notu görünür duruyor: kullanıcı seçerken neyin bedelini ödediğini
       bilmeli (3.7/3.8 uzun bölümleri reddedip dakikalar yakabiliyor, Claude
       halkaları ise PARA harcıyor). */
    notu.textContent = bulunan ? bulunan.not : "";
    notu.classList.toggle("model-ucretli", !!(bulunan && bulunan.ucretli));
  }
}

/* Harcama GÖSTERGESİ — fren değil (kullanıcı kararı). Sürpriz harcamanın kaynağı
   zaten yapısal olarak kapalı: ücretli model elle seçiliyor ve ücretsiz zincir asla
   ücretliye inmiyor. Gösterge "bu gidişle ne olur" sorusunu cevaplamak için var,
   o yüzden pencere AYLIK (fatura da öyle okunuyor). */
function cizHarcama(harcama) {
  const satir = el("modelHarcama");
  if (!satir) return;
  if (!harcama || !harcama.istek) {
    satir.hidden = true;
    return;
  }
  const dokum = harcama.modeller
    .map((m) => `${m.model.replace(/^claude-/, "")} ${m.istek}`)
    .join(" · ");
  satir.hidden = false;
  satir.textContent =
    `Bu ay ücretli çeviri: ${harcama.istek} bölüm ≈ ` +
    `$${harcama.maliyet.toFixed(2)} (${dokum})`;
}

async function loadModelSecim() {
  const kutu = el("modelSecim");
  if (!kutu) return;
  try {
    const res = await fetch("/api/settings/model");
    if (!res.ok) throw new Error(`sunucu ${res.status}`);
    const data = await res.json();
    modelSecenekleri = data.secenekler || [];
    cizModelSecim(data.secili);
    cizHarcama(data.harcama);
  } catch {
    kutu.innerHTML = "";
    const notu = el("modelNotu");
    if (notu) notu.textContent = "Sunucuya ulaşılamadı — model seçimi okunamadı.";
  }
}

el("modelSecim").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-model]");
  if (!b || b.getAttribute("aria-pressed") === "true") return;
  const onceki = modelSecenekleri.find(
    (m) => el("modelSecim").querySelector(`[data-model="${m.ad}"]`)
             ?.getAttribute("aria-pressed") === "true",
  );
  cizModelSecim(b.dataset.model); // iyimser: dokunuş anında geri bildirim
  try {
    const res = await fetch("/api/settings/model", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: b.dataset.model }),
    });
    if (!res.ok) throw new Error(`sunucu ${res.status}`);
    const data = await res.json();
    cizModelSecim(data.secili);
    /* Sözlükle AYNI kural: yalnız yeni çevrilen bölümde geçerli.
       Söylenmezse kullanıcı açık duran bölümün değişmesini bekler ve "çalışmadı"
       sanır. */
    setStatus("Model seçildi — yeni çevrilen bölümlerde geçerli.");
  } catch {
    if (onceki) cizModelSecim(onceki.ad); // yazılamadı: gerçeğe geri dön
    setStatus("Model kaydedilemedi — sunucuya ulaşılamadı.");
  }
});

el("settingsBtn").addEventListener("click", () => {
  el("settingsPanel").hidden = !el("settingsPanel").hidden;
  if (!el("settingsPanel").hidden) {
    showShellVersion();
    loadModelSecim();
  }
});

/* ---------- kabuk sürümü + sıfırlama (bayat kabuk kaçış kapısı) ---------- */
const KABUK_ONEK = "novellink-shell-";
const VERI_ONBELLEK = "novellink-data";

/* Sunucunun ŞU ANKİ kabuk sürümü — `sw.js` HTTP önbelleği ATLANARAK okunur ve
   içindeki SHELL_CACHE çıkarılır.

   Neden ikinci bir sürüm sabiti tutmuyoruz: app.js'e ayrı bir sabit koysaydık
   sw.js ile birlikte bumplanmayı unutmak sürüm bilgisinin KENDİSİNİ bayatlatırdı
   (yanlış "güncel" yazan bir gösterge, göstergesizlikten kötüdür). Tek kaynak
   sw.js.

   ZAMAN AŞIMI ŞART (ölçülen vaka, ts.net üzerinden telefon): Tailscale tökezlediğinde
   bu adrese giden istek HATA VERMEZ, dakikalarca askıda kalır — `sw.js` içindeki
   `fetchWithTimeout` de tam olarak bu "kara delik" yüzünden var. Zaman aşımı olmadan
   aşağıdaki `await` hiç dönmüyor ve sürüm satırı BOŞ kalıyordu; kullanıcı da
   sıfırlamanın işe yarayıp yaramadığını göremiyordu ("sıfırla düzgün çalışmıyor,
   anlamadım"). Boş bir gösterge, göstergesizlikten kötüdür. */
async function sunucuKabukSurumu(ms = 4000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch("/sw.js", { cache: "no-store", signal: ctrl.signal });
    const m = (await res.text()).match(/SHELL_CACHE\s*=\s*"([^"]+)"/);
    return m ? m[1] : null;
  } finally {
    clearTimeout(timer);
  }
}

/* Sunucuya ulaşmayı BİRDEN ÇOK KEZ dener; "ulaşıldı mı" ile "sürüm okunabildi mi"
   sorularını AYIRIR.

   Ölçülen kök neden (2026-09-06, kullanıcı bildirimi "sunucuya bağlanmıyor"):
   sunucu, `tailscale serve` proxy'si ve tünelin üçü de SAĞLAMDI — PC'den
   `https://<makine>.ts.net/api/books` 200 dönüyordu. Arıza telefonun ilk
   isteğindeydi: Android'de Tailscale boştayken düşük güç durumuna geçiyor ve
   tünel ilk pakette hazır olmuyor. Ölçüm: PC'den atılan `tailscale ping`in
   İLKİ zaman aşımına uğradı, İKİNCİSİ 38 ms'de döndü (doğrudan LAN yolu).
   Tek atışlık 4 sn'lik kontrol bu UYANMA ANINI "sunucu kapalı" diye okuyup
   sıfırlamayı reddediyordu. Başarısız ilk istek tünelin uyanmasını ZATEN
   tetiklediği için ikinci deneme çoğunlukla tutar.

   İkinci bir arıza da burada kapanıyor: eski kontrol `sunucuKabukSurumu()`nün
   `null` dönmesini "ulaşılamadı" sayıyordu, oysa `null` "sunucuya ULAŞILDI ama
   sürüm deseni eşleşmedi" demek. Sunucu ayaktayken bile sıfırlamayı reddedecek
   bir yoldu. Artık ağ hatası (throw) ile desen eşleşmemesi (null) ayrı. */
async function sunucuyaUlas(denemeler = 3, ms = 4000) {
  for (let i = 0; i < denemeler; i++) {
    try {
      return { ulasildi: true, surum: await sunucuKabukSurumu(ms) };
    } catch {
      // Son denemede bekleme: kullanıcıyı boşuna oyalamaz.
      if (i < denemeler - 1) await new Promise((r) => setTimeout(r, 700));
    }
  }
  return { ulasildi: false, surum: null };
}

/* Panel her açılışta GERÇEK durumu okur ve TELEFONDAKİ ile SUNUCUDAKİNİ KIYASLAR.
   Eskiden yalnız telefondaki sürüm yazıyordu; "v68" görmek güncel mi bayat mı
   olduğunu söylemiyordu, yani sıfırlamanın işe yarayıp yaramadığı doğrulanamıyordu
   (kullanıcı bildirimi: "tam sıfırlamıyor gibi"). */
async function showShellVersion() {
  const out = el("shellVersion");
  if (!out) return;
  out.classList.remove("shell-ver-stale");
  if (!("caches" in window)) {
    out.textContent = "(önbellek yok — hep ağdan)";
    return;
  }
  let telefonda;
  try {
    telefonda = (await caches.keys()).filter((k) => k.startsWith(KABUK_ONEK));
  } catch (err) {
    // Sessiz boşaltma YASAK: satırın boş kalması, kullanıcıya sıfırlamanın işe
    // yarayıp yaramadığını göremediği bir ekran bırakıyordu ("anlamadım").
    out.textContent = "(önbellek okunamadı: " + (err?.name || "hata") + ")";
    out.classList.add("shell-ver-stale");
    return;
  }
  const kisa = (k) => k.replace(KABUK_ONEK, "");
  if (!telefonda.length) {
    out.textContent = "(kurulmadı)";
    return;
  }
  // Birden çok kabuk önbelleği = önceki güncelleme YARIM kalmış. Tek başına bir
  // bulgudur: activate'in temizliği koşmamış demektir.
  if (telefonda.length > 1) {
    out.textContent = telefonda.map(kisa).join(" + ") + " — karışık, sıfırla";
    out.classList.add("shell-ver-stale");
    return;
  }
  const bu = kisa(telefonda[0]);
  // Yerel sürümü HEMEN yaz. Aşağıdaki sunucu kıyası askıda kalırsa (Tailscale kara
  // deliği) bu satıra hiç dönülmüyordu ve gösterge BOŞ kalıyordu — asıl şikâyetin
  // kaynağı buydu. Kıyas sonuçlanırsa üzerine yazılır.
  out.textContent = bu;
  // Gösterge için İKİ deneme yeter: burada bekleme kullanıcıyı oyalar ve panel
  // zaten yeniden açılabilir. Sıfırlama düğmesi (yıkıcı işlem) üç deneme yapar.
  const { ulasildi, surum: sunucuda } = await sunucuyaUlas(2);
  if (!ulasildi) {
    // "güncel" demek YANLIŞ olurdu; sürümü yaz ve ulaşılamadığını SÖYLE — sıfırlama
    // bu hâldeyken kabuğu silip yerine yenisini indiremeyeceği için tehlikelidir.
    out.textContent = bu + " · sunucuya ulaşılamıyor";
    out.classList.add("shell-ver-stale");
    return;
  }
  if (!sunucuda) {
    out.textContent = bu;
    return;
  }
  const o = kisa(sunucuda);
  out.textContent = bu === o ? bu + " · güncel" : bu + " -> sunucuda " + o + ", sıfırla";
  if (bu !== o) out.classList.add("shell-ver-stale");
}

el("shellReset")?.addEventListener("click", async () => {
  const btn = el("shellReset");
  btn.disabled = true;
  btn.textContent = "Sıfırlanıyor…";
  /* SUNUCU ERİŞİMİ ÖN KOŞUL. Sıfırlama kabuk önbelleğini SİLİP service worker'ı
     kaldırıyor; yerine yenisini ancak ağdan indirebilir. Sunucuya ulaşılamıyorken
     basılırsa uygulama telefonda tümden açılmaz hâle gelir (indirilen bölümler
     `novellink-data`da durur ama onlara ulaşacak kabuk kalmaz). Bu, kullanıcının
     "bir şey çalışmıyor" diye bastığı anda tam olarak gerçekleşebilecek senaryodur —
     Tailscale koptuğunda uygulama önbellekten açılmaya devam ettiği için ağın
     gittiği fark edilmiyor. */
  try {
    // ÜÇ deneme: bu yıkıcı bir işlem ve yanlış bir "ulaşılamıyor" kullanıcıyı
    // sunucu sapasağlamken kilitliyor (ölçülen vaka). Tünelin uyanması için
    // birkaç saniye beklemek, hatalı reddin bedelinden ucuz.
    btn.textContent = "Sunucu deneniyor…";
    if (!(await sunucuyaUlas(3)).ulasildi) {
      btn.textContent = "Sunucuya ulaşılamıyor";
      alert(
        "Sunucuya ulaşılamıyor, bu yüzden sıfırlama yapılmadı.\n\n" +
        "Sıfırlama uygulama kabuğunu siler ve yerine yenisini sunucudan indirir; " +
        "şu an indiremeyeceği için uygulama açılmaz hâle gelirdi.\n\n" +
        "Üç kez denendi. Telefon uykudaysa Tailscale'in tüneli ilk isteklerde " +
        "hazır olmayabilir: Tailscale uygulamasını bir açıp kapatın, sonra " +
        "tekrar deneyin. PC'deki sunucunun da açık olduğundan emin olun."
      );
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = "Sıfırla";
      }, 2500);
      return;
    }
  } catch {}
  try {
    if ("serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if ("caches" in window) {
      const keys = await caches.keys();
      // İndirilen bölümler (novellink-data) KORUNUR; yalnız kabuk önbellekleri silinir.
      await Promise.all(
        keys.filter((k) => k !== VERI_ONBELLEK).map((k) => caches.delete(k))
      );
    }
  } catch {}
  /* Düz `location.reload()` YETMİYOR: `unregister()` kaydı siler ama açık sayfa
     UNLOAD olana kadar hâlâ eski service worker tarafından KONTROL EDİLİYOR, yani
     reload navigasyonu onun fetch handler'ından geçebiliyor. Benzersiz sorgulu bir
     navigasyon hem onu hem HTTP önbelleğini kesin olarak atlar. Parametre açılışta
     temizlenir (adres çubuğunda kalmasın) — bkz. aşağıdaki temizleyici. */
  location.replace(location.pathname + "?kabuk=" + Date.now());
});
el("fontMinus").addEventListener("click", () => {
  settings.fontPx = Math.max(14, settings.fontPx - 1);
  saveSettings();
  applySettings();
  updateSettingsUI();
});
el("fontPlus").addEventListener("click", () => {
  settings.fontPx = Math.min(30, settings.fontPx + 1);
  saveSettings();
  applySettings();
  updateSettingsUI();
});
el("fontFamily").addEventListener("click", () => {
  settings.font = settings.font === "sans" ? "serif" : "sans";
  saveSettings();
  applySettings();
  updateSettingsUI();
});
// Ayarlar → "Bu bölüm — Yeniden çevir": AKTİF bölümü yerinde yeniden çevirir
// (akışı sıfırlamaz — dikişler korunur).
el("retranslate").addEventListener("click", () => {
  if (isNavigating) return;
  const e = activeEntry();
  if (e) retranslateChapter(e);
});

/* ---------- olaylar: okuyucu ---------- */
// Sonsuz okuma v2: gezinme = kaydırma. Alt çubuk nav düğmeleri (SONRAKI/ÖNCEKİ) ve
// yatay swipe kaldırıldı — sonraki bölüm akışa otomatik eklenir (gözlemci), önceki
// akış başındaki kartla eklenir. Footer gizli (D-B9v2).
el("readerBody").addEventListener("click", onParaTap); // çift-tık → İngilizce orijinal
el("findBtn").addEventListener("click", () => {
  if (el("findBar").hidden) openFind();
  else closeFind();
});
el("findInput").addEventListener("input", () => {
  clearTimeout(findTimer);
  findTimer = setTimeout(runFind, 150);
});
el("findInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    cycleFind(e.shiftKey ? -1 : 1);
  } else if (e.key === "Escape") {
    closeFind();
  }
});
el("findNext").addEventListener("click", () => cycleFind(1));
el("findPrev").addEventListener("click", () => cycleFind(-1));
el("findClose").addEventListener("click", closeFind);

/* ---------- kaydırma konumu dinleyicileri ---------- */
window.addEventListener("scroll", onReaderScroll, { passive: true });
window.addEventListener("pagehide", persistScroll);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") persistScroll();
});

/* ---------- toplu çeviri (sunucu-taraflı arka plan iş) ---------- */
// Kullanıcının "Arka Plana Al" dediği iş: ilerleme ekranı bir daha kendiliğinden
// açılmaz (discoverBulkJob buna bakar). TOPLU ÇEVİR düğmesi yeniden açabilir.
let bulkDismissedJobId = null;
// Ekranın ŞU AN hangi işi gösterdiği. Uçuştaki eski bir anket yanıtı (iş A),
// araya yeni iş (B) girdiyse B'nin ilerlemesini ezmesin diye her await sonrası
// bu belirteçle doğrulanır.
let bulkActiveJobId = null;
let bulkDoneTimer = null;

function hideBulkToBackground(jobId) {
  bulkDismissedJobId = jobId;
  bulkActiveJobId = null;
  clearTimeout(bulkPollTimer);
  clearTimeout(bulkDoneTimer);
  el("bulkProgress").hidden = true;
}

el("bulkBtn").addEventListener("click", async () => {
  // QA bulgusu: arka plana alınmış iş varken bu düğme başlatma modalını açıyordu.
  // Çalışan iş varsa doğrudan ilerleme/durdurma ekranı açılır (geri çağırma yolu).
  const job = currentBookSlug ? await fetchBookJob(currentBookSlug) : null;
  if (job && job.state === "running") {
    bulkDismissedJobId = null; // kullanıcı ekranı bilerek geri açtı
    openBulkProgress(job);
    return;
  }
  el("bulkCount").value = "10";
  el("bulkModal").hidden = false;
});
el("bulkCancel").addEventListener("click", () => {
  el("bulkModal").hidden = true;
});

el("bulkStart").addEventListener("click", () => {
  const n = Math.max(1, Math.min(500, parseInt(el("bulkCount").value, 10) || 0));
  el("bulkModal").hidden = true;
  startBulk(n);
});

async function startBulk(count) {
  // QA bulgusu: iş KALDIĞIN yerden değil, kitabın EN SON ÇEVRİLMİŞ bölümünden
  // ileriye başlamalı (okuma konumu geride olabilir; çevrili aralığı yeniden
  // gezmek kafa karıştırıyordu). Son çevrili bölüm start alınır — önbellekte
  // olduğu için iş onu API harcamadan atlar ve sonrasına geçer. Hiç çevrili
  // bölüm yoksa okuma konumuna düşülür (yeni kitap).
  let url = null;
  const chapters =
    currentChapters && currentChapters.length
      ? currentChapters
      : await chaptersOf(currentBookSlug);
  if (chapters.length) {
    const last = chapters.reduce((a, b) =>
      (b.chapter_no || 0) > (a.chapter_no || 0) ? b : a
    );
    url = last.url;
  } else {
    const book =
      currentBook ||
      ((await fetchBooks()) || []).find((b) => b.slug === currentBookSlug);
    url = book ? book.current_url : null;
  }
  if (!url) return;

  el("bulkProgressText").textContent = "Başlatılıyor…";
  el("bulkStop").disabled = false;
  el("bulkProgress").hidden = false;

  let jobId;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(currentBookSlug)}/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_url: url, count }),
    });
    const data = await res.json();
    jobId = data.job_id;
  } catch (e) {
    el("bulkProgressText").textContent = "Başlatılamadı: " + e.message;
    return;
  }
  bulkDismissedJobId = null; // kullanıcı ekranı bilerek açtı
  el("bulkStop").onclick = () => {
    fetch(`/api/bulk/${jobId}/stop`, { method: "POST" }).catch(() => {});
  };
  el("bulkHide").onclick = () => hideBulkToBackground(jobId);
  pollBulk(jobId);
}

// Var olan işin ilerleme/durdurma ekranını aç ve anketini başlat.
function openBulkProgress(job) {
  el("bulkProgressText").textContent = job.message || "Hazırlanıyor…";
  el("bulkStop").disabled = false;
  el("bulkProgress").hidden = false;
  el("bulkStop").onclick = () => {
    fetch(`/api/bulk/${job.id}/stop`, { method: "POST" }).catch(() => {});
  };
  el("bulkHide").onclick = () => hideBulkToBackground(job.id);
  pollBulk(job.id);
}

async function discoverBulkJob(slug) {
  const job = await fetchBookJob(slug);
  if (!job || job.state !== "running" || slug !== currentBookSlug || views.book.hidden) return;
  if (job.id === bulkDismissedJobId) return; // arka plana atıldı, kendiliğinden açılma
  openBulkProgress(job);
}

function pollBulk(jobId) {
  clearTimeout(bulkPollTimer);
  clearTimeout(bulkDoneTimer);
  bulkActiveJobId = jobId;
  // Ekran kapandıysa VEYA ekran artık başka bir işi gösteriyorsa bu anket ölür.
  // Görünürlük tek başına yetmez: A işinin uçuştaki yanıtı, araya giren B işinin
  // açık ekranını "görünür" bulup B'nin ilerlemesini ezebilirdi.
  const stale = () => el("bulkProgress").hidden || bulkActiveJobId !== jobId;
  const tick = async () => {
    if (stale()) return;
    let s;
    try {
      const r = await fetch(`/api/bulk/${jobId}`);
      s = await r.json();
    } catch {
      if (stale()) return;
      bulkPollTimer = setTimeout(tick, 2000);
      return;
    }
    if (stale()) return;
    el("bulkProgressText").textContent = s.message || "…";
    if (s.state === "running") {
      bulkPollTimer = setTimeout(tick, 1500);
    } else {
      el("bulkStop").disabled = true;
      // Bitiş geri çağrısı sahipli: 2.5 sn içinde kullanıcı ekranı kapatır,
      // başka iş açar veya başka görünüme geçerse ekranla oynamaz, gezinmeyi
      // gasp etmez (openBook yalnız hâlâ o kitabın sayfası açıksa çalışır).
      const jobSlug = currentBookSlug;
      bulkDoneTimer = setTimeout(() => {
        if (stale()) return;
        el("bulkProgress").hidden = true;
        bulkActiveJobId = null;
        if (jobSlug && jobSlug === currentBookSlug && !views.book.hidden) {
          openBook(jobSlug);
        }
        // Ekrandan BAGIMSIZ: `openBook` yalnizca hala o kitabin sayfasindaysan
        // calisiyor, oysa toplu is coguzaman kullanici baska yerdeyken bitiyor —
        // tam da bolumlerin telefona hic inmedigi durum.
        otoIndirmeTur();
      }, 2500);
    }
  };
  tick();
}

el("clearanceRefresh")?.addEventListener("click", async () => {
  const btn = el("clearanceRefresh");
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Yenileniyor…";
  try {
    const res = await fetch("/api/clearance/refresh", { method: "POST" });
    if (!res.ok) throw new Error();
    btn.textContent = "Yenilendi ✓";
  } catch {
    btn.textContent = "Yenilenemedi";
  }
  setTimeout(() => {
    btn.textContent = old;
    btn.disabled = false;
  }, 2500);
});

/* ---------- çevrimdışı indir ---------- */
el("offlineBtn")?.addEventListener("click", () => {
  if (currentBookSlug) runOfflineDownload([currentBookSlug]);
});
el("offlineAllBtn")?.addEventListener("click", startOfflineDownloadAll);
el("offlineStop")?.addEventListener("click", () => {
  offlineStop = true;
});

async function chaptersOf(slug) {
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/chapters`);
    const data = await res.json();
    return data.chapters || [];
  } catch {
    return [];
  }
}

async function startOfflineDownloadAll() {
  const books = await fetchBooks();
  if (books.length === 0) return;
  await runOfflineDownload(books.map((b) => b.slug));
}

async function runOfflineDownload(slugs) {
  const groups = [];
  let total = 0;
  for (const slug of slugs) {
    // Cevirisi olmayan bolum ELENIR: "cevrimdisi indir" indirmedir, cevirtme
    // degil — GET'lemek ceviri tetikler ve ucretli modelde para harcardi.
    const chs = (await chaptersOf(slug)).filter((c) => c.translated !== false);
    groups.push(chs);
    total += chs.length;
  }

  el("offlineProgress").hidden = false;
  if (total === 0) {
    el("offlineStop").disabled = true;
    el("offlineProgressText").textContent = "İndirilecek çevrilmiş bölüm yok.";
    setTimeout(() => {
      el("offlineProgress").hidden = true;
      el("offlineStop").disabled = false;
    }, 1800);
    return;
  }

  offlineStop = false;
  el("offlineStop").disabled = false;
  el("offlineProgressText").textContent = "Hazırlanıyor…";

  let done = 0;
  let failed = 0;
  outer: for (const chs of groups) {
    for (const ch of chs) {
      if (offlineStop) break outer;
      el("offlineProgressText").textContent = `${done + failed + 1} / ${total} indiriliyor…`;
      try {
        const r = await fetch(`/api/chapter?url=${encodeURIComponent(ch.url)}`);
        if (r.ok) done++;
        else failed++;
      } catch {
        failed++;
      }
    }
  }

  const tail = failed ? ` (${failed} başarısız)` : "";
  el("offlineProgressText").textContent = offlineStop
    ? `Durduruldu. ${done}/${total} bölüm telefonda.`
    : `Bitti — ${done}/${total} bölüm telefonda${tail}.`;
  el("offlineStop").disabled = true;
  setTimeout(() => {
    el("offlineProgress").hidden = true;
    el("offlineStop").disabled = false;
  }, 2200);
}

/* ---------- kitap birleştir ---------- */
el("mergeBtn")?.addEventListener("click", openMergeModal);
el("deleteBookBtn")?.addEventListener("click", deleteCurrentBook);

/* ---------- bu kitaba bölüm ekle (metin yapıştır / web adresinden çek) ---------- */
let chAddTab = "paste";
el("addChapterBtn")?.addEventListener("click", openChapterAddModal);
el("chAddCancel")?.addEventListener("click", () => (el("chapterAddModal").hidden = true));
el("chapterAddModal")?.addEventListener("click", (e) => {
  if (e.target === el("chapterAddModal")) el("chapterAddModal").hidden = true;
});
document.querySelectorAll("#chapterAddModal .seg[data-chadd-tab]").forEach((b) =>
  b.addEventListener("click", () => setChAddTab(b.dataset.chaddTab))
);
el("chAddConfirm")?.addEventListener("click", submitChapterAdd);

function setChAddTab(tab) {
  chAddTab = tab;
  document.querySelectorAll("#chapterAddModal .seg[data-chadd-tab]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.chaddTab === tab))
  );
  el("chAddPaste").hidden = tab !== "paste";
  el("chAddUrl").hidden = tab !== "url";
}

function openChapterAddModal() {
  if (!currentBookSlug) return;
  const synth = isSyntheticSlug(currentBookSlug);
  // Sentetik (içe aktarılan) kitapta metin URL'siz eklenir; web kitabında bölümün
  // gerçek adresi gerekir (o adrese kaydedilir → kitap web-yerli kalır).
  el("chAddPasteUrl").hidden = synth;
  el("chAddPasteHint").textContent = synth
    ? "Bu içe aktarılan kitaba yeni bölüm eklenir (sıradaki numara)."
    : "Takılan/eksik bir bölümün metnini, o bölümün web adresiyle yapıştır. Kitap web bağlantısını korur.";
  ["chAddPasteUrl", "chAddTitle", "chAddText", "chAddFetchUrl"].forEach((id) => (el(id).value = ""));
  setChAddTab("paste");
  el("chapterAddModal").hidden = false;
}

async function submitChapterAdd() {
  if (!currentBookSlug) return;
  const btn = el("chAddConfirm");
  const synth = isSyntheticSlug(currentBookSlug);
  let endpoint, body, slow = false;
  if (chAddTab === "url") {
    const url = el("chAddFetchUrl").value.trim();
    if (!/^https?:\/\//.test(url)) return el("chAddFetchUrl").focus();
    endpoint = `/api/book/${encodeURIComponent(currentBookSlug)}/fetch-next`;
    body = { url };
    slow = true; // çekme + çeviri sürebilir
  } else {
    const text = el("chAddText").value.trim();
    if (!text) return el("chAddText").focus();
    const title = el("chAddTitle").value.trim() || null;
    if (synth) {
      endpoint = "/api/import/paste";
      body = { slug: currentBookSlug, text, title: title || "Bölüm" };
    } else {
      const url = el("chAddPasteUrl").value.trim();
      if (!/^https?:\/\//.test(url)) {
        el("chAddPasteUrl").focus();
        return alert("Bu bölümün web adresini (URL) gir.");
      }
      endpoint = "/api/import/paste-url";
      body = { url, slug: currentBookSlug, text, title };
    }
  }
  btn.disabled = true;
  const orig = btn.textContent;
  if (slow) btn.textContent = "Çekiliyor…";
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail?.message || err.detail || "Ekleme başarısız.");
    }
    el("chapterAddModal").hidden = true;
    openBook(currentBookSlug); // liste yenilensin, yeni bölüm görünsün
  } catch (e) {
    alert(String(e.message || e));
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

// Kitabı + tüm bölümlerini kalıcı sil. Boş/mükerrer kitapları raftan kaldırır
// (sentetik kitaplar merge edilemez ama silinebilir). Onay ister, geri alınamaz.
async function deleteCurrentBook() {
  if (!currentBookSlug) return;
  const name = (currentBook && currentBook.title) || currentBookSlug;
  const n = currentChapters ? currentChapters.length : 0;
  const detail = n ? `\n${n} bölüm ve sözlüğü de silinir.` : "";
  if (!confirm(`"${name}" kitabı kalıcı olarak silinsin mi?${detail}\nBu işlem geri alınamaz.`)) return;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(currentBookSlug)}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error();
    history.back(); // silinen kitap görünümünden bir üste (kütüphane) dön — geçmişi büyütme
  } catch {
    alert("Silme başarısız — sunucuya ulaşılamadı.");
  }
}
el("mergeCancel")?.addEventListener("click", () => {
  el("mergeModal").hidden = true;
});
el("mergeModal")?.addEventListener("click", (e) => {
  if (e.target === el("mergeModal")) el("mergeModal").hidden = true;
});

async function openMergeModal() {
  if (!currentBookSlug) return;
  const books = (await fetchBooks()).filter((b) => b.slug !== currentBookSlug);
  const list = el("mergeList");
  list.replaceChildren();
  if (books.length === 0) {
    const p = document.createElement("p");
    p.className = "loading-row";
    p.textContent = "Birleştirilecek başka kitap yok.";
    list.appendChild(p);
  } else {
    for (const book of books) {
      const row = document.createElement("button");
      row.className = "merge-row";
      row.textContent = book.title;
      row.addEventListener("click", () => confirmMerge(book));
      list.appendChild(row);
    }
  }
  el("mergeModal").hidden = false;
}

async function confirmMerge(target) {
  const ok = window.confirm(
    `Bu kitap "${target.title}" ile birleştirilsin mi?\n` +
      "Bölümleri ve sözlüğü ona taşınacak; bu kitap listeden kalkacak."
  );
  if (!ok) return;
  const source = currentBookSlug;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(source)}/merge-into`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: target.slug }),
    });
    const data = await res.json();
    el("mergeModal").hidden = true;
    currentBookSlug = data.canonical || target.slug;
    // Mevcut book kaydını kanonik slug'la güncelle (birleşmeyle eski slug kaybolabilir).
    history.replaceState({ view: "book", slug: currentBookSlug }, "");
    openBook(currentBookSlug);
  } catch {
    el("mergeModal").hidden = true;
  }
}

/* ---------- ePub ---------- */
el("epubBtn").addEventListener("click", () => {
  el("epubModal").hidden = false;
});
el("epubCancel").addEventListener("click", () => {
  el("epubModal").hidden = true;
});
el("epubDownload").addEventListener("click", () => {
  if (!currentBookSlug) return;
  const start = Math.max(1, parseInt(el("epubStart").value, 10) || 1);
  const count = Math.max(1, Math.min(2000, parseInt(el("epubCount").value, 10) || 1));
  el("epubModal").hidden = true;
  const url =
    `/api/book/${encodeURIComponent(currentBookSlug)}/epub?start=${start}&count=${count}`;
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

/* ---------- kitap ekle olayları ---------- */
el("addCancel").addEventListener("click", closeAddModal);
document.querySelectorAll("[data-add-tab]").forEach((b) =>
  b.addEventListener("click", () => setAddTab(b.getAttribute("data-add-tab")))
);
["pasteBookTitle", "pasteChapterTitle", "pasteChapterNo", "pasteText"].forEach((id) =>
  el(id).addEventListener("input", savePasteDraft)
);
el("pasteBookSelect").addEventListener("change", () => {
  // Mevcut kitaba eklerken kitap adı alanı anlamsız — gizle.
  el("pasteBookTitle").hidden = !!el("pasteBookSelect").value;
});
// Manga siteleri (URL bölüm linki → siteden sayfa görselleri çekip Gemini-vision ile
// çevir). Roman siteleri metin akışına gider; manga siteleri resim akışına.
function isMangaUrl(u) {
  return /asurascans?\.com|asuracomic\.net|reaperscans|flamecomics|mangadex\.org/i.test(u || "");
}

async function importMangaUrl(url) {
  const btn = el("addConfirm");
  const orig = btn.innerHTML;
  btn.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span> Manga çekiliyor…`;
  btn.disabled = true;
  try {
    const res = await fetch("/api/import/manga-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      throw new Error(e.detail?.message || e.detail || `Hata (${res.status})`);
    }
    const data = await res.json();
    closeAddModal();
    navigate({ view: "reader", url: data.first_url });
  } catch (err) {
    alert("Manga çekilemedi: " + (err.message || err));
  } finally {
    btn.innerHTML = orig;
    btn.disabled = false;
  }
}

el("addConfirm").addEventListener("click", () => {
  if (addTab === "paste") {
    submitPaste();
    return;
  }
  if (addTab === "dosya") {
    uploadFile();
    return;
  }
  const url = el("addUrlInput").value.trim();
  if (url) {
    if (isMangaUrl(url)) return importMangaUrl(url); // manga sitesi → sayfaları çek+çevir
    closeAddModal();
    navigate({ view: "reader", url });
  }
});
el("addUrlInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") el("addConfirm").click();
});
el("addModal").addEventListener("click", (e) => {
  if (e.target === el("addModal")) closeAddModal();
});

/* ---------- başlangıç ---------- */
applySettings();
updateSettingsUI();
// Kalıcı raf filtresini çiplere yansıt (setShelfFilter çağrılmaz — çift render olmasın).
document.querySelectorAll("#shelfFilters .chip").forEach((c) => {
  c.setAttribute("aria-pressed", String(c.dataset.filter === shelfFilter));
});
// Tarayıcının otomatik scroll restorasyonunu KAPAT (SPA kendi restorasyonunu yapar:
// loadChapter restoreRatio). Aksi halde geri jestinde tarayıcı pencereyi tepeye
// kaydırır, reader HÂLÂ görünürken bir scroll olayı tetiklenir ve updateActiveChapter
// aktif bölümü akışın İLK (en üstteki) bölümüne sıfırlar → konum başladığın bölüme
// geri yazılır ("bir önceki/ilk bölüme dönüyor" bug'ı; sonsuz okuma v2 ile geldi).
if ("scrollRestoration" in history) history.scrollRestoration = "manual";
history.replaceState({ view: "library" }, ""); // kök kayıt: buradan geri = uygulamadan çık

// Statik ikonları SVG ile doldur (emoji yerine; aria-label butonda zaten var).
el("findBtn").innerHTML = ICONS.search;
el("settingsBtn").innerHTML = ICONS.sliders;

/* Alt gezinme: ikonlar + davranış. Sekmeler MEVCUT işlevleri çağırır, yenisini
   uydurmaz — "Çevrimdışı" kütüphanedeki indirme akışının, "Ayarlar" ise
   `settingsBtn`in ta kendisidir (aynı işi iki ayrı kod yolundan yapmak, bu
   projede künye alanlarının ayrıştığı hatanın aynısı olurdu). */
{
  const IKON = { library: ICONS.shelf, offline: ICONS.download, settings: ICONS.sliders };
  for (const tab of document.querySelectorAll(".navtab")) {
    const ad = tab.dataset.tab;
    tab.querySelector(".navtab-icon").innerHTML = IKON[ad] || "";
    tab.addEventListener("click", () => {
      if (ad === "library") {
        el("settingsPanel").hidden = true;
        navigate({ view: "library" });
      } else if (ad === "offline") {
        // İndirme kütüphane ekranının akışı: başka görünümdeysen önce oraya dön,
        // yoksa ilerleme satırı görünmeyen bir ekranda akardı.
        el("settingsPanel").hidden = true;
        if (views.library.hidden) navigate({ view: "library" });
        startOfflineDownloadAll();
      } else if (ad === "settings") {
        el("settingsBtn").click(); // TEK kaynak: panelin kendi aç/kapa mantığı
      }
      senkronlaSekme(views.library.hidden ? "" : "library");
    });
  }
}
el("offlineAllBtn").innerHTML = ICONS.download + " HEPSİNİ ÇEVRİMDIŞI İNDİR";

renderLibrary();
showView("library");

/* ---------- seçimden sözlüğe ekleme ----------
   Okurken bir özel adı seçip doğrudan sözlüğe atmak için. Android'in KENDİ seçim
   menüsüne (Çevir/Kopyala/Paylaş) kendi eylemimizi EKLEYEMEYİZ — o tarayıcının
   menüsü, sayfaya kapalı. Bunun yerine seçim yapılınca kendi kayan düğmemizi
   gösteririz; native menü seçimin üstünde durduğu için düğme ALTA konumlanır. */

// Cümle seçilince düğme çıkmasın: sözlük TERİM eşlemesidir, cümle çevirisi değil.
const SEL_GLOSS_MAX_WORDS = 8;
let selGlossData = null; // aktif seçim (düğme görünürken)
// Düğmeye basılınca kullanılacak SON geçerli seçim. Ayrı tutulur: dokunma anında
// tarayıcı seçimi temizleyip `selectionchange` yayabiliyor, tek değişken olsaydı
// tıklama işlenmeden önce null'lanıp düğme sessizce hiçbir şey yapmazdı.
let selGlossLast = null;
let selGlossTimer = null;

/* `glossary.normalize_source`'un hafif JS eşi: çevresel noktalama kırpılır, İngilizce
   iyelik eki KORUNUR (kullanıcı ne eklediğini görsün, sunucu zaten köke indiriyor).
   Sunucudaki `set_term` normalize ETMEZ — kırpma burada olmazsa sözlükte
   "Silverwing Town." gibi noktalı anahtarlar birikir. */
function trimSecim(text) {
  return (text || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[^\p{L}\p{N}]+/u, "")
    .replace(/[^\p{L}\p{N}'’]+$/u, "");
}

function hideSelGloss() {
  selGlossData = null;
  const btn = el("selGlossBtn");
  if (btn) btn.hidden = true;
}

function updateSelGloss() {
  const btn = el("selGlossBtn");
  if (!btn || views.reader.hidden) return hideSelGloss();
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return hideSelGloss();
  const range = sel.getRangeAt(0);
  const node = range.commonAncestorContainer;
  const host = node.nodeType === 1 ? node : node.parentElement;
  if (!host || !host.closest("#readerBody")) return hideSelGloss();

  const terim = trimSecim(sel.toString());
  if (!terim || terim.split(" ").length > SEL_GLOSS_MAX_WORDS) return hideSelGloss();

  // Sözlük eşlemesi kaynak(İngilizce) → karşılık(Türkçe). Seçimin İngilizce orijinal
  // bloğundan (`.source-line`) mı yoksa Türkçe paragraftan mı geldiği, modalda hangi
  // alanın dolacağını belirler.
  // Bağlam cümlesi öneriye gider: aynı sözcük bir kitapta kişi adı, başkasında yer
  // adı olabilir ("Rain"), sınıfı ancak cümle belli eder.
  selGlossData = {
    terim,
    kaynaktan: !!host.closest(".source-line"),
    baglam: (host.closest(".source-line, p") || host).textContent.slice(0, 600),
  };
  selGlossLast = selGlossData;

  btn.hidden = false; // ölçüden ÖNCE görünür olmalı, yoksa offset* 0 döner
  const yariGenislik = btn.offsetWidth / 2 || 60;
  const r = range.getBoundingClientRect();
  const x = Math.min(
    Math.max(r.left + r.width / 2, yariGenislik + 8),
    window.innerWidth - yariGenislik - 8
  );
  const altta = r.bottom + 8;
  const y =
    altta + btn.offsetHeight + 8 < window.innerHeight
      ? altta
      : r.top - btn.offsetHeight - 8; // ekranın dibinde seçim: üste al
  btn.style.left = x + "px";
  btn.style.top = Math.max(8, y) + "px";
}

function openGlossQuick() {
  const secim = selGlossLast;
  if (!secim) return;
  const { terim, kaynaktan } = secim;
  el("glossQuickSource").value = kaynaktan ? terim : "";
  el("glossQuickTarget").value = kaynaktan ? "" : terim;
  el("glossQuickHint").textContent = kaynaktan
    ? "Karakter adıysa İngilizce kalır, değilse Türkçe karşılığı yazılır. Sözlük YALNIZ bundan sonra çevrilecek bölümlerde geçerlidir."
    : "Türkçe metinden seçtin: bunu KARŞILIK alanına koydum, kaynak İngilizce terimi sen yaz. Sözlük yalnız bundan sonra çevrilecek bölümlerde geçerlidir.";
  el("glossQuickState").textContent = "";
  el("glossQuickModal").hidden = false;
  hideSelGloss();
  window.getSelection()?.removeAllRanges();
  (kaynaktan ? el("glossQuickTarget") : el("glossQuickSource")).focus();
  if (kaynaktan) doldurOneri(secim);
}

/* Karşılığı kullanıcı yerine SİSTEM belirler: karakter adı İngilizce kalır, başka
   her özel ad Türkçe karşılığıyla girer — `pipeline._sozluge_isle`'ın otomatik
   davranışıyla aynı kural. Öneri yine de ONAYA sunulur: sözlük prompt'ta KURALdır,
   yanlış bir karşılık kitap boyunca birebir uygulanırdı. */
async function doldurOneri(secim) {
  const { terim, baglam } = secim;
  if (!currentBookSlug) return;
  // Zaten kayıtlıysa öneri istemeye gerek yok (kayıt INSERT OR REPLACE: kullanıcı
  // üzerine yazdığını bilerek yazsın). Çevrimdışıysa boş döner, akış sürer.
  const terms = await fetchGlossary(currentBookSlug);
  if (el("glossQuickModal").hidden) return; // kullanıcı bu arada kapattı
  if (terms[terim] !== undefined) {
    if (!el("glossQuickTarget").value.trim()) el("glossQuickTarget").value = terms[terim];
    el("glossQuickState").textContent =
      `Zaten kayıtlı: ${terim} → ${terms[terim]} · kaydedersen değişir`;
    return;
  }
  el("glossQuickState").textContent = "Karşılık öneriliyor…";
  try {
    const res = await fetchWithTimeout(
      `/api/book/${encodeURIComponent(currentBookSlug)}/glossary/suggest`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: terim, context: baglam || "" }),
      },
      25000 // model çağrısı: sözlük yazımından uzun sürebilir
    );
    if (!res.ok) throw new Error("öneri alınamadı");
    const data = await res.json();
    if (el("glossQuickModal").hidden) return;
    if (!el("glossQuickTarget").value.trim()) el("glossQuickTarget").value = data.target || terim;
    el("glossQuickState").textContent = data.is_character
      ? "Karakter adı → İngilizce kalacak. Yanlışsa karşılığı sen yaz."
      : "Önerilen karşılık dolduruldu; istersen değiştir.";
  } catch {
    if (el("glossQuickModal").hidden) return;
    el("glossQuickState").textContent =
      "Öneri alınamadı (sunucu kapalı ya da kota dolu olabilir) — karşılığı elle yaz.";
  }
}

function saveGlossQuick() {
  const source = trimSecim(el("glossQuickSource").value);
  if (!source) {
    el("glossQuickState").textContent = "Kaynak terim gerekli.";
    el("glossQuickSource").focus();
    return;
  }
  if (!currentBookSlug) {
    el("glossQuickState").textContent = "Kitap bilinmiyor — sözlük ekranından ekle.";
    return;
  }
  const target = el("glossQuickTarget").value.trim() || source;
  saveTerm(currentBookSlug, source, target); // çevrimdışıysa kuyrukta bekler
  el("glossQuickState").textContent = `Eklendi: ${source} → ${target}`;
  selGlossLast = null;
  setTimeout(() => (el("glossQuickModal").hidden = true), 700);
}

document.addEventListener("selectionchange", () => {
  clearTimeout(selGlossTimer);
  // Seçim tutamacı sürüklenirken her karede yeniden konumlandırma.
  selGlossTimer = setTimeout(updateSelGloss, 180);
});
// Seçim ekranda kayınca düğme onunla birlikte gitsin (gizlemek yerine yeniden konumla:
// kaydırıp sonra eklemek isteyen kullanıcı düğmeyi kaybetmemeli).
window.addEventListener("scroll", () => selGlossData && updateSelGloss(), { passive: true });

el("selGlossBtn")?.addEventListener("click", openGlossQuick);
el("glossQuickSave")?.addEventListener("click", saveGlossQuick);
el("glossQuickCancel")?.addEventListener("click", () => (el("glossQuickModal").hidden = true));
el("glossQuickModal")?.addEventListener("click", (e) => {
  if (e.target === el("glossQuickModal")) el("glossQuickModal").hidden = true;
});
for (const id of ["glossQuickSource", "glossQuickTarget"]) {
  el(id)?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    saveGlossQuick();
  });
}

// Açılışta bekleyen sözlük düzenlemelerini gönder (çevrimdışı eklenip telefonda
// kalmış olabilir); sunucu hâlâ kapalıysa kuyrukta bekler.
flushGlossQueue();

// Sıfırlamanın önbellek-kırıcı parametresini adres çubuğundan temizle. Uygulamanın
// kendi kök history kaydından (aşağıda) ÖNCE koşar; `history.state` korunur.
if (location.search.includes("kabuk=")) {
  history.replaceState(history.state, "", location.pathname);
}

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
  // Kalıcı depolama: tarayıcı yer darlığında çevrimdışı bölüm önbelleğini silmesin.
  navigator.storage?.persist?.().catch(() => {});
  // Yeni SW sürümü devraldığında sayfayı bir kez tazele: aksi halde açık sayfa
  // eski kabuk JS/CSS'iyle çalışmayı sürdürür (örn. yeni eklenen düğmeler görünmez).
  // hadController: ilk kurulumda (sayfa zaten ağdan geldi) gereksiz reload atlanır.
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController || reloaded) return;
    reloaded = true;
    location.reload();
  });
}
