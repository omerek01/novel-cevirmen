"use strict";

const LS_SETTINGS = "novellink:settings";
const LS_SCROLL = "novellink:scroll";
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
let currentNext = null;
let currentPrev = null;
let currentUrl = null;
let currentBookSlug = null;
let currentBook = null; // {current_url, current_ratio, ...} — resume için
let currentChapters = []; // açık kitabın tam bölüm listesi (prev türetme + arama)
let currentParas = []; // açık bölümün paragrafları (bölümde arama)
let offlineStop = false;
let isRestoring = false; // programatik scroll sırasında kaydı baskıla
let chapterLoaded = false; // bölüm BAŞARIYLA render edildi mi (konum kaydı için)
let scrollSaveTimer = null;
let bulkPollTimer = null;

/* ---------- depolama ---------- */
async function fetchBooks() {
  try {
    const res = await fetch("/api/books");
    const data = await res.json();
    return data.books || [];
  } catch {
    return [];
  }
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
function currentRatio() {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  if (max <= 0) return 0;
  return Math.min(1, Math.max(0, window.scrollY / max));
}
function persistScroll() {
  // Yalnızca başarıyla render edilmiş bölümün konumunu kaydet. Aksi halde çekme/çeviri
  // başarısız bir bölüm (henüz cache'te yok) "kaldığın yer" olarak yazılır ve sonraki
  // açılışta "devam et" onu yeniden çekmeye çalışır → gereksiz "Yükleniyor" ekranı.
  if (!currentUrl || !chapterLoaded || views.reader.hidden) return;
  const ratio = currentRatio();
  saveScrollLocal(currentUrl, ratio);
  if (currentBookSlug) {
    fetch(`/api/book/${encodeURIComponent(currentBookSlug)}/position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrl, ratio }),
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
  updateProgress();
  if (isRestoring) return;
  if (scrollSaveTimer) return;
  scrollSaveTimer = setTimeout(() => {
    scrollSaveTimer = null;
    persistScroll();
  }, 250);
}
function restoreScroll(ratio) {
  if (!ratio || ratio <= 0) {
    isRestoring = false;
    window.scrollTo(0, 0);
    updateProgress();
    return;
  }
  isRestoring = true;
  requestAnimationFrame(() => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    window.scrollTo(0, Math.round(max * ratio));
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
  switch (state && state.view) {
    case "book":
      openBook(state.slug);
      break;
    case "glossary":
      openGlossary(state.slug);
      break;
    case "reader":
      loadChapter(state.url, state.ratio != null ? { restoreRatio: state.ratio } : {});
      break;
    default:
      renderLibrary();
      showView("library");
  }
}

// İleri navigasyon: geçmişe yeni kayıt ekle ve görünümü çiz.
function navigate(state) {
  history.pushState(state, "");
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

function spineColor(slug) {
  let h = 0;
  for (const ch of slug) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const hue = h % 360;
  const sat = 48 + (Math.floor(h / 360) % 22);
  const light = 38 + (Math.floor(h / 7920) % 12);
  return `hsl(${hue} ${sat}% ${light}%)`;
}

/* ---------- kütüphane ---------- */
async function renderLibrary() {
  const books = await fetchBooks();
  const shelf = el("shelf");
  shelf.replaceChildren();
  el("emptyState").hidden = books.length > 0;

  for (const book of books) {
    const spine = document.createElement("button");
    spine.className = "spine";
    spine.style.setProperty("--spine", spineColor(book.slug));
    const tag = book.chapter_no ? "BÖL. " + book.chapter_no : "OKU";
    spine.innerHTML =
      `<span class="spine-title">${escapeHtml(book.title)}</span>` +
      `<span class="spine-tag">${tag}</span>`;
    spine.addEventListener("click", () => navigate({ view: "book", slug: book.slug }));
    shelf.appendChild(spine);
  }

  const add = document.createElement("button");
  add.className = "spine spine-add";
  add.innerHTML =
    '<span class="spine-plus">+</span><span class="spine-addlabel">KİTAP EKLE</span>';
  add.addEventListener("click", openAddModal);
  shelf.appendChild(add);
}

/* ---------- kitap (bölüm listesi) ---------- */
async function openBook(slug) {
  currentBookSlug = slug;
  const books = await fetchBooks();
  currentBook = books.find((b) => b.slug === slug) || null;
  el("bookTitle").textContent = currentBook ? currentBook.title : slug;

  const resume = el("resumeBtn");
  if (currentBook && currentBook.current_url) {
    resume.hidden = false;
    resume.onclick = () =>
      navigate({
        view: "reader",
        url: currentBook.current_url,
        ratio: currentBook.current_ratio || 0,
      });
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
    const row = document.createElement("button");
    row.className = "chapter-row";
    if (book && ch.url === book.current_url) row.classList.add("current");
    const no = document.createElement("span");
    no.className = "chapter-no";
    no.textContent = ch.chapter_no ? "BÖLÜM " + ch.chapter_no : "BÖLÜM";
    const name = document.createElement("span");
    name.className = "chapter-name";
    name.textContent = ch.title || "";
    row.append(no, name);
    row.addEventListener("click", () => navigate({ view: "reader", url: ch.url }));
    list.appendChild(row);
  }
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
function openAddModal() {
  el("addUrlInput").value = "";
  el("addModal").hidden = false;
  el("addUrlInput").focus();
}
function closeAddModal() {
  el("addModal").hidden = true;
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

function renderError(message, url, refresh) {
  isRestoring = false;
  const s = el("status");
  s.replaceChildren();
  s.hidden = false;
  const msg = document.createElement("div");
  msg.textContent = "Hata: " + message;
  const retry = document.createElement("button");
  retry.className = "pill";
  retry.textContent = "Tekrar dene";
  retry.style.marginTop = "1rem";
  retry.addEventListener("click", () => loadChapter(url, { refresh }));
  s.append(msg, retry);
}

async function loadChapter(url, opts = {}) {
  if (!url) return;
  const { refresh = false, restoreRatio = null } = opts;
  currentUrl = url;
  chapterLoaded = false; // başarı (renderChapter) gelene dek konum kaydını engelle
  isRestoring = true; // yükleme/işleme penceresinde kaydı baskıla
  showView("reader");
  closeFind();
  el("settingsPanel").hidden = true;
  el("readerBody").hidden = true;
  el("readerFooter").hidden = true;
  setStatus(refresh ? "Yeniden çevriliyor…" : "Yükleniyor…");

  try {
    const query =
      `/api/chapter?url=${encodeURIComponent(url)}` + (refresh ? "&refresh=1" : "");
    const res = await fetch(query);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Sunucu hatası (${res.status})`);
    }
    const data = await res.json();
    const ratio = restoreRatio != null ? restoreRatio : getScrollLocal(url);
    renderChapter(data, ratio);
  } catch (err) {
    renderError(err.message, url, refresh);
  }
}

function computePrev(data) {
  if (currentChapters && currentChapters.length) {
    const idx = currentChapters.findIndex((c) => c.url === currentUrl);
    if (idx > 0) return currentChapters[idx - 1].url;
  }
  return data.prev_url || null; // listede yok / başı → sayfadan çekilen yedek
}

function renderChapter(data, ratio) {
  setStatus(null);
  chapterLoaded = true; // başarı: artık bu bölümün konumu kaydedilebilir
  el("readerBook").textContent = data.book_title || "";
  el("readerChapter").textContent = data.title || "Bölüm";

  currentParas = (data.translation || "")
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
  renderReaderBody("");
  el("readerBody").hidden = false;

  currentNext = data.next_url || null;
  currentBookSlug = data.book_slug || currentBookSlug;
  currentPrev = computePrev(data);

  const next = el("nextBtn");
  next.disabled = !currentNext;
  next.textContent = currentNext ? "SONRAKI BÖLÜM →" : "SON BÖLÜM";
  const prev = el("prevBtn");
  prev.hidden = !currentPrev;
  el("readerFooter").hidden = false;

  restoreScroll(ratio || 0);
}

function renderReaderBody(query) {
  const body = el("readerBody");
  body.replaceChildren();
  const q = (query || "").trim();
  for (const para of currentParas) {
    const p = document.createElement("p");
    if (q) appendHighlighted(p, para, q);
    else p.textContent = para;
    body.appendChild(p);
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
function closeFind() {
  el("findBar").hidden = true;
  el("findInput").value = "";
  findMatches = [];
  findIndex = -1;
  el("findCount").textContent = "";
  if (currentParas.length) renderReaderBody("");
}
function runFind() {
  const q = el("findInput").value.trim();
  renderReaderBody(q);
  findMatches = q ? Array.from(el("readerBody").querySelectorAll("mark")) : [];
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

/* ---------- olaylar: navigasyon ---------- */
el("libThemeToggle").addEventListener("click", cycleTheme);
el("backBtn").addEventListener("click", () => {
  if (currentBookSlug) navigate({ view: "book", slug: currentBookSlug });
  else navigate({ view: "library" });
});
el("bookBackBtn").addEventListener("click", () => {
  navigate({ view: "library" });
});
el("openGlossaryBtn").addEventListener("click", () => {
  if (currentBookSlug) navigate({ view: "glossary", slug: currentBookSlug });
});
el("glossaryBackBtn").addEventListener("click", () => {
  if (currentBookSlug) navigate({ view: "book", slug: currentBookSlug });
  else navigate({ view: "library" });
});
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
el("retranslate").addEventListener("click", () => {
  if (currentUrl) loadChapter(currentUrl, { refresh: true });
});

/* ---------- olaylar: okuyucu nav + bölümde arama ---------- */
el("nextBtn").addEventListener("click", () => {
  if (currentNext) navigate({ view: "reader", url: currentNext });
});
el("prevBtn").addEventListener("click", () => {
  if (currentPrev) navigate({ view: "reader", url: currentPrev });
});
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

/* ---------- kaydırarak bölüm geçişi (swipe) ---------- */
let touchX = null;
let touchY = null;
el("readerBody").addEventListener(
  "touchstart",
  (e) => {
    if (e.touches.length !== 1) return;
    touchX = e.touches[0].clientX;
    touchY = e.touches[0].clientY;
  },
  { passive: true }
);
el("readerBody").addEventListener(
  "touchend",
  (e) => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    const dy = e.changedTouches[0].clientY - touchY;
    touchX = touchY = null;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    if (dx < 0 && currentNext) navigate({ view: "reader", url: currentNext });
    else if (dx > 0 && currentPrev) navigate({ view: "reader", url: currentPrev });
  },
  { passive: true }
);

/* ---------- toplu çeviri (sunucu-taraflı arka plan iş) ---------- */
el("bulkBtn").addEventListener("click", () => {
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
  const book = currentBook || (await fetchBooks()).find((b) => b.slug === currentBookSlug);
  const url = book ? book.current_url : null;
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
  el("bulkStop").onclick = () => {
    fetch(`/api/bulk/${jobId}/stop`, { method: "POST" }).catch(() => {});
  };
  pollBulk(jobId);
}

function pollBulk(jobId) {
  clearTimeout(bulkPollTimer);
  const tick = async () => {
    let s;
    try {
      const r = await fetch(`/api/bulk/${jobId}`);
      s = await r.json();
    } catch {
      bulkPollTimer = setTimeout(tick, 2000);
      return;
    }
    el("bulkProgressText").textContent = s.message || "…";
    if (s.state === "running") {
      bulkPollTimer = setTimeout(tick, 1500);
    } else {
      el("bulkStop").disabled = true;
      setTimeout(() => {
        el("bulkProgress").hidden = true;
        if (currentBookSlug) openBook(currentBookSlug);
      }, 2500);
    }
  };
  tick();
}

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
el("addConfirm").addEventListener("click", () => {
  const url = el("addUrlInput").value.trim();
  if (url) {
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
history.replaceState({ view: "library" }, ""); // kök kayıt: buradan geri = uygulamadan çık
renderLibrary();
showView("library");

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
