/* Okuyucu: sonsuz okuma akışı, bölüm çizimi, künye, prefetch, iki-dilli satır,
   bölümde arama, köken odağı. */

import { diyalogAcikMi, diyalogKapat } from "./diyalog.js";
import { settings } from "./ayarlar.js";
import { warmOffline } from "./cevrimdisi.js";
import { durum, views } from "./durum.js";
import { navigate, showView } from "./gezinme.js";
import { openBook } from "./kitap.js";
import { getScrollLocal, saveLastRead, saveScrollLocal } from "./konum.js";
import { saveTerm, tazelemeyiPlanla, terimiSilGeriAlinabilir } from "./sozluk.js";
import { ICONS, SVG, el, escapeHtml, localDay } from "./temel.js";

// --- Sonsuz okuma v2 (D-B9v2): tek-bölüm singleton yerine bölüm AKIŞI ---
// Her bölüm kendi <article data-url> öğesinde; aktif bölüm = reader-bar çizgisini
// geçen SON bölüm (en-çok-görünür değil → titreme önlenir). Konum {url, bölüm-içi
// oran}; aktif değişince history.replaceState (push YOK) → geri jesti okuyucudan çıkar.
export let stream = []; // [{url,no,title,paras,source,nextUrl,prevUrl,bookSlug,bookTitle,el,loaded,empty}]
export let activeUrl = null; // reader-bar alt çizgisini geçen son bölümün url'i
export let streamBusy = false; // append/prepend uçuşta — çift tetiği engelle
export let bottomObserver = null; // akış sonu gözlemcisi (sonrakini otomatik ekle)
export const loggedReads = new Set(); // bu oturumda reading-log'a yazılmış url'ler
export const prefetched = new Set(); // ısıtma (prefetch) tetiklenmiş next url'leri
export let sourceLoading = false; // eski bölüm kaynağı yüklenirken çift-istek engeli
export let mangaNextExhausted = false; // manga: site'de sonraki bölüm kalmadı → devam deneme (resetStream'de sıfırlanır)
export let isRestoring = false; // programatik scroll sırasında kaydı baskıla
export let scrollSaveTimer = null;
export let isNavigating = false;
export let failedAttempts = 0;
/* ---------- sonsuz okuma: aktif bölüm + konum ---------- */
export function activeEntry() {
  return stream.find((c) => c.url === activeUrl) || null;
}
export function entryFor(url) {
  return stream.find((c) => c.url === url) || null;
}
export function readerBar() {
  return document.querySelector("#readerView .reader-bar");
}
export function readerBarBottom() {
  const b = readerBar();
  return b ? b.getBoundingClientRect().bottom : 0;
}

// Konum = AKTİF bölüm içindeki oran (bölüm-yerel). reader-bar alt çizgisinin, aktif
// bölümün üstünden ne kadar aşağıda olduğu / bölüm yüksekliği. İlerleme çubuğu da bunu
// gösterir (her bölümde 0→1) — sonsuz akışta "bu bölümde ne kadar ilerledim".
export function currentRatio() {
  const e = activeEntry();
  if (!e || !e.el) return 0;
  const r = e.el.getBoundingClientRect();
  if (r.height <= 0) return 0;
  return Math.min(1, Math.max(0, (readerBarBottom() - r.top) / r.height));
}

// Aktif bölümü yeniden hesapla: reader-bar çizgisini GEÇEN son bölüm. En-çok-görünür
// yerine "çizgiyi geçen son" seçilir → iki bölüm ekranı paylaşırken titremez (D-B9v2).
export function updateActiveChapter() {
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
export function setActiveChapter(e) {
  activeUrl = e.url;
  durum.currentUrl = e.url;
  durum.currentBookSlug = e.bookSlug || durum.currentBookSlug;
  durum.currentChapterNo = e.no;
  durum.currentChapterTitle = e.title;
  el("readerBook").textContent = e.bookTitle || "";
  el("readerChapter").textContent = e.title || "Bölüm";
  const st = history.state;
  if (st && st.view === "reader") {
    history.replaceState({ view: "reader", url: e.url, ratio: currentRatio() }, "");
  }
  saveLastRead(durum.currentBookSlug, e.url);
  logReadOnce(e);
}

// Okuma günlüğü: bölüm gerçekten aktif olunca, oturum başına bir kez (karar #8 —
// SW cache-first GET sunucuya ulaşmaz; istemci olayı şart; prefetch bu yola girmez).
export function logReadOnce(e) {
  if (!e || !e.loaded || !e.bookSlug || loggedReads.has(e.url)) return;
  loggedReads.add(e.url);
  fetch("/api/reading-log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day: localDay(), slug: e.bookSlug, url: e.url }),
  }).catch(() => {});
}

export function persistScroll() {
  // Yalnızca başarıyla render edilmiş aktif bölümün konumunu kaydet — aksi halde
  // yarım/hatalı bir bölüm "kaldığın yer" olarak yazılır, sonraki açılış onu yeniden
  // çekmeye çalışır (gereksiz "Yükleniyor").
  if (views.reader.hidden) return;
  const e = activeEntry();
  if (!e || !e.loaded) return;
  const ratio = currentRatio();
  saveScrollLocal(e.url, ratio);
  saveLastRead(durum.currentBookSlug, e.url);
  const st = history.state;
  if (st && st.view === "reader") history.replaceState({ view: "reader", url: e.url, ratio }, "");
  if (durum.currentBookSlug) {
    // Konum ÜÇLÜ gider: (url, ad, numara). Ad/numara sunucuda `current_url`i
    // ANLATIR; yalnız url gönderilince satır tutarsızlaşıyor ve kütüphane fişi
    // okunan bölümden bir geride kalıyordu (bkz. library.set_position).
    // Değerler `durum.currentChapterNo`/`durum.currentChapterTitle` GLOBAL'lerinden değil,
    // konumu yazılan ENTRY'nin kendisinden alınır: url ile ad tek kaynaktan
    // gelsin, global'lerin geride kalması bu satırı yeniden bozamasın.
    fetch(`/api/book/${encodeURIComponent(durum.currentBookSlug)}/position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: e.url,
        ratio,
        title: e.title || null,
        chapter_no: e.no != null ? e.no : null,
      }),
    }).catch(() => {});
  }
}
export function updateProgress() {
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
export let hudSonY = 0;

export function hudGuncelle() {
  const bar = readerBar();
  if (!bar) return;
  // Ayar sheet'i ya da arama çubuğu açıkken HUD kaçmaz: kullanıcı o an onlarla
  // uğraşıyor ve dayanak aldığı çubuğun kayması yön kaybettirir.
  if (diyalogAcikMi("settingsPanel") || !el("findBar").hidden) {
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

export function hudGoster() {
  const bar = readerBar();
  if (bar) bar.classList.remove("hud-gizli");
  hudSonY = Math.max(0, window.scrollY);
}

export function onReaderScroll() {
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
export function scrollToChapterRatio(e, ratio) {
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

/* Sözlükten gelen KÖKEN odağı: cümleye kaydır, vurgula, İngilizce karşılığını aç.

   Cümle `KOKEN_CUMLE_MAX` ile kırpılmış olabilir, o yüzden tam eşleşme aranmaz —
   baştan bir parçası (`ARAMA_ONEK`) yeter. Türkçe tarafta KARŞILIK, İngilizce
   tarafta KAYNAK terim vurgulanır: iki dil arasında cümle-düzeyi hizalama yok
   (işaretçiler PARAGRAF hizalıyor), ama kullanıcı zaten bir TERİMİN kökenine
   bakıyor ve aradığı şey o terimin iki dildeki geçişi. */
export const ARAMA_ONEK = 60;

/* Cümle içinde ARANAN TERİMİ ayrıca işaretle.

   Ölçülen gerçek vaka (shadow-slave bölüm 353): tek bölümde 16 terim var ve
   bazıları AYNI cümleden geliyor (nitelik/anı listeleri). Yalnız cümleyi
   vurgulamak o durumda hangi terime baktığını kaybettiriyordu. */
export function _terimIsaretle(parca, terim) {
  if (!terim) return escapeHtml(parca);
  const j = parca.toLowerCase().indexOf(String(terim).toLowerCase());
  if (j < 0) return escapeHtml(parca);
  return (
    escapeHtml(parca.slice(0, j)) +
    '<b class="koken-terim">' + escapeHtml(parca.slice(j, j + terim.length)) +
    "</b>" + escapeHtml(parca.slice(j + terim.length))
  );
}

export function _vurgula(host, aranan, terim) {
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
export function _terimliCumle(metin, terim) {
  if (!terim) return null;
  const t = terim.toLowerCase();
  for (const c of (metin || "").split(/(?<=[.!?…])\s+/)) {
    if (c.toLowerCase().includes(t)) return c.trim();
  }
  return null;
}

export function kokeneOdaklan(koken, url) {
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

/* ---------- okuyucu ---------- */
export function setStatus(message) {
  const s = el("status");
  s.replaceChildren();
  if (!message) {
    s.hidden = true;
    return;
  }
  s.hidden = false;
  s.textContent = message;
}

export function renderError(err, url, refresh) {
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
export async function loadChapter(url, opts = {}) {
  if (!url) return;
  const { refresh = false, restoreRatio = null, koken = null } = opts;
  isNavigating = true;
  isRestoring = true;
  el("readerError").hidden = true;

  const wasHidden = views.reader.hidden;
  if (wasHidden) showView("reader");
  closeFind();
  diyalogKapat("settingsPanel");
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
export function fetchChapterData(url, refresh, track = true, refetch = false) {
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

export function resetStream() {
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

// Bölüm listesinden (openBook doldurur) bir önceki bölümün url'i — server prev_url
// yoksa yedek (birleştirilmiş kitaplarda sayfa nav'ı eksik olabilir).
export function chapterListPrev(url) {
  if (durum.currentChapters && durum.currentChapters.length) {
    const idx = durum.currentChapters.findIndex((c) => c.url === url);
    if (idx > 0) return durum.currentChapters[idx - 1].url;
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
export let streamChapters = { slug: null, list: [] }; // akıştaki kitabın bölüm listesi

export function chapterListFor(slug) {
  if (!slug) return [];
  if (slug === durum.currentBookSlug && durum.currentChapters.length) return durum.currentChapters;
  return streamChapters.slug === slug ? streamChapters.list : [];
}

// Listeyi hazırla (yoksa çek). GET olduğu için SW çevrimdışıyken son kaydı verir;
// hiç kaydı yoksa boş liste → davranış eskisi gibi zincire düşer.
export async function ensureChapterList(slug) {
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
export function pickNextTarget(last) {
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
export function buildChapterEntry(url, data) {
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
    // Bu çeviride kullanılan sözlüğün sürümü (eski bölümlerde yok).
    sozlukSurumu: data.sozluk_surumu ?? null,
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
export function renderTranslatingPlaceholder(entry, done, total) {
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
export async function pollTranslating(entry) {
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
export function renderHtmlContent(entry) {
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
export function renderParagraphs(entry, query) {
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
export function appendKunye(entry, art) {
  const kart = kunyeKarti(entry);
  if (kart) art.appendChild(kart);
}

export function kunyeKarti(entry) {
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
    // Sözlük sürümü: bölüm çevrildikten sonra sözlük değiştiyse "bu bölümde eski
    // karşılıklar olabilir" sorusu buradan okunur.
    if (entry.sozlukSurumu != null) {
      satir.append(document.createTextNode(` · sözlük s.${entry.sozlukSurumu}`));
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

   Yazma yolu sözlük ekranıyla AYNI kuyruk (`saveTerm`/`terimiSilGeriAlinabilir`)
   → sunucu kapalıyken de çalışır, bağlanınca gönderilir. Kayıt durumu rozeti de
   aynı yerden çizilir (`data-sozluk-*` → `refreshGlossPendingUi`). */
export function kunyeTerimSatiri(entry, kaynak, karsilik) {
  const slug = entry.bookSlug || durum.currentBookSlug;
  const korunuyor = !karsilik || karsilik === kaynak;
  const li = document.createElement("li");
  li.className = "kunye-terim";
  if (slug) {
    li.dataset.sozlukSlug = slug;
    li.dataset.sozlukKaynak = kaynak;
  }
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
  });

  const sil = document.createElement("button");
  sil.className = "gloss-del";
  sil.textContent = "×";
  sil.setAttribute("aria-label", kaynak + " terimini sözlükten sil");
  const silindiIsaretle = (silindi) => {
    // Satır KALDIRILMAZ, üstü çizilir: GERİ AL basılınca yerinde geri gelebilsin.
    li.classList.toggle("kunye-terim-silindi", silindi);
    alan.disabled = silindi;
    sil.disabled = silindi;
  };
  sil.addEventListener("click", () => {
    if (!slug) return;
    silindiIsaretle(true);
    terimiSilGeriAlinabilir(slug, kaynak, { geriAlindi: () => silindiIsaretle(false) });
  });

  li.append(ad, ok, alan, sil);
  if (slug) tazelemeyiPlanla(); // bekleyen/hatalı kayıt rozeti
  return li;
}


export function emptyChapterCard(entry) {
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
export const PREFETCH_YOKLAMA_MS = 5000;
export const PREFETCH_YOKLAMA_MAX = 12; // ~60 sn; ölçülen çeviri süresi 15-45 sn

export function prefetchNext(entry) {
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
export async function isitVeKaydet(url, kalanDeneme) {
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
export function ensureBottomSentinel() {
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
export function refreshStreamEnd() {
  if (views.reader.hidden || !stream.length) return;
  ensureBottomSentinel();
}

// Akışın sonuna göre uygun kartı göster: next varsa "hazırlanıyor" ipucu (gözlemci
// birazdan ekler); web bölümü ama next yok → "SONRAKINI WEB'DEN GETİR"; sentetik/son
// → "— Son bölüm —".
export function updateEndCard() {
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

export async function maybeAppendNext() {
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
export async function goNextManual(btn) {
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
export async function discoverNextForLast(btn) {
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
export function ensureTopCard() {
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

export async function prependPrev(btn) {
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
export function sureliDugmeSayaci(btn, etiket) {
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

export async function retranslateChapter(entry, refetch = false) {
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
export let lastTapIdx = -1;
export let lastTapUrl = null;
export let lastTapAt = 0;

export function onParaTap(e) {
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
export function toggleSource(p, idx, url) {
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

export function insertSourceLine(p, text, extraClass) {
  const div = document.createElement("div");
  div.className = "source-line" + (extraClass ? " " + extraClass : "");
  div.textContent = text;
  p.after(div);
  return div;
}

export async function loadSourceForChapter(p, idx, url) {
  if (!url || sourceLoading) return;
  sourceLoading = true;
  const note = insertSourceLine(p, "İngilizce getiriliyor…", "source-loading");
  try {
    const res = await fetch(`/api/chapter?url=${encodeURIComponent(url)}&source=1&track=0`);
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

export function appendHighlighted(p, text, q) {
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
export let findMatches = [];
export let findIndex = -1;
export let findTimer = null;

export function openFind() {
  el("findBar").hidden = false;
  el("findInput").focus();
}
// Arama AKTİF bölüme kapsanır (D-B9v2) — akıştaki tüm bölümleri taramaz.
export function closeFind() {
  el("findBar").hidden = true;
  el("findInput").value = "";
  findMatches = [];
  findIndex = -1;
  el("findCount").textContent = "";
  const e = activeEntry();
  if (e && e.loaded && !e.html) renderParagraphs(e, "");
}
export function runFind() {
  const q = el("findInput").value.trim();
  const e = activeEntry();
  if (!e || !e.loaded || e.html) return; // görsel içerikte (PDF/EPUB) arama yok
  renderParagraphs(e, q);
  findMatches = q ? Array.from(e.el.querySelectorAll("mark")) : [];
  findIndex = findMatches.length ? 0 : -1;
  updateFindUI();
  focusMatch();
}
export function updateFindUI() {
  if (findMatches.length) {
    el("findCount").textContent = `${findIndex + 1}/${findMatches.length}`;
  } else {
    el("findCount").textContent = el("findInput").value.trim() ? "0" : "";
  }
}
export function focusMatch() {
  for (const m of findMatches) m.classList.remove("find-active");
  if (findIndex >= 0 && findMatches[findIndex]) {
    const m = findMatches[findIndex];
    m.classList.add("find-active");
    m.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}
export function cycleFind(dir) {
  if (!findMatches.length) return;
  findIndex = (findIndex + dir + findMatches.length) % findMatches.length;
  updateFindUI();
  focusMatch();
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {
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

  // Statik ikonları SVG ile doldur (emoji yerine; aria-label butonda zaten var).
  el("findBtn").innerHTML = ICONS.search;
  el("settingsBtn").innerHTML = ICONS.sliders;
}
