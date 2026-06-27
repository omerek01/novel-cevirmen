"use strict";

const LS_SETTINGS = "novellink:settings";
const DEFAULT_SETTINGS = { theme: "light", fontPx: 19, font: "serif" };

const el = (id) => document.getElementById(id);
const views = {
  library: el("libraryView"),
  book: el("bookView"),
  glossary: el("glossaryView"),
  reader: el("readerView"),
};

let settings = loadSettings();
let currentNext = null;
let currentUrl = null;
let currentBookSlug = null;
let bulkStop = false;
let offlineStop = false;

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

/* ---------- ayarları uygula ---------- */
function applySettings() {
  document.documentElement.dataset.theme = settings.theme;
  document.documentElement.style.setProperty("--reading", settings.fontPx + "px");
  document.documentElement.style.setProperty(
    "--reading-font",
    settings.font === "sans"
      ? 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
      : 'Georgia, "Times New Roman", serif'
  );
}
function updateSettingsUI() {
  el("fontValue").textContent = settings.fontPx;
  el("fontFamily").textContent = settings.font === "sans" ? "Sans" : "Serif";
  el("themeToggle").textContent = settings.theme === "dark" ? "Koyu" : "Açık";
  el("libThemeToggle").textContent = settings.theme === "dark" ? "☀" : "☾";
}

function toggleTheme() {
  settings.theme = settings.theme === "dark" ? "light" : "dark";
  saveSettings();
  applySettings();
  updateSettingsUI();
}

/* ---------- görünüm ---------- */
function showView(name) {
  for (const [key, node] of Object.entries(views)) node.hidden = key !== name;
  window.scrollTo(0, 0);
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function spineColor(slug) {
  // 32-bit hash → tüm renk spektrumuna yay (eski %360 hue'ları dar banda sıkıştırıyordu).
  let h = 0;
  for (const ch of slug) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const hue = h % 360;
  const sat = 48 + (Math.floor(h / 360) % 22); // 48–69%
  const light = 38 + (Math.floor(h / 7920) % 12); // 38–49% (beyaz metin okunur kalır)
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
    spine.addEventListener("click", () => openBook(book.slug));
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
  const book = (await fetchBooks()).find((b) => b.slug === slug) || null;
  el("bookTitle").textContent = book ? book.title : slug;

  const resume = el("resumeBtn");
  if (book && book.current_url) {
    resume.hidden = false;
    resume.onclick = () => loadChapter(book.current_url);
  } else {
    resume.hidden = true;
  }

  const list = el("chapterList");
  list.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "loading-row";
  loading.textContent = "Yükleniyor…";
  list.appendChild(loading);
  showView("book");

  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/chapters`);
    const data = await res.json();
    renderChapterList(data.chapters || [], book);
  } catch {
    list.replaceChildren();
    const err = document.createElement("p");
    err.className = "loading-row";
    err.textContent = "Bölümler yüklenemedi.";
    list.appendChild(err);
  }
}

function renderChapterList(chapters, book) {
  const list = el("chapterList");
  list.replaceChildren();
  if (chapters.length === 0) {
    const p = document.createElement("p");
    p.className = "loading-row";
    p.textContent = "Henüz çevrilmiş bölüm yok. 'Kaldığın yerden devam et' ile başla.";
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
    row.addEventListener("click", () => loadChapter(ch.url));
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
  if (!message) {
    s.hidden = true;
    return;
  }
  s.hidden = false;
  s.textContent = message;
}

async function loadChapter(url, refresh = false) {
  if (!url) return;
  currentUrl = url;
  showView("reader");
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
    renderChapter(data);
  } catch (err) {
    setStatus("Hata: " + err.message);
  }
}

function renderChapter(data) {
  setStatus(null);
  el("readerBook").textContent = data.book_title || "";
  el("readerChapter").textContent = data.title || "Bölüm";

  const body = el("readerBody");
  body.replaceChildren();
  for (const para of (data.translation || "").split(/\n\n+/)) {
    if (!para.trim()) continue;
    const p = document.createElement("p");
    p.textContent = para;
    body.appendChild(p);
  }
  body.hidden = false;

  currentNext = data.next_url || null;
  currentBookSlug = data.book_slug || currentBookSlug;
  const next = el("nextBtn");
  next.disabled = !currentNext;
  next.textContent = currentNext ? "SONRAKI BÖLÜM →" : "SON BÖLÜM";
  el("readerFooter").hidden = false;
  window.scrollTo(0, 0);
}

/* ---------- olaylar ---------- */
el("libThemeToggle").addEventListener("click", toggleTheme);
el("themeToggle").addEventListener("click", toggleTheme);
el("backBtn").addEventListener("click", () => {
  if (currentBookSlug) openBook(currentBookSlug);
  else {
    renderLibrary();
    showView("library");
  }
});
el("bookBackBtn").addEventListener("click", () => {
  renderLibrary();
  showView("library");
});
el("openGlossaryBtn").addEventListener("click", () => {
  if (currentBookSlug) openGlossary(currentBookSlug);
});
el("glossaryBackBtn").addEventListener("click", () => {
  if (currentBookSlug) openBook(currentBookSlug);
  else {
    renderLibrary();
    showView("library");
  }
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

/* ---------- toplu çeviri ---------- */
el("bulkBtn").addEventListener("click", () => {
  el("bulkCount").value = "10";
  el("bulkModal").hidden = false;
});
el("bulkCancel").addEventListener("click", () => {
  el("bulkModal").hidden = true;
});
el("bulkStop").addEventListener("click", () => {
  bulkStop = true;
});
el("bulkStart").addEventListener("click", () => {
  const n = Math.max(1, Math.min(200, parseInt(el("bulkCount").value, 10) || 0));
  el("bulkModal").hidden = true;
  startBulk(n);
});

async function startBulk(count) {
  const book = (await fetchBooks()).find((b) => b.slug === currentBookSlug);
  let url = book ? book.current_url : null;
  if (!url) return;

  bulkStop = false;
  el("bulkStop").disabled = false;
  el("bulkProgressText").textContent = "Hazırlanıyor…";
  el("bulkProgress").hidden = false;

  let done = 0;
  let translated = 0;
  for (let i = 0; i < count; i++) {
    if (bulkStop) {
      el("bulkProgressText").textContent = `Durduruldu. ${translated} yeni bölüm çevrildi.`;
      break;
    }
    el("bulkProgressText").textContent = `Bölüm ${i + 1} / ${count} hazırlanıyor…`;
    let data;
    try {
      const res = await fetch(`/api/chapter?url=${encodeURIComponent(url)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        el("bulkProgressText").textContent = "Durdu: " + (err.detail || "hata " + res.status);
        break;
      }
      data = await res.json();
    } catch (e) {
      el("bulkProgressText").textContent = "Bağlantı hatası: " + e.message;
      break;
    }
    done++;
    if (!data.cached) translated++;
    el("bulkProgressText").textContent =
      `${done} / ${count} bitti — ${data.title || ""} (${translated} yeni)`;
    if (!data.next_url) {
      el("bulkProgressText").textContent = `Son bölüme ulaşıldı. ${translated} yeni bölüm çevrildi.`;
      break;
    }
    url = data.next_url;
  }

  el("bulkStop").disabled = true;
  setTimeout(() => {
    el("bulkProgress").hidden = true;
    if (currentBookSlug) openBook(currentBookSlug);
  }, 2000);
}

/* ---------- çevrimdışı indir ---------- */
// Optional chaining: eski (önbellekteki) HTML bu düğümleri içermese bile
// başlangıç scripti durmaz, kütüphane yine çizilir.
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

// Verilen kitapların tüm çevrilmiş bölümlerini telefonun önbelleğine indirir
// (her bölüm fetch'i service worker tarafından önbelleğe yazılır → çevrimdışı okunur).
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
el("settingsBtn").addEventListener("click", () => {
  el("settingsPanel").hidden = !el("settingsPanel").hidden;
});
el("nextBtn").addEventListener("click", () => {
  if (currentNext) loadChapter(currentNext);
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
  if (currentUrl) loadChapter(currentUrl, true);
});
el("addCancel").addEventListener("click", closeAddModal);
el("addConfirm").addEventListener("click", () => {
  const url = el("addUrlInput").value.trim();
  if (url) {
    closeAddModal();
    loadChapter(url);
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
renderLibrary();
showView("library");

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
