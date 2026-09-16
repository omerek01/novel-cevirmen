/* Çevrimdışı: service worker önbelleği yardımcıları, otomatik ve elle indirme. */

import { bildir } from "./bildirim.js";
import { diyalogAc, diyalogAcikMi, diyalogKapat } from "./diyalog.js";
import { durum, views } from "./durum.js";
import { openBook, pollBulk } from "./kitap.js";
import { fetchBooks } from "./kutuphane.js";
import { chapterListFor } from "./okuyucu.js";
import { ICONS, el } from "./temel.js";
import { onbellekBayatMi } from "./terim-yardimci.js";

export let offlineStop = false;
/* Elle "çevrimdışı indir" sürüyor mu. Otomatik tarama buna bakıp çekilir.
   Eskiden ilerleme penceresinin GÖRÜNÜRLÜĞÜNE bakılıyordu; pencere artık Escape
   ile kapatılabiliyor ve indirme arka planda sürüyor — görünürlük "sürüyor"
   demek değil. */
export let elleIndirmeSuruyor = false;

/* ---------- bölüm silme ---------- */
// SW, /api/chapter yanıtlarını kalıcı önbelleğe alır (çevrimdışı okuma). Sunucudan
// silinen bölümün SW kopyası da kalksın ki listede/okuyucuda hayalet kalmasın.
export async function purgeChapterFromSwCache(url) {
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

/* Önbellekteki her bölüm kopyasının İNDİRİLDİĞİ an (yanıtın Date başlığı, ms).
   TAZELİK için: bölüm başka bir cihazdan (ya da toplu yeniden çeviriyle) sunucuda
   yeniden çevrilince telefondaki kopya kendiliğinden değişmiyordu — kullanıcı
   düzeltilmiş bölümün ESKİ hâlini okumaya devam ediyordu. */
export async function onbellekTarihleri() {
  if (!("caches" in window)) return null;
  try {
    const out = new Map();
    for (const key of await caches.keys()) {
      const c = await caches.open(key);
      for (const req of await c.keys()) {
        const u = new URL(req.url);
        const v = u.pathname === "/api/chapter" ? u.searchParams.get("url") : null;
        if (!v) continue;
        const res = await c.match(req);
        const t = res ? Date.parse(res.headers.get("date") || "") : NaN;
        // Aynı bölümün birden çok girdisi (source=1) olabilir: EN ESKİSİ belirleyicidir.
        const onceki = out.get(v);
        out.set(v, onceki === undefined ? t : Math.min(onceki, t) || onceki);
      }
    }
    return out;
  } catch {
    return null;
  }
}

/* Kopyası bayat bölümü sil ve yeniden indir. */
async function tazele(url) {
  await purgeChapterFromSwCache(url);
  await warmOffline(url);
}

// Tek bölümü önbelleğe çek. Yanıt gövdesi okunmaz — tek amaç SW'nin girdiyi
// yazması. Çevrimdışıysa/sunucu kapalıysa sessiz geç: ısıtma en iyi çabadır.
export async function warmOffline(url) {
  try {
    await fetch(`/api/chapter?url=${encodeURIComponent(url)}&track=0`);
  } catch {}
}

// Kitabın ÇEVRİLMİŞ ama telefonda olmayan bölümlerini arka planda, sırayla indir.
// Sıralı: paralel istek sunucudaki tek çekim kapısını (fetch._FETCH_GATE) ve
// okuyucunun canlı isteğini bekletirdi. Liste `/api/book/{slug}/chapters`ten gelir
// ve YALNIZ çevrilmiş bölümleri içerir (cache.list_chapters), yani bu GET'ler
// önbellek isabetidir — hiçbiri yeni çeviri tetiklemez.
export async function otoCevrimdisiKaydet(slug, liste) {
  const list = liste || chapterListFor(slug);
  if (!list || !list.length) return;
  const tarihler = await onbellekTarihleri();
  if (!tarihler) return;
  for (const ch of list) {
    if (durum.currentBookSlug !== slug) return; // başka kitaba geçildi: peşine düşme
    if (!ch.url || ch.translated === false) continue;
    if (!tarihler.has(ch.url)) await warmOffline(ch.url);
    else if (onbellekBayatMi(tarihler.get(ch.url), ch.ceviri_zamani)) await tazele(ch.url);
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
export let otoIndirmeCalisiyor = false;

export function otoIndirmeDurum(metin) {
  const satir = el("autoOffline");
  if (!satir) return;
  satir.textContent = metin || "";
  satir.hidden = !metin;
}

export async function otoIndirmeTur() {
  // TEK UÇUŞ: kütüphane her yenilendiğinde (anket, filtre, geri dönüş) yeniden
  // başlasaydı aynı bölümler üst üste indirilirdi.
  if (otoIndirmeCalisiyor) return;
  // Elle indirme açıksa karışma: ikisi aynı bölümleri çekip sunucuyu iki katına
  // çıkarır ve ilerleme sayısı yanlış görünürdü.
  if (elleIndirmeSuruyor) return;
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
    const tarihler = await onbellekTarihleri();
    if (!tarihler) return; // caches API yok: otomatik kayıt sessizce devre dışı

    // ÖNCE eksikleri say, sonra indir: "3/48" diyebilmek için toplamı bilmek
    // gerekiyor ve sayım, önbellek isabetleri olduğu için ucuz.
    const eksikler = [];
    for (const b of books) {
      for (const ch of await chaptersOf(b.slug)) {
        // `translated` LOAD-BEARING: cevirisi olmayan bolumu GET'lemek CEVIRI
        // TETIKLER ve ucretli model seciliyken PARA harcar. Otomatik bir tarama
        // bunu asla yapmamali — dugmenin adi da isin adi da "indir".
        if (!ch.url || ch.translated === false) continue;
        // Eksik YA DA bayat (sunucuda sonradan yeniden çevrilmiş) kopya.
        if (!tarihler.has(ch.url) || onbellekBayatMi(tarihler.get(ch.url), ch.ceviri_zamani)) {
          eksikler.push(ch.url);
        }
      }
    }
    if (!eksikler.length) return;

    let indi = 0;
    for (const url of eksikler) {
      // Çevrimdışına düşülürse ya da kullanıcı elle indirmeyi başlatırsa BIRAK.
      if (navigator.onLine === false || elleIndirmeSuruyor) break;
      otoIndirmeDurum(`${indi + 1}/${eksikler.length} bölüm çevrimdışına alınıyor…`);
      if (tarihler.has(url)) await tazele(url);
      else await warmOffline(url);
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

/* ---------- kitap sayfası: çevrimdışı durum kartı ----------
   Belge bulgusu: telefona kaç bölümün indiği, ne kadar yer tuttuğu ve tarayıcının
   onları silip silemeyeceği hiçbir yerde görünmüyordu. Sayılar SW önbelleğinden
   okunur (sunucuya gitmez, çevrimdışı da çalışır). Boyut `content-length`
   başlığından gelir: gövdeyi okumak yüzlerce bölümde belleği şişirirdi. */
export async function kitapOnbellekOzeti(urller) {
  if (!("caches" in window)) return null;
  const hedef = new Set(urller);
  const bulunan = new Set();
  let bayt = 0;
  let bilinmeyen = 0;
  let son = 0;
  try {
    for (const key of await caches.keys()) {
      const c = await caches.open(key);
      for (const req of await c.keys()) {
        const u = new URL(req.url);
        const v = u.pathname === "/api/chapter" ? u.searchParams.get("url") : null;
        if (!v || !hedef.has(v)) continue;
        const res = await c.match(req);
        if (!res) continue;
        const uzunluk = Number(res.headers.get("content-length"));
        if (uzunluk > 0) bayt += uzunluk;
        else bilinmeyen++;
        const zaman = Date.parse(res.headers.get("date") || "");
        if (zaman > son) son = zaman;
        bulunan.add(v);
      }
    }
  } catch {
    return null;
  }
  return { adet: bulunan.size, bayt, bilinmeyen, son: son || null };
}

function boyutYaz(bayt) {
  if (bayt < 1048576) return Math.max(1, Math.round(bayt / 1024)) + " KB";
  return (bayt / 1048576).toLocaleString("tr-TR", { maximumFractionDigits: 1 }) + " MB";
}

/* `navigator.storage.persist()` bir İSTEKTİR, garanti değil: tarayıcı reddedebilir
   ve sonucu olduğu gibi söylenir. */
async function kaliciDurumuYaz(istekSonucu) {
  const satir = el("offlineCardKalici");
  const btn = el("offlinePersistBtn");
  if (!satir || !btn) return;
  if (!navigator.storage || !navigator.storage.persisted) {
    satir.textContent = "";
    btn.hidden = true;
    return;
  }
  let kalici = false;
  try {
    kalici = await navigator.storage.persisted();
  } catch {}
  satir.textContent = kalici
    ? "Kalıcı depolama açık: tarayıcı yer daralınca indirilen bölümleri kendiliğinden silmez."
    : istekSonucu === false
      ? "Tarayıcı kalıcı depolamayı vermedi (istek garanti değil) — yer daralırsa bölümler silinebilir."
      : "Kalıcı depolama kapalı — tarayıcı yer daralınca indirilen bölümleri silebilir.";
  btn.hidden = kalici || !navigator.storage.persist;
}

export async function cevrimdisiKartiCiz(slug, chapters) {
  const kart = el("offlineCard");
  if (!kart) return;
  if (!window.isSecureContext || !("caches" in window)) {
    kart.hidden = false;
    el("offlineCardOzet").textContent =
      "Bu adreste çevrimdışı kayıt yok: güvenli bağlantı (https://…ts.net) gerekiyor.";
    el("offlineCardKalici").textContent = "";
    el("offlinePersistBtn").hidden = true;
    return;
  }
  const cevrili = (chapters || []).filter((c) => c.url && c.translated !== false);
  const ozet = await kitapOnbellekOzeti(cevrili.map((c) => c.url));
  if (durum.currentBookSlug !== slug) return;
  if (!ozet) {
    kart.hidden = true;
    return;
  }
  const parcalar = [`Telefonda ${ozet.adet}/${cevrili.length} çevrilmiş bölüm`];
  if (ozet.bayt) parcalar.push("≈ " + boyutYaz(ozet.bayt) + (ozet.bilinmeyen ? "+" : ""));
  if (ozet.son) {
    parcalar.push(
      "son indirme " +
        new Date(ozet.son).toLocaleString("tr-TR", {
          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
        })
    );
  }
  el("offlineCardOzet").textContent = parcalar.join(" · ");
  kart.hidden = false;
  await kaliciDurumuYaz();
}

export async function chaptersOf(slug) {
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/chapters`);
    const data = await res.json();
    return data.chapters || [];
  } catch {
    return [];
  }
}

export async function startOfflineDownloadAll() {
  const books = await fetchBooks();
  if (books.length === 0) return;
  await runOfflineDownload(books.map((b) => b.slug));
}

export async function runOfflineDownload(slugs) {
  const groups = [];
  let total = 0;
  for (const slug of slugs) {
    // Cevirisi olmayan bolum ELENIR: "cevrimdisi indir" indirmedir, cevirtme
    // degil — GET'lemek ceviri tetikler ve ucretli modelde para harcardi.
    const chs = (await chaptersOf(slug)).filter((c) => c.translated !== false);
    groups.push(chs);
    total += chs.length;
  }

  diyalogAc("offlineProgress");
  if (total === 0) {
    el("offlineStop").disabled = true;
    el("offlineProgressText").textContent = "İndirilecek çevrilmiş bölüm yok.";
    setTimeout(() => {
      diyalogKapat("offlineProgress");
      el("offlineStop").disabled = false;
    }, 1800);
    return;
  }

  offlineStop = false;
  elleIndirmeSuruyor = true;
  el("offlineStop").disabled = false;
  el("offlineProgressText").textContent = "Hazırlanıyor…";

  let done = 0;
  let failed = 0;
  outer: for (const chs of groups) {
    for (const ch of chs) {
      if (offlineStop) break outer;
      el("offlineProgressText").textContent = `${done + failed + 1} / ${total} indiriliyor…`;
      try {
        // track=0: indirmek OKUMAK değildir; konum son indirilen bölüme kaymasın.
        const r = await fetch(`/api/chapter?url=${encodeURIComponent(ch.url)}&track=0`);
        if (r.ok) done++;
        else failed++;
      } catch {
        failed++;
      }
    }
  }

  elleIndirmeSuruyor = false;
  const tail = failed ? ` (${failed} başarısız)` : "";
  const ozet = offlineStop
    ? `Durduruldu. ${done}/${total} bölüm telefonda.`
    : `Bitti — ${done}/${total} bölüm telefonda${tail}.`;
  el("offlineProgressText").textContent = ozet;
  if (durum.currentBookSlug && !views.book.hidden) {
    cevrimdisiKartiCiz(durum.currentBookSlug, durum.currentChapters);
  }
  // Pencere Escape ile kapatıldıysa sonuç yine SÖYLENİR.
  if (!diyalogAcikMi("offlineProgress")) bildir(ozet);
  el("offlineStop").disabled = true;
  setTimeout(() => {
    diyalogKapat("offlineProgress");
    el("offlineStop").disabled = false;
  }, 2200);
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {

  /* ---------- çevrimdışı indir ---------- */
  el("offlineBtn")?.addEventListener("click", () => {
    if (durum.currentBookSlug) runOfflineDownload([durum.currentBookSlug]);
  });
  el("offlineAllBtn")?.addEventListener("click", startOfflineDownloadAll);
  el("offlinePersistBtn")?.addEventListener("click", async () => {
    let sonuc = false;
    try {
      sonuc = await navigator.storage.persist();
    } catch {}
    kaliciDurumuYaz(sonuc);
  });
  el("offlineStop")?.addEventListener("click", () => {
    offlineStop = true;
  });
  el("offlineAllBtn").innerHTML = ICONS.download + " HEPSİNİ ÇEVRİMDIŞI İNDİR";
}
