/* Kütüphane rafı: kitap sırtları, devam fişi, durum filtresi, iş rozetleri. */

import { otoIndirmeTur } from "./cevrimdisi.js";
import { durum, views } from "./durum.js";
import { openAddModal } from "./ekle.js";
import { navigate } from "./gezinme.js";
import { getLastRead, resolveResume } from "./konum.js";
import { persistScroll } from "./okuyucu.js";
import { el, escapeHtml, localDay } from "./temel.js";

export let libraryJobPollTimer = null;

/* ---------- depolama ---------- */
// null = sunucuya ulaşılamadı (D-PWA-Durum: "boş kütüphane" olarak RENDER EDİLMEZ).
// [] = sunucu cevap verdi ve kütüphane gerçekten boş.
export async function fetchBooks() {
  try {
    const res = await fetch("/api/books");
    if (!res.ok) return null;
    const data = await res.json();
    return data.books || [];
  } catch {
    return null;
  }
}

// WCAG göreli parlaklık (0..1) — HSL bileşenlerinden (s ve l 0..1).
export function hslLuma(hue, s, l) {
  const a = s * Math.min(l, 1 - l);
  const chan = (n) => {
    const k = (n + hue / 30) % 12;
    const c = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * chan(0) + 0.7152 * chan(8) + 0.0722 * chan(4);
}

export function spineColor(slug) {
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
export function bookKind(book) {
  const s = book.slug || "";
  const u = book.current_url || "";
  if (s.startsWith("manga-") || u.startsWith("manga://")) return "manga";
  if (s.startsWith("pdf-") || s.startsWith("epub-") || u.startsWith("pdf://") || u.startsWith("epub://"))
    return "kitap";
  return "novel";
}
// Raf sırası + başlıkları (tür-bazlı raflar). Boş tür rafı çizilmez.
export const KIND_SHELVES = [
  { kind: "novel", label: "Noveller" },
  { kind: "manga", label: "Mangalar" },
  { kind: "kitap", label: "Kitaplar" },
];

// Raf durum filtresi (D-B2v2: yaşam durumu sırtta görünmez, yalnız filtre).
export const LS_FILTER = "novellink:shelfFilter";
export let shelfFilter = localStorage.getItem(LS_FILTER) || "all";

export function setShelfFilter(value) {
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
export function bookFreshness(book) {
  const local = getLastRead(book.slug);
  return Math.max((book.updated_at || 0) * 1000, (local && local.ts) || 0);
}

// Devam fişi hedefi: en TAZE okunan kitap (kitaplar arasında en yenisi kazanır).
export function pickResumeBook(books) {
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
export function renderResumeFiche(books) {
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
    durum.currentBookSlug = book.slug; // ilk bölüm hata verirse "metni yapıştır" doğru kitaba yazsın
    navigate({ view: "reader", url: target.url, ratio: target.ratio });
  };
  fiche.hidden = false;
}

// Raf altı sessiz istatistik satırı (D-B3: gün-1 "Bugün 0" gizlenir;
// çevrimdışı/hata → satır tamamen gizli, okuma akışına etkisi yok).
export async function renderLibStats() {
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
export function makeSpine(book, jobChecks) {
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
export function makeAddSpine() {
  const add = document.createElement("button");
  add.className = "spine spine-add";
  add.innerHTML =
    '<span class="spine-plus" aria-hidden="true">+</span><span class="spine-addlabel">KİTAP EKLE</span>';
  add.addEventListener("click", openAddModal);
  return add;
}

// Bir tür rafı: başlık (varsa) + sırtlar + raf tahtası. withAdd → ekle sırtı sona.
export function buildShelfSection(label, books, withAdd, jobChecks) {
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

export async function renderLibrary() {
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
export function applyJobBadge(spine, job) {
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
export async function refreshShelfBadges() {
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

export async function fetchBookJob(slug) {
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/job`);
    if (!res.ok) return null;
    return (await res.json()).job || null;
  } catch {
    return null;
  }
}

export function isRecentJob(job) {
  return job.state === "running" || Date.now() / 1000 - (job.updated_at || 0) < 86400;
}

export function jobBadgeText(job) {
  if (job.state === "running") return `${job.done}/${job.total} · DEVAM ET`;
  return "! HATA"; // applyJobBadge yalnız running/error gösterir
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {

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
  // Kalıcı raf filtresini çiplere yansıt (setShelfFilter çağrılmaz — çift render olmasın).
  document.querySelectorAll("#shelfFilters .chip").forEach((c) => {
    c.setAttribute("aria-pressed", String(c.dataset.filter === shelfFilter));
  });
}
