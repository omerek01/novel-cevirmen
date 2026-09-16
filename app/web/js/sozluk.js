/* Sözlük: çevrimdışı yazma kuyruğu ve sözlük ekranı. */

import { durum, views } from "./durum.js";
import { navigate, showView } from "./gezinme.js";
import { fetchBooks } from "./kutuphane.js";
import { chapterListFor, ensureChapterList } from "./okuyucu.js";
import { el, markSegment } from "./temel.js";

/* ---------- sözlük ---------- */
/* Çevrimdışı düzenleme: her ekleme/değiştirme/silme ÖNCE localStorage kuyruğuna
   yazılır, sonra sunucuya gönderilmeye çalışılır. Sunucu (PC) kapalıyken kayıt
   telefonda durur ve bağlantı dönünce kendiliğinden gider. Çevrimiçiyken de aynı
   yol işler — tek kod yolu, "ağ var mı" dallanması yok.
   Biçim: { [slug]: { [source]: string | null } }   null = silinecek. */
export const LS_GLOSS_QUEUE = "novellink:glossQueue";

export function loadGlossQueue() {
  try {
    return JSON.parse(localStorage.getItem(LS_GLOSS_QUEUE)) || {};
  } catch {
    return {};
  }
}
export function saveGlossQueue(queue) {
  try {
    localStorage.setItem(LS_GLOSS_QUEUE, JSON.stringify(queue));
  } catch {}
}
export function queueGlossChange(slug, source, target) {
  const queue = loadGlossQueue();
  if (!queue[slug]) queue[slug] = {};
  queue[slug][source] = target; // null = silme
  saveGlossQueue(queue);
}
export function dropGlossChange(slug, source) {
  const queue = loadGlossQueue();
  if (!queue[slug]) return;
  delete queue[slug][source];
  if (Object.keys(queue[slug]).length === 0) delete queue[slug];
  saveGlossQueue(queue);
}
export function pendingGloss(slug) {
  return loadGlossQueue()[slug] || {};
}
export function pendingGlossCount() {
  return Object.values(loadGlossQueue()).reduce(
    (n, terms) => n + Object.keys(terms).length,
    0
  );
}
// Sunucudan (ya da service worker önbelleğinden) gelen listeye bekleyen değişiklikleri
// bindir → ekranda daima son hâl görünür, gönderilmiş gibi.
export function overlayGloss(slug, terms) {
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
export const GLOSS_WRITE_TIMEOUT = 8000;

export async function fetchWithTimeout(url, options, timeoutMs = GLOSS_WRITE_TIMEOUT) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function postTermNow(slug, source, target) {
  const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(slug)}/glossary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, target }),
  });
  return res.status;
}
export async function deleteTermNow(slug, source) {
  const res = await fetchWithTimeout(
    `/api/book/${encodeURIComponent(slug)}/glossary?source=${encodeURIComponent(source)}`,
    { method: "DELETE" }
  );
  return res.status;
}

export let glossFlushing = false;
/* Kuyruğu sunucuya boşalt. Her başarılı istekten SONRA kuyruktan düşer: akış
   ortasında bağlantı giderse gönderilenler tekrar gönderilmez. Ağ hatası =
   sıradakiler beklesin (dur). 4xx = istek bozuk, tekrar denemek düzeltmez → düş.
   Döner: ekranın tazelenmesi gerekip gerekmediği. */
export async function flushGlossQueue() {
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
export let glossFilter = "all";
export let glossQuery = "";
export let glossRows = {};       // kaynak -> {origin, created_at, first_chapter}
export let glossTermsSonHal = {}; // sunucudan gelen HAM eşleme (süzgeç yerelde yeniden çizer)
export let glossWarnPairs = [];  // [[a, b], …] yazım hatası olabilecek çiftler

/* `glossary.fold_term`'ün hafif JS eşi: yazım varyantından bağımsız karşılaştırma
   anahtarı. "İngilizce kalanlar" süzgeci sunucudaki tanımla AYNI olmalı — iki yerde
   iki tanım, aynı kayıt için farklı karar demektir. */
export function foldTerim(t) {
  return (t || "").trim().replace(/[\s\-_'’.·]+/g, "").toLocaleLowerCase("tr");
}

export function glossIngilizceKorunan(source, target) {
  return foldTerim(source) === foldTerim(target);
}

export function glossUyaranlar() {
  const kume = new Set();
  for (const cift of glossWarnPairs) for (const ad of cift) kume.add(ad);
  return kume;
}

export function glossSatirGecer(source, target) {
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

export async function fetchGlossary(slug) {
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
export function saveTerm(slug, source, target) {
  queueGlossChange(slug, source, target);
  updateGlossPendingNote();
  flushGlossQueue().then(refreshGlossPendingUi);
}
export function deleteTerm(slug, source) {
  queueGlossChange(slug, source, null);
  updateGlossPendingNote();
  flushGlossQueue().then(refreshGlossPendingUi);
}

// Gönderim bitince satır rozetlerini + bekleyen sayısını yerinde tazele (tam yeniden
// çizim yok: kullanıcı bir alanı düzenliyor olabilir).
export function refreshGlossPendingUi() {
  updateGlossPendingNote();
  const pending = pendingGloss(durum.currentBookSlug);
  for (const row of document.querySelectorAll("#glossList .gloss-row")) {
    const src = row.querySelector(".gloss-source");
    if (src) row.classList.toggle("gloss-row-pending", src.textContent in pending);
  }
}

export async function openGlossary(slug) {
  durum.currentBookSlug = slug;
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
    if (durum.currentBookSlug === slug && !views.glossary.hidden) {
      renderGlossary(await fetchGlossary(slug));
    } else {
      refreshGlossPendingUi();
    }
  });
}

// Bekleyen (henüz sunucuya gitmemiş) düzenlemeleri sözlük ekranının başında duyur.
export function updateGlossPendingNote() {
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
export function updateGlossWarnNote() {
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

export function updateGlossCount(gosterilen, toplam) {
  const note = el("glossCount");
  if (!note) return;
  const suzuluyor = gosterilen !== toplam;
  note.hidden = toplam === 0;
  note.textContent = suzuluyor
    ? `${toplam} terimden ${gosterilen} tanesi gösteriliyor`
    : `${toplam} terim`;
}

export function renderGlossary(terms) {
  const list = el("glossList");
  list.replaceChildren();
  updateGlossPendingNote();
  updateGlossWarnNote();
  const pending = pendingGloss(durum.currentBookSlug);
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
      saveTerm(durum.currentBookSlug, source, tgt.value.trim() || source);
      row.classList.add("gloss-row-pending"); // gönderim bitince kendiliğinden kalkar
      gosterTerimEtkisi(row, source);
    });

    const del = document.createElement("button");
    del.className = "gloss-del";
    del.textContent = "×";
    del.setAttribute("aria-label", source + " sil");
    del.addEventListener("click", () => {
      row.remove();
      deleteTerm(durum.currentBookSlug, source);
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
export async function kokeneGit(no, cumle, source, target) {
  const slug = durum.currentBookSlug;
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
export async function addGlossTerm() {
  const source = el("glossSource").value.trim();
  if (!source) return el("glossSource").focus();
  const target = el("glossTarget").value.trim() || source;
  saveTerm(durum.currentBookSlug, source, target); // çevrimdışıysa kuyrukta bekler
  el("glossSource").value = "";
  el("glossTarget").value = "";
  renderGlossary(await fetchGlossary(durum.currentBookSlug));
  el("glossSource").focus();
}

/* ---------- yedek / toplu düzenleme ----------
   Sözlük tek bir PC'deki tek bir SQLite dosyasında yaşıyor; yedeği yoktu. Dışa
   aktarma düz bir indirme bağlantısı (sunucu Content-Disposition ile gönderiyor),
   içe aktarma dosyayı okuyup uca POST ediyor. */
export function setGlossIoState(text) {
  const node = el("glossIoState");
  if (node) node.textContent = text || "";
}

export function refreshGlossExportLink(slug) {
  const link = el("glossExportBtn");
  if (!link) return;
  link.href = `/api/book/${encodeURIComponent(slug)}/glossary/export`;
}

/* Terim düzeltildikten SONRA: "bu terim çevrilmiş N bölümde geçiyor".
   Ekranın ipucu satırı "eski bölüm için Yeniden çevir" diyordu ama HANGİ
   bölümler olduğunu söylemiyordu; kullanıcı elle aramak zorundaydı. */
export async function gosterTerimEtkisi(row, source) {
  if (!durum.currentBookSlug) return;
  let satir = row.nextElementSibling;
  if (!satir || !satir.classList.contains("gloss-impact")) {
    satir = document.createElement("p");
    satir.className = "gloss-impact";
    row.after(satir);
  }
  satir.textContent = "Etkilenen bölümler aranıyor…";
  try {
    const res = await fetch(
      `/api/book/${encodeURIComponent(durum.currentBookSlug)}/glossary/impact` +
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
export function yenidenSuz() {
  if (!durum.currentBookSlug || views.glossary.hidden) return;
  renderGlossary(overlayGloss(durum.currentBookSlug, glossTermsSonHal));
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {
  el("glossAddBtn").addEventListener("click", addGlossTerm);

  el("glossImportBtn")?.addEventListener("click", () => el("glossImportFile")?.click());

  el("glossImportFile")?.addEventListener("change", async (e) => {
    const dosya = e.target.files && e.target.files[0];
    e.target.value = ""; // aynı dosya ikinci kez seçilebilsin
    if (!dosya || !durum.currentBookSlug) return;
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
        `/api/book/${encodeURIComponent(durum.currentBookSlug)}/glossary/import`,
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
      renderGlossary(await fetchGlossary(durum.currentBookSlug));
    } catch (err) {
      setGlossIoState("Yüklenemedi (" + err.message + ") — sunucu açıkken tekrar dene.");
    }
  });
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
    if (durum.currentBookSlug && !views.glossary.hidden) {
      renderGlossary(await fetchGlossary(durum.currentBookSlug));
    } else {
      updateGlossPendingNote();
    }
  });
}
