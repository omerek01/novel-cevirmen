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
};
const THEMES = ["light", "sepia", "dark"];
const THEME_ICON = { light: "☾", sepia: "☀", dark: "☀" };
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
function onReaderScroll() {
  updateActiveChapter();
  updateProgress();
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
  el("libThemeToggle").textContent = THEME_ICON[settings.theme] || "☾";
  markSegment("theme", settings.theme, "data-theme-opt");
  markSegment("lh", settings.lineHeight, "data-lh");
  markSegment("mg", settings.margin, "data-mg");
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
      loadChapter(state.url, { restoreRatio: state.ratio });
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

async function renderLibrary() {
  clearTimeout(libraryJobPollTimer);
  const books = await fetchBooks();
  const shelf = el("shelf");
  el("libLoading").hidden = true;

  // D-PWA-Durum: sunucuya ulaşılamadı ≠ boş kütüphane. Raf daha önce çizildiyse
  // eldekini koru (anket yenilemesi rafı silmesin); hiç çizilmediyse hata yüzeyi.
  if (books === null) {
    if (!shelf.querySelector(".spine")) {
      el("libError").hidden = false;
      el("emptyState").hidden = true;
      el("filterEmpty").hidden = true;
      el("shelfFilters").hidden = true;
      el("resumeFiche").hidden = true;
    }
    return;
  }
  el("libError").hidden = true;

  shelf.replaceChildren();
  el("emptyState").hidden = books.length > 0;
  el("shelfFilters").hidden = books.length === 0;
  renderResumeFiche(books);
  renderLibStats();

  const visible = books.filter(
    (b) => shelfFilter === "all" || (b.status || "okunuyor") === shelfFilter
  );
  // Raf sırası = en son okunan en başta. Sunucu updated_at DESC döner ama yerel
  // son-okuma (çevrimdışı / düşmüş POST) sunucuya yansımamış olabilir; fişle aynı
  // tazelik ölçüsüyle istemcide yeniden sıralarız → devam ettiğin kitap rafın başında.
  visible.sort((a, b) => bookFreshness(b) - bookFreshness(a));
  el("filterEmpty").hidden = !(books.length > 0 && visible.length === 0);

  const jobChecks = [];
  for (const book of visible) {
    const spine = document.createElement("button");
    spine.className = "spine";
    spine.dataset.slug = book.slug; // rozet anketi sırtı yerinde bulabilsin
    spine.style.setProperty("--spine", spineColor(book.slug));
    // Etiket, resume ile AYNI merge'i kullanır → çevrimdışı okunan son bölüm de görünür
    // (sunucu chapter_no'su yalnız çevrimiçi güncellenir).
    const chNo = resolveResume(book, book.slug).chapterNo;
    const tag = chNo ? "BÖL. " + chNo : "OKU";
    spine.innerHTML =
      `<span class="spine-title" lang="en">${escapeHtml(book.title)}</span>` +
      '<span class="spine-job" hidden></span>' +
      `<span class="spine-tag">${tag}</span>`;
    spine.addEventListener("click", () => navigate({ view: "book", slug: book.slug }));
    shelf.appendChild(spine);
    jobChecks.push(fetchBookJob(book.slug).then((job) => applyJobBadge(spine, job)));
  }

  const add = document.createElement("button");
  add.className = "spine spine-add";
  add.innerHTML =
    '<span class="spine-plus">+</span><span class="spine-addlabel">KİTAP EKLE</span>';
  add.addEventListener("click", openAddModal);
  shelf.appendChild(add);

  const active = (await Promise.all(jobChecks)).some(Boolean);
  if (active && !views.library.hidden) {
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
  const spines = [...document.querySelectorAll("#shelf .spine[data-slug]")];
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
  for (const ch of chapters) {
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
async function fetchGlossary(slug) {
  const res = await fetch(`/api/book/${encodeURIComponent(slug)}/glossary`);
  const data = await res.json();
  return data.terms || {};
}
async function saveTerm(slug, source, target) {
  await fetch(`/api/book/${encodeURIComponent(slug)}/glossary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, target }),
  });
}
async function deleteTerm(slug, source) {
  await fetch(
    `/api/book/${encodeURIComponent(slug)}/glossary?source=${encodeURIComponent(source)}`,
    { method: "DELETE" }
  );
}

async function openGlossary(slug) {
  currentBookSlug = slug;
  const book = (await fetchBooks()).find((b) => b.slug === slug) || null;
  el("glossaryTitle").textContent = "SÖZLÜK — " + (book ? book.title : slug);

  const list = el("glossList");
  list.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "loading-row";
  loading.textContent = "Yükleniyor…";
  list.appendChild(loading);
  showView("glossary");
  window.scrollTo(0, 0);

  try {
    renderGlossary(await fetchGlossary(slug));
  } catch {
    list.replaceChildren();
    const err = document.createElement("p");
    err.className = "loading-row";
    err.textContent = "Sözlük yüklenemedi.";
    list.appendChild(err);
  }
}

function renderGlossary(terms) {
  const list = el("glossList");
  list.replaceChildren();
  const entries = Object.entries(terms);
  if (entries.length === 0) {
    const p = document.createElement("p");
    p.className = "loading-row";
    p.textContent = "Henüz terim yok. Bölüm okudukça karakter isimleri buraya eklenir.";
    list.appendChild(p);
    return;
  }
  for (const [source, target] of entries) {
    const row = document.createElement("div");
    row.className = "gloss-row";

    const src = document.createElement("span");
    src.className = "gloss-source";
    src.textContent = source;

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
    });

    const del = document.createElement("button");
    del.className = "gloss-del";
    del.textContent = "×";
    del.setAttribute("aria-label", source + " sil");
    del.addEventListener("click", () => {
      deleteTerm(currentBookSlug, source);
      row.remove();
    });

    row.append(src, arrow, tgt, del);
    list.appendChild(row);
  }
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
  const { refresh = false, restoreRatio = null } = opts;
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
    body.replaceChildren(entry.el);
    body.hidden = false;
    ensureTopCard();
    ensureBottomSentinel();
    setActiveChapter(entry);
    const ratio = restoreRatio != null ? restoreRatio : getScrollLocal(url);
    scrollToChapterRatio(entry, ratio || 0);
    prefetchNext(entry);
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
function fetchChapterData(url, refresh, track = true) {
  const query =
    `/api/chapter?url=${encodeURIComponent(url)}` +
    (refresh ? "&refresh=1" : "") +
    (track ? "" : "&track=0");
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
    el: null,
    loaded: false,
    empty: false,
  };
  const art = document.createElement("article");
  art.className = "chapter" + (isHtml ? " chapter-html" : "");
  art.dataset.url = url;
  if (entry.no != null) art.dataset.no = entry.no;
  const sep = document.createElement("div");
  sep.className = "chapter-sep";
  // Görsel içerikte ayraç başlığı gösterir ("Sayfa 32"); metin bölümde "Bölüm N".
  sep.textContent = isHtml
    ? `— ${entry.title || (entry.no != null ? "Bölüm " + entry.no : "Bölüm")} —`
    : entry.no != null
      ? `— Bölüm ${entry.no} —`
      : `— ${entry.title || "Bölüm"} —`;
  art.appendChild(sep);
  entry.el = art; // renderParagraphs/renderHtml entry.el'e yazar → sep'ten ÖNCE atanmalı
  if (isHtml) {
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
  btn.textContent = "Yeniden Çevir";
  btn.addEventListener("click", () => retranslateChapter(entry));
  actions.appendChild(btn);
  card.append(title, desc, actions);
  return card;
}

/* ---------- prefetch: sonraki bölümü sessizce ısıt ---------- */
function prefetchNext(entry) {
  const u = entry && entry.nextUrl;
  if (!u || !/^https?:\/\//.test(u) || prefetched.has(u)) return;
  prefetched.add(u);
  fetch("/api/prefetch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: u }),
  }).catch(() => {});
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
  bottomObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((en) => en.isIntersecting)) maybeAppendNext();
    },
    { rootMargin: "800px 0px" } // görünmeden ~800px önce hazırla (dikişsiz akış)
  );
  bottomObserver.observe(s);
}

// Akışın sonuna göre uygun kartı göster: next varsa "hazırlanıyor" ipucu (gözlemci
// birazdan ekler); web bölümü ama next yok → "SONRAKINI WEB'DEN GETİR"; sentetik/son
// → "— Son bölüm —".
function updateEndCard() {
  const s = el("streamEnd");
  if (!s || !stream.length) return;
  const last = stream[stream.length - 1];
  s.replaceChildren();
  s.className = "stream-end";
  if (last.nextUrl) {
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
  if (streamBusy || !stream.length) return;
  const last = stream[stream.length - 1];
  if (!last.nextUrl) return;
  streamBusy = true;
  let ok = false;
  const s = el("streamEnd");
  s.replaceChildren();
  const load = document.createElement("div");
  load.className = "stream-loading";
  load.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span> Sonraki bölüm yükleniyor…`;
  s.appendChild(load);
  try {
    // track=false: önden eklenen bölüm okunmuş sayılmaz → konumu ilerletmez.
    const data = await fetchChapterData(last.nextUrl, false, false);
    const entry = buildChapterEntry(last.nextUrl, data);
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
      maybeAppendNext();
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
async function retranslateChapter(entry) {
  const btn = el("retranslate");
  const orig = btn.innerHTML;
  btn.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span> Yükleniyor…`;
  btn.disabled = true;
  try {
    const data = await fetchChapterData(entry.url, true);
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
el("glossAddBtn").addEventListener("click", async () => {
  const source = el("glossSource").value.trim();
  if (!source) return;
  const target = el("glossTarget").value.trim() || source;
  await saveTerm(currentBookSlug, source, target);
  el("glossSource").value = "";
  el("glossTarget").value = "";
  renderGlossary(await fetchGlossary(currentBookSlug));
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
el("settingsBtn").addEventListener("click", () => {
  el("settingsPanel").hidden = !el("settingsPanel").hidden;
  if (!el("settingsPanel").hidden) showShellVersion();
});

/* ---------- kabuk sürümü + sıfırlama (bayat kabuk kaçış kapısı) ---------- */
// Panel her açılışta GERÇEK önbellek durumunu okur (JS'teki bir sabit değil):
// telefonun fiilen hangi kabuğu servis ettiği görülür → "güncellendi mi?"
// sorusu tahmin olmaktan çıkar.
async function showShellVersion() {
  const out = el("shellVersion");
  if (!out) return;
  if (!("caches" in window)) {
    out.textContent = "(önbellek yok — hep ağdan)";
    return;
  }
  try {
    const keys = await caches.keys();
    const shell = keys.find((k) => k.startsWith("novellink-shell-"));
    out.textContent = shell ? shell.replace("novellink-shell-", "") : "(kurulmadı)";
  } catch {
    out.textContent = "";
  }
}

el("shellReset")?.addEventListener("click", async () => {
  const btn = el("shellReset");
  btn.disabled = true;
  btn.textContent = "Sıfırlanıyor…";
  try {
    if ("serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if ("caches" in window) {
      const keys = await caches.keys();
      // İndirilen bölümler (novellink-data) KORUNUR; yalnız kabuk önbellekleri silinir.
      await Promise.all(
        keys.filter((k) => k !== "novellink-data").map((k) => caches.delete(k))
      );
    }
  } catch {}
  location.reload();
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
    const chs = await chaptersOf(slug);
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
renderLibrary();
showView("library");

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
