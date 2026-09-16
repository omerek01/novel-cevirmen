/* Kitap sayfası: bölüm listesi, toplu çeviri, birleştirme, silme, bölüm ekleme, ePub. */

import { diyalogAc, diyalogAcikMi, diyalogKapat } from "./diyalog.js";
import { chaptersOf, otoCevrimdisiKaydet, otoIndirmeTur, purgeChapterFromSwCache } from "./cevrimdisi.js";
import { durum, views } from "./durum.js";
import { navigate, showView } from "./gezinme.js";
import { resolveResume } from "./konum.js";
import { fetchBookJob, fetchBooks } from "./kutuphane.js";
import { chapterListPrev, pickNextTarget } from "./okuyucu.js";
import { el, isSyntheticSlug, markSegment } from "./temel.js";

export let bulkPollTimer = null;

/* ---------- kitap (bölüm listesi) ---------- */
export async function openBook(slug) {
  durum.currentBookSlug = slug;
  const books = await fetchBooks();
  durum.currentBook = (books || []).find((b) => b.slug === slug) || null;
  el("bookTitle").textContent = durum.currentBook ? durum.currentBook.title : slug;
  markSegment("status", (durum.currentBook && durum.currentBook.status) || "okunuyor", "data-status-opt");

  const resume = el("resumeBtn");
  const target = resolveResume(durum.currentBook, slug);
  if (target.url) {
    // Liste vurgusu ("current") ve resume aynı bölümü göstersin (çevrimdışı okunan da).
    if (durum.currentBook) durum.currentBook.current_url = target.url;
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
    durum.currentChapters = data.chapters || [];
    applyChapterFilter();
    // Beklemeden: toplu çeviriyle hazırlanmış bölümler de "çevrimdışı indir"
    // düğmesine basılmadan telefona insin. Toplu iş bitince openBook zaten
    // yeniden çağrılıyor, yani yeni bölümler o turda yakalanır.
    otoCevrimdisiKaydet(slug, durum.currentChapters);
  } catch {
    list.replaceChildren();
    const err = document.createElement("p");
    err.className = "loading-row";
    err.textContent = "Bölümler yüklenemedi.";
    list.appendChild(err);
  }
}

// Saf: başlık veya bölüm numarasına göre filtrele (test edilebilir).
export function filterChapters(list, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return list;
  return list.filter(
    (c) =>
      (c.title || "").toLowerCase().includes(q) ||
      String(c.chapter_no || "").includes(q)
  );
}

export function applyChapterFilter() {
  const q = el("chapterSearch").value;
  renderChapterList(filterChapters(durum.currentChapters, q), durum.currentBook, q);
}

export function renderChapterList(chapters, book, query) {
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
  // YALNIZ çizim anında yapılır — `durum.currentChapters` mantıksal kaynak olarak ARTAN
  // kalmak zorunda, çünkü akış devamı ondan türetiliyor (`chapterListPrev` idx-1 =
  // önceki, `pickNextTarget` idx+1 = sonraki). Listeyi ters SAKLAMAK sonsuz okumayı
  // sessizce geriye çevirirdi. `slice()` de load-bearing: `filterChapters` boş
  // sorguda dizinin KENDİSİNİ döndürür ve `reverse()` yerinde çalışır — kopyasız
  // tersleme `durum.currentChapters`ı kalıcı olarak bozardı.
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

export async function deleteChapter(ch) {
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
  durum.currentChapters = durum.currentChapters.filter((c) => c.url !== ch.url);
  // Silinen bölüm "kaldığın yer" ise sunucu işareti temizledi; devam düğmesini gizle.
  if (durum.currentBook && durum.currentBook.current_url === ch.url) {
    durum.currentBook.current_url = null;
    el("resumeBtn").hidden = true;
  }
  applyChapterFilter();
}

/* ---------- toplu çeviri (sunucu-taraflı arka plan iş) ---------- */
// Kullanıcının "Arka Plana Al" dediği iş: ilerleme ekranı bir daha kendiliğinden
// açılmaz (discoverBulkJob buna bakar). TOPLU ÇEVİR düğmesi yeniden açabilir.
export let bulkDismissedJobId = null;
// Ekranın ŞU AN hangi işi gösterdiği. Uçuştaki eski bir anket yanıtı (iş A),
// araya yeni iş (B) girdiyse B'nin ilerlemesini ezmesin diye her await sonrası
// bu belirteçle doğrulanır.
export let bulkActiveJobId = null;
export let bulkDoneTimer = null;

export function hideBulkToBackground(jobId) {
  bulkDismissedJobId = jobId;
  bulkActiveJobId = null;
  clearTimeout(bulkPollTimer);
  clearTimeout(bulkDoneTimer);
  diyalogKapat("bulkProgress");
}

export async function startBulk(count) {
  // QA bulgusu: iş KALDIĞIN yerden değil, kitabın EN SON ÇEVRİLMİŞ bölümünden
  // ileriye başlamalı (okuma konumu geride olabilir; çevrili aralığı yeniden
  // gezmek kafa karıştırıyordu). Son çevrili bölüm start alınır — önbellekte
  // olduğu için iş onu API harcamadan atlar ve sonrasına geçer. Hiç çevrili
  // bölüm yoksa okuma konumuna düşülür (yeni kitap).
  let url = null;
  const chapters =
    durum.currentChapters && durum.currentChapters.length
      ? durum.currentChapters
      : await chaptersOf(durum.currentBookSlug);
  if (chapters.length) {
    const last = chapters.reduce((a, b) =>
      (b.chapter_no || 0) > (a.chapter_no || 0) ? b : a
    );
    url = last.url;
  } else {
    const book =
      durum.currentBook ||
      ((await fetchBooks()) || []).find((b) => b.slug === durum.currentBookSlug);
    url = book ? book.current_url : null;
  }
  if (!url) return;

  el("bulkProgressText").textContent = "Başlatılıyor…";
  el("bulkStop").disabled = false;
  diyalogAc("bulkProgress");

  let jobId;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(durum.currentBookSlug)}/bulk`, {
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
export function openBulkProgress(job) {
  el("bulkProgressText").textContent = job.message || "Hazırlanıyor…";
  el("bulkStop").disabled = false;
  diyalogAc("bulkProgress");
  el("bulkStop").onclick = () => {
    fetch(`/api/bulk/${job.id}/stop`, { method: "POST" }).catch(() => {});
  };
  el("bulkHide").onclick = () => hideBulkToBackground(job.id);
  pollBulk(job.id);
}

export async function discoverBulkJob(slug) {
  const job = await fetchBookJob(slug);
  if (!job || job.state !== "running" || slug !== durum.currentBookSlug || views.book.hidden) return;
  if (job.id === bulkDismissedJobId) return; // arka plana atıldı, kendiliğinden açılma
  openBulkProgress(job);
}

export function pollBulk(jobId) {
  clearTimeout(bulkPollTimer);
  clearTimeout(bulkDoneTimer);
  bulkActiveJobId = jobId;
  // Ekran kapandıysa VEYA ekran artık başka bir işi gösteriyorsa bu anket ölür.
  // Görünürlük tek başına yetmez: A işinin uçuştaki yanıtı, araya giren B işinin
  // açık ekranını "görünür" bulup B'nin ilerlemesini ezebilirdi.
  const stale = () => !diyalogAcikMi("bulkProgress") || bulkActiveJobId !== jobId;
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
      const jobSlug = durum.currentBookSlug;
      bulkDoneTimer = setTimeout(() => {
        if (stale()) return;
        diyalogKapat("bulkProgress");
        bulkActiveJobId = null;
        if (jobSlug && jobSlug === durum.currentBookSlug && !views.book.hidden) {
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

/* ---------- bu kitaba bölüm ekle (metin yapıştır / web adresinden çek) ---------- */
export let chAddTab = "paste";

export function setChAddTab(tab) {
  chAddTab = tab;
  document.querySelectorAll("#chapterAddModal .seg[data-chadd-tab]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.chaddTab === tab))
  );
  el("chAddPaste").hidden = tab !== "paste";
  el("chAddUrl").hidden = tab !== "url";
}

export function openChapterAddModal() {
  if (!durum.currentBookSlug) return;
  const synth = isSyntheticSlug(durum.currentBookSlug);
  // Sentetik (içe aktarılan) kitapta metin URL'siz eklenir; web kitabında bölümün
  // gerçek adresi gerekir (o adrese kaydedilir → kitap web-yerli kalır).
  el("chAddPasteUrl").hidden = synth;
  el("chAddPasteHint").textContent = synth
    ? "Bu içe aktarılan kitaba yeni bölüm eklenir (sıradaki numara)."
    : "Takılan/eksik bir bölümün metnini, o bölümün web adresiyle yapıştır. Kitap web bağlantısını korur.";
  ["chAddPasteUrl", "chAddTitle", "chAddText", "chAddFetchUrl"].forEach((id) => (el(id).value = ""));
  setChAddTab("paste");
  diyalogAc("chapterAddModal");
}

export async function submitChapterAdd() {
  if (!durum.currentBookSlug) return;
  const btn = el("chAddConfirm");
  const synth = isSyntheticSlug(durum.currentBookSlug);
  let endpoint, body, slow = false;
  if (chAddTab === "url") {
    const url = el("chAddFetchUrl").value.trim();
    if (!/^https?:\/\//.test(url)) return el("chAddFetchUrl").focus();
    endpoint = `/api/book/${encodeURIComponent(durum.currentBookSlug)}/fetch-next`;
    body = { url };
    slow = true; // çekme + çeviri sürebilir
  } else {
    const text = el("chAddText").value.trim();
    if (!text) return el("chAddText").focus();
    const title = el("chAddTitle").value.trim() || null;
    if (synth) {
      endpoint = "/api/import/paste";
      body = { slug: durum.currentBookSlug, text, title: title || "Bölüm" };
    } else {
      const url = el("chAddPasteUrl").value.trim();
      if (!/^https?:\/\//.test(url)) {
        el("chAddPasteUrl").focus();
        return alert("Bu bölümün web adresini (URL) gir.");
      }
      endpoint = "/api/import/paste-url";
      body = { url, slug: durum.currentBookSlug, text, title };
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
    diyalogKapat("chapterAddModal");
    openBook(durum.currentBookSlug); // liste yenilensin, yeni bölüm görünsün
  } catch (e) {
    alert(String(e.message || e));
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

// Kitabı + tüm bölümlerini kalıcı sil. Boş/mükerrer kitapları raftan kaldırır
// (sentetik kitaplar merge edilemez ama silinebilir). Onay ister, geri alınamaz.
export async function deleteCurrentBook() {
  if (!durum.currentBookSlug) return;
  const name = (durum.currentBook && durum.currentBook.title) || durum.currentBookSlug;
  const n = durum.currentChapters ? durum.currentChapters.length : 0;
  const detail = n ? `\n${n} bölüm ve sözlüğü de silinir.` : "";
  if (!confirm(`"${name}" kitabı kalıcı olarak silinsin mi?${detail}\nBu işlem geri alınamaz.`)) return;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(durum.currentBookSlug)}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error();
    history.back(); // silinen kitap görünümünden bir üste (kütüphane) dön — geçmişi büyütme
  } catch {
    alert("Silme başarısız — sunucuya ulaşılamadı.");
  }
}

export async function openMergeModal() {
  if (!durum.currentBookSlug) return;
  const books = (await fetchBooks()).filter((b) => b.slug !== durum.currentBookSlug);
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
  diyalogAc("mergeModal");
}

export async function confirmMerge(target) {
  const ok = window.confirm(
    `Bu kitap "${target.title}" ile birleştirilsin mi?\n` +
      "Bölümleri ve sözlüğü ona taşınacak; bu kitap listeden kalkacak."
  );
  if (!ok) return;
  const source = durum.currentBookSlug;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(source)}/merge-into`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: target.slug }),
    });
    const data = await res.json();
    diyalogKapat("mergeModal");
    durum.currentBookSlug = data.canonical || target.slug;
    // Mevcut book kaydını kanonik slug'la güncelle (birleşmeyle eski slug kaybolabilir).
    history.replaceState({ view: "book", slug: durum.currentBookSlug }, "");
    openBook(durum.currentBookSlug);
  } catch {
    diyalogKapat("mergeModal");
  }
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {
  // Escape = "Arka Plana Al": iş sunucuda sürer, pencere yalnız gizlenir. Varsayılan
  // kapanış anketi sahipsiz bırakırdı (ekran kapalıyken durum yazmaya çalışırdı).
  el("bulkProgress").addEventListener("cancel", (e) => {
    e.preventDefault();
    el("bulkHide").click();
  });
  // D-B12: durum düzenleme kitap görünümünde. İyimser güncelle; sunucu reddederse
  // eski değere dön (kalıcı yanlış aria-pressed bırakma).
  document.querySelectorAll("[data-status-opt]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!durum.currentBookSlug) return;
      const status = b.getAttribute("data-status-opt");
      const prev = (durum.currentBook && durum.currentBook.status) || "okunuyor";
      if (status === prev) return;
      markSegment("status", status, "data-status-opt");
      try {
        const res = await fetch(
          `/api/book/${encodeURIComponent(durum.currentBookSlug)}/status`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          }
        );
        if (!res.ok) throw new Error();
        if (durum.currentBook) durum.currentBook.status = status;
      } catch {
        markSegment("status", prev, "data-status-opt");
      }
    })
  );
  el("openGlossaryBtn").addEventListener("click", () => {
    if (durum.currentBookSlug) navigate({ view: "glossary", slug: durum.currentBookSlug });
  });

  el("chapterSearch").addEventListener("input", applyChapterFilter);

  el("bulkBtn").addEventListener("click", async () => {
    // QA bulgusu: arka plana alınmış iş varken bu düğme başlatma modalını açıyordu.
    // Çalışan iş varsa doğrudan ilerleme/durdurma ekranı açılır (geri çağırma yolu).
    const job = durum.currentBookSlug ? await fetchBookJob(durum.currentBookSlug) : null;
    if (job && job.state === "running") {
      bulkDismissedJobId = null; // kullanıcı ekranı bilerek geri açtı
      openBulkProgress(job);
      return;
    }
    el("bulkCount").value = "10";
    diyalogAc("bulkModal");
  });
  el("bulkCancel").addEventListener("click", () => {
    diyalogKapat("bulkModal");
  });

  el("bulkStart").addEventListener("click", () => {
    const n = Math.max(1, Math.min(500, parseInt(el("bulkCount").value, 10) || 0));
    diyalogKapat("bulkModal");
    startBulk(n);
  });

  /* ---------- kitap birleştir ---------- */
  el("mergeBtn")?.addEventListener("click", openMergeModal);
  el("deleteBookBtn")?.addEventListener("click", deleteCurrentBook);
  el("addChapterBtn")?.addEventListener("click", openChapterAddModal);
  el("chAddCancel")?.addEventListener("click", () => diyalogKapat("chapterAddModal"));
  el("chapterAddModal")?.addEventListener("click", (e) => {
    if (e.target === el("chapterAddModal")) diyalogKapat("chapterAddModal");
  });
  document.querySelectorAll("#chapterAddModal .seg[data-chadd-tab]").forEach((b) =>
    b.addEventListener("click", () => setChAddTab(b.dataset.chaddTab))
  );
  el("chAddConfirm")?.addEventListener("click", submitChapterAdd);
  el("mergeCancel")?.addEventListener("click", () => {
    diyalogKapat("mergeModal");
  });
  el("mergeModal")?.addEventListener("click", (e) => {
    if (e.target === el("mergeModal")) diyalogKapat("mergeModal");
  });

  /* ---------- ePub ---------- */
  el("epubBtn").addEventListener("click", () => {
    diyalogAc("epubModal");
  });
  el("epubCancel").addEventListener("click", () => {
    diyalogKapat("epubModal");
  });
  el("epubDownload").addEventListener("click", () => {
    if (!durum.currentBookSlug) return;
    const start = Math.max(1, parseInt(el("epubStart").value, 10) || 1);
    const count = Math.max(1, Math.min(2000, parseInt(el("epubCount").value, 10) || 1));
    diyalogKapat("epubModal");
    const url =
      `/api/book/${encodeURIComponent(durum.currentBookSlug)}/epub?start=${start}&count=${count}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
}
