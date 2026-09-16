/* Sözlük: çevrimdışı yazma kuyruğu ve sözlük ekranı. */

import { bildir } from "./bildirim.js";
import { durum, views } from "./durum.js";
import { navigate, showView } from "./gezinme.js";
import { fetchBooks } from "./kutuphane.js";
import { chapterListFor, ensureChapterList } from "./okuyucu.js";
import { anahtarla, kuyrukOlustur } from "./sozluk-kuyruk.js";
import { incelemeyiYukle, incelenecekler } from "./sozluk-inceleme.js";
import { terimPaneliAc } from "./terim-paneli.js";
import { el, markSegment } from "./temel.js";

/* ---------- sözlük: yazma kuyruğu ---------- */
/* Çevrimdışı düzenleme: her ekleme/değiştirme/silme ÖNCE kuyruğa yazılır, sonra
   sunucuya gönderilir. Sunucu kapalıyken kayıt cihazda durur ve bağlantı dönünce
   kendiliğinden gider. Çevrimiçiyken de aynı yol işler — tek kod yolu.
   Kuyruğun mantığı `sozluk-kuyruk.js`te (Node'da test edilir); burada yalnız
   tarayıcı bağdaştırıcıları ve ekran durumu var. */

// Alfabetik sıra: ekranda terim, sunucu yanıtının geldiği sırayla zıplamasın.
function sirala(terms) {
  return Object.fromEntries(
    Object.entries(terms).sort((a, b) => a[0].localeCompare(b[0], "tr", { sensitivity: "base" }))
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

function hataMesaji(govde, kod) {
  const d = govde && govde.detail;
  if (typeof d === "string") return d;
  if (d && typeof d.message === "string") return d.message;
  if (Array.isArray(d) && d[0] && d[0].msg) return d[0].msg; // FastAPI doğrulama hatası
  return `sunucu ${kod}`;
}

// İşlemi HTTP isteğine çevirir. Gövde okunamazsa (boş yanıt) durum kodu yeter.
async function islemiGonder(op) {
  const slug = encodeURIComponent(op.slug);
  let res;
  if (op.tur === "sil") {
    const taban = op.taban_surum !== undefined ? `&taban_surum=${op.taban_surum}` : "";
    res = await fetchWithTimeout(
      `/api/book/${slug}/glossary?source=${encodeURIComponent(op.source)}${taban}`,
      { method: "DELETE" }
    );
  } else if (op.tur === "geri") {
    // Geri alma TAM kaydı içe aktarma ucuyla yazar: koşul + köken geri gelir.
    res = await fetchWithTimeout(`/api/book/${slug}/glossary/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kayitlar: [op.kayit], strateji: "dosya" }),
    });
  } else {
    const govde = { source: op.source, target: op.target };
    if (op.kosul !== undefined) govde.kosul = op.kosul; // yok = sunucu koşulu korur
    if (op.ornek) govde.ornek = op.ornek; // okurken eklenen terimin kökeni (boşsa yazılır)
    if (op.taban_surum !== undefined) govde.taban_surum = op.taban_surum; // çakışma denetimi
    if (op.terim_turu !== undefined) govde.tur = op.terim_turu; // kisi/yer/… (prompt'a girmez)
    res = await fetchWithTimeout(`/api/book/${slug}/glossary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
    });
  }
  let govde = null;
  try {
    govde = await res.json();
  } catch {}
  const sonuc = { durum: res.status, govde, mesaj: res.ok ? "" : hataMesaji(govde, res.status) };
  // 409: sunucudaki güncel kayıt kuyruğa taşınır, kullanıcı iki değeri yan yana görür.
  if (res.status === 409 && govde && govde.detail && typeof govde.detail === "object") {
    sonuc.guncel = govde.detail.guncel ?? null;
  }
  return sonuc;
}

// localStorage erişimi bazı gizlilik kiplerinde getter'da bile FIRLATIR; kuyruk
// her çağrıyı kendi try'ında tutar, yani burada yakalamak gerekmez.
const tarayiciDepo = {
  oku: (k) => localStorage.getItem(k),
  yaz: (k, v) => localStorage.setItem(k, v),
  sil: (k) => localStorage.removeItem(k),
};

/* Başarılı gönderimlerin günlüğü. Bir GET, kendisinden SONRA tamamlanan bir
   gönderimi görmemiş olabilir: gönderim bitip liste tazelendikten sonra yola
   ÖNCE çıkmış bir GET yanıtı gelirse listeyi eski hâline döndürür ve terim yine
   kaybolurdu. `fetchGlossary` o gönderimleri GET sonucunun üstüne yeniden uygular. */
let gonderimSirasi = 0;
const sonGonderimler = []; // { sira, islem }
const SON_GONDERIM_MAX = 100;
// Az önce sunucuya ulaşan terimler: satırda kısa bir "KAYDEDİLDİ" görünür.
const sonKaydedilen = new Map(); // "slug\u0000anahtar" -> zaman
const KAYDEDILDI_MS = 2500;
const silinenKayitlar = new Map(); // silme işlem kimliği -> sunucudan dönen satır
const dinleyiciler = new Set();

export function kuyrukDinle(fn) {
  dinleyiciler.add(fn);
  return () => dinleyiciler.delete(fn);
}

function islemiUygula(terms, kosullar, op) {
  const kayitli = Object.keys(terms).find((s) => anahtarla(s) === anahtarla(op.source));
  const ad = kayitli === undefined ? op.source : kayitli;
  if (op.tur === "sil") {
    delete terms[ad];
    delete kosullar[ad];
  } else if (op.tur === "geri") {
    terms[ad] = op.kayit.target || op.kayit.source;
    if (op.kayit.kosul) kosullar[ad] = op.kayit.kosul;
    else delete kosullar[ad];
  } else {
    terms[ad] = op.target;
    if (op.kosul !== undefined) {
      if (op.kosul) kosullar[ad] = op.kosul;
      else delete kosullar[ad];
    }
  }
}

function kuyrukOlayi(ad, veri) {
  if (ad === "gonderildi") {
    const op = veri.islem;
    gonderimSirasi += 1;
    sonGonderimler.push({ sira: gonderimSirasi, islem: op });
    if (sonGonderimler.length > SON_GONDERIM_MAX) sonGonderimler.shift();
    sonKaydedilen.set(op.slug + "\u0000" + anahtarla(op.source), Date.now());
    setTimeout(refreshGlossPendingUi, KAYDEDILDI_MS + 50);
    if (op.tur === "sil" && veri.govde) silinenKayitlar.set(op.id, veri.govde.silinen || null);
    // Sunucu hâli TAZELENİR: gönderim bitip işlem kuyruktan düşünce süzgeç eski
    // listeden çizerse eklenen terim ekrandan kayboluyordu (duman testi buldu).
    if (op.slug === durum.currentBookSlug) {
      // Yazılan kaydın SÜRÜMÜ yerelde tazelenir: bir sonraki düzenlemenin çakışma
      // tabanı buradan okunur, eski tabanla kullanıcı kendi kaydıyla çakışırdı.
      if (veri.govde && veri.govde.kayit) glossRows[veri.govde.kayit.source] = veri.govde.kayit;
      if (op.tur === "sil") {
        const ad = Object.keys(glossRows).find((s) => anahtarla(s) === anahtarla(op.source));
        if (ad !== undefined) delete glossRows[ad];
      }
      if (veri.govde && veri.govde.terms) {
        glossTermsSonHal = veri.govde.terms;
        if (veri.govde.kosullar) glossKosullarSonHal = veri.govde.kosullar;
        else islemiUygula({ ...glossTermsSonHal }, glossKosullarSonHal, op);
      } else {
        islemiUygula(glossTermsSonHal, glossKosullarSonHal, op);
      }
    }
  }
  for (const fn of dinleyiciler) {
    try {
      fn(ad, veri);
    } catch (hata) {
      console.error(hata);
    }
  }
  refreshGlossPendingUi();
}

export const kuyruk = kuyrukOlustur({ depo: tarayiciDepo, gonder: islemiGonder, olay: kuyrukOlayi });

// Yeniden deneme: 429/5xx/ağ hatasında kuyruk bekler; uygulama açıkken giderek
// seyrekleşen aralıklarla tekrar dener (bağlantı dönünce `online` de tetikler).
const YENIDEN_DENEME_MS = [5000, 15000, 60000];
let yenidenDenemeAdimi = 0;
let yenidenDenemeZamanlayici = null;

/* Kuyruğu sunucuya boşalt. Döner: en az bir işlem gönderildi mi (liste tazelensin mi). */
export async function flushGlossQueue() {
  const sonuc = await kuyruk.bosalt();
  clearTimeout(yenidenDenemeZamanlayici);
  if (sonuc.yenidenDenenecek && sonuc.kaldi > 0 && navigator.onLine !== false) {
    const ms = YENIDEN_DENEME_MS[Math.min(yenidenDenemeAdimi, YENIDEN_DENEME_MS.length - 1)];
    yenidenDenemeAdimi += 1;
    yenidenDenemeZamanlayici = setTimeout(flushGlossQueue, ms);
  } else if (!sonuc.yenidenDenenecek) {
    yenidenDenemeAdimi = 0;
  }
  return sonuc.gonderilen > 0;
}

/* Bekleyen işlemleri sunucu listesine bindir: ekranda daima SON hâl görünür. */
export function overlayGloss(slug, terms, kosullar = {}) {
  const b = kuyruk.bindir(slug, terms, kosullar);
  return { terms: sirala(b.terms), kosullar: b.kosullar };
}

/* Terimin ekrandaki kayıt durumu. Metinler belge kararıyla SABİT: "Cihazda
   bekliyor / Sunucuya kaydedildi / Gönderilemedi" — kaydedilmemiş bir değer
   hiçbir zaman kaydedilmiş gibi görünmez. */
export function terimDurumu(slug, source, harita = null) {
  const anahtar = slug + "\u0000" + anahtarla(source);
  const d = harita ? harita.get(anahtar) || null : kuyruk.kaynakDurumu(slug, source);
  if (d === "hata") return { sinif: "hata", etiket: "GÖNDERİLEMEDİ" };
  if (d === "bekliyor") {
    return kuyruk.kalici()
      ? { sinif: "bekliyor", etiket: "CİHAZDA BEKLİYOR" }
      : { sinif: "bellekte", etiket: "KAYDEDİLMEDİ" };
  }
  const zaman = sonKaydedilen.get(anahtar);
  if (zaman && Date.now() - zaman < KAYDEDILDI_MS) return { sinif: "kaydedildi", etiket: "KAYDEDİLDİ" };
  return null;
}

/* ---------- sözlük süzme + yakın terim uyarısı ----------
   Sözlük 267 satıra çıkabiliyor; telefonda parmakla kaydırarak terim bulmak
   pratik değil. Süzme TAMAMEN istemci tarafında: sunucuya ek istek yok, çevrimdışı
   da çalışır (bekleyen kayıtlar `overlayGloss` ile listeye zaten karışıyor). */
export let glossFilter = "all";
export let glossQuery = "";
export let glossRows = {};       // kaynak -> {origin, created_at, first_chapter}
export let glossTermsSonHal = {}; // sunucudan gelen HAM eşleme (süzgeç yerelde yeniden çizer)
export let glossKosullarSonHal = {}; // sunucudan gelen HAM koşullar
export let glossWarnPairs = [];  // [[a, b], …] yazım hatası olabilecek çiftler
export let glossSurum = null; // kitabın sözlük sürümü (bölüm künyesiyle kıyaslanır)
export let glossEkler = {}; // kaynak -> {yazimlar, anlamlar} (yalnız eki olanlar)
export let glossTurSuzgeci = ""; // "" = hepsi

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
  if (glossTurSuzgeci && (glossRows[source] || {}).tur !== glossTurSuzgeci) return false;
  if (glossQuery) {
    const q = glossQuery.toLocaleLowerCase("tr");
    const alanlar = source + " " + (target || "");
    if (!alanlar.toLocaleLowerCase("tr").includes(q)) return false;
  }
  const kok = glossRows[source] || {};
  switch (glossFilter) {
    case "en":
      return glossIngilizceKorunan(source, target);
    case "tr":
      return !glossIngilizceKorunan(source, target);
    case "manual":
      return kok.origin === "manual";
    case "auto":
      return kok.origin === "auto";
    case "kosullu":
      return !!glossKosullarGorunen()[source];
    case "bolumde":
      return !!glossBolumde && glossBolumde.has(anahtarla(source));
    case "incelenecek":
      return incelenecekler.has(anahtarla(source));
    case "esitlenmeyen": {
      const d = kuyruk.kaynakDurumu(durum.currentBookSlug, source);
      return d === "bekliyor" || d === "hata";
    }
    default:
      return true;
  }
}

function glossKosullarGorunen() {
  return overlayGloss(durum.currentBookSlug, glossTermsSonHal, glossKosullarSonHal).kosullar;
}

/* "Bu bölümde geçenler": kitabın OKUMA KONUMUNDAKİ bölümün kaynak metninde geçen
   terimler (sunucu `?bolum=` ile hesaplar — eşleştirme ölçütü çeviri yoluyla aynı).
   Kümeye yazım varyantından bağımsız anahtarla girilir. */
export let glossBolumde = null; // Set | null
export let glossBolumdeNot = "";

async function bolumdeGecenleriYukle() {
  glossBolumde = null;
  const slug = durum.currentBookSlug;
  const url = durum.currentBook && durum.currentBook.current_url;
  if (!url) {
    glossBolumdeNot = "Bu kitapta okuma konumu yok — önce bir bölüm aç.";
    return;
  }
  glossBolumdeNot = "Okuduğun bölümdeki terimler aranıyor…";
  yenidenSuz();
  try {
    const res = await fetch(
      `/api/book/${encodeURIComponent(slug)}/glossary?bolum=${encodeURIComponent(url)}`
    );
    const veri = await res.json();
    if (slug !== durum.currentBookSlug || glossFilter !== "bolumde") return;
    if (veri.bolumde == null) {
      glossBolumdeNot = "Okuduğun bölümün İngilizce kaynağı saklı değil — süzülemiyor.";
    } else {
      glossBolumde = new Set(veri.bolumde.map(anahtarla));
      glossBolumdeNot = `Okuduğun bölümde (${durum.currentBook.chapter_no ?? "?"}) geçenler.`;
    }
  } catch {
    glossBolumdeNot = "Sunucuya ulaşılamadı — bu süzgeç çevrimdışı çalışmaz.";
  }
}

export async function fetchGlossary(slug) {
  let terms = {};
  let kosullar = {};
  glossRows = {};
  glossWarnPairs = [];
  const istekSirasi = gonderimSirasi;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/glossary`);
    const data = await res.json();
    terms = data.terms || {};
    kosullar = data.kosullar || {};
    for (const satir of data.rows || []) glossRows[satir.source] = satir;
    glossWarnPairs = data.warnings || [];
    glossSurum = Number.isFinite(data.surum) ? data.surum : null;
    glossEkler = data.ekler || {};
  } catch {
    terms = {}; // çevrimdışı + hiç önbellek yok: yalnız bekleyen kayıtlar görünsün
  }
  // İstek yoldayken tamamlanan gönderimler bu yanıtta OLMAYABİLİR: üstüne uygula.
  for (const g of sonGonderimler) {
    if (g.sira > istekSirasi && g.islem.slug === slug) islemiUygula(terms, kosullar, g.islem);
  }
  // Süzgeç yeniden çizerken sunucuya GİTMEZ; ham liste burada saklanır.
  glossTermsSonHal = terms;
  glossKosullarSonHal = kosullar;
  return overlayGloss(slug, terms, kosullar).terms;
}
/* Kayıt ANINDA yereldir; gönderim arka planda. Sunucuyu beklemek, PC kapalıyken
   "Ekle" düğmesini saniyelerce dondururdu — kayıt zaten kuyrukta güvende.
   Döner: { id, kalici } — çağıran bu işlemin durumunu izleyebilir.
   `kosul`: undefined = sunucudaki koşul korunur, "" = temizlenir. */
export function saveTerm(slug, source, target, kosul, ornek, tabanSurum, terimTuru) {
  const alanlar = { tur: "yaz", target };
  if (terimTuru !== undefined) alanlar.terim_turu = terimTuru;
  if (kosul !== undefined) alanlar.kosul = kosul;
  if (ornek) alanlar.ornek = ornek;
  if (tabanSurum !== undefined) alanlar.taban_surum = tabanSurum;
  const sonuc = kuyruk.ekle(slug, source, alanlar);
  refreshGlossPendingUi();
  flushGlossQueue();
  return sonuc;
}
export function deleteTerm(slug, source, tabanSurum) {
  const alanlar = { tur: "sil" };
  if (tabanSurum !== undefined) alanlar.taban_surum = tabanSurum;
  const sonuc = kuyruk.ekle(slug, source, alanlar);
  refreshGlossPendingUi();
  flushGlossQueue();
  return sonuc;
}

/* Silme + GERİ AL bildirimi. Geri almanın üç hâli var:
     * silme henüz gönderilmedi  -> işlemden vazgeçilir, sunucuya hiçbir şey gitmez
     * silme uçuşta              -> bitmesi beklenir, sonra kayıt geri yazılır
     * silme gönderildi          -> sunucunun döndürdüğü TAM satır geri yazılır
   `geriAlindi`: ekranı eski hâline getiren geri çağrı (satırı geri koymak vb.). */
export function terimiSilGeriAlinabilir(slug, source, { geriAlindi = () => {}, tabanSurum } = {}) {
  const { id } = deleteTerm(slug, source, tabanSurum);
  bildir(`${source} sözlükten silindi.`, {
    eylem: { etiket: "GERİ AL", fn: () => silmeyiGeriAl(slug, source, id, geriAlindi) },
  });
  return id;
}

async function silmeyiGeriAl(slug, source, id, geriAlindi) {
  const bekliyor = kuyruk.islemler(slug).some((o) => o.id === id);
  if (bekliyor && kuyruk.ucustakiKimlik() !== id) {
    kuyruk.vazgec(id);
    geriAlindi();
    bildir(`${source} geri alındı.`);
    return;
  }
  if (bekliyor) {
    // Uçuşta: gönderimin sonucu (sunucunun döndürdüğü satır) gelene kadar bekle.
    await new Promise((coz) => {
      const birak = kuyrukDinle((ad, veri) => {
        if (veri && veri.islem && veri.islem.id === id && ad !== "eklendi") {
          birak();
          coz();
        }
      });
    });
  }
  const kayit = silinenKayitlar.get(id);
  if (!kayit) {
    bildir(`${source} geri alınamadı: sunucu silinen kaydı döndürmedi.`);
    return;
  }
  kuyruk.ekle(slug, kayit.source, { tur: "geri", kayit });
  geriAlindi();
  refreshGlossPendingUi();
  flushGlossQueue();
  bildir(`${source} geri alınıyor…`);
}

/* Aynı görev içinde birden çok satır kurulurken (künyede 10 terim) tazelemeyi
   TEK kez yap: her satır ayrı tarama isteseydi belge baştan sona 10 kez gezilirdi. */
let tazelemePlanli = false;
export function tazelemeyiPlanla() {
  if (tazelemePlanli) return;
  tazelemePlanli = true;
  queueMicrotask(() => {
    tazelemePlanli = false;
    refreshGlossPendingUi();
  });
}

// Kayıt durumlarını YERİNDE tazele (tam yeniden çizim yok: kullanıcı bir alanı
// düzenliyor olabilir). Sözlük satırları ve okuyucudaki künye satırları
// `data-sozluk-slug` + `data-sozluk-kaynak` taşır; hepsi tek yerden güncellenir.
export function refreshGlossPendingUi() {
  updateGlossPendingNote();
  // Kuyruk TEK kez okunur: satır başına okumak 500 terimlik listede 500 kez
  // depolama okuması + JSON ayrıştırması demekti. Aynı terimin son işlemi kazanır.
  const harita = new Map();
  for (const op of kuyruk.islemler()) harita.set(op.slug + "\u0000" + anahtarla(op.source), op.durum);
  for (const satir of document.querySelectorAll("[data-sozluk-kaynak]")) {
    const d = terimDurumu(satir.dataset.sozlukSlug, satir.dataset.sozlukKaynak, harita);
    satir.classList.toggle("gloss-row-pending", !!d && (d.sinif === "bekliyor" || d.sinif === "bellekte"));
    satir.classList.toggle("gloss-row-hata", !!d && d.sinif === "hata");
    let rozet = satir.querySelector(":scope > .gloss-durum");
    if (!d) {
      if (rozet) rozet.remove();
      continue;
    }
    if (!rozet) {
      rozet = document.createElement("span");
      rozet.className = "gloss-durum";
      const hedef = satir.querySelector(":scope > .gloss-source");
      if (hedef) hedef.after(rozet);
      else satir.prepend(rozet);
    }
    rozet.dataset.durum = d.sinif;
    rozet.textContent = d.etiket;
  }
}

export async function openGlossary(slug) {
  durum.currentBookSlug = slug;
  // Süzgeç kitapla birlikte sıfırlanır: başka kitaptan kalan bir süzgeç, bu kitabın
  // listesini sebepsiz boş gösterirdi.
  glossFilter = "all";
  glossQuery = "";
  glossTurSuzgeci = "";
  if (el("glossTurSuz")) el("glossTurSuz").value = "";
  if (el("glossSearch")) el("glossSearch").value = "";
  markSegment("glossFilter", "all", "data-gloss-filter");
  refreshGlossExportLink(slug);
  setGlossIoState("");
  // fetchBooks() sunucuya ulaşamazsa null döner — sözlük çevrimdışı da açılmalı,
  // başlık slug'a düşer.
  const books = (await fetchBooks()) || [];
  const book = books.find((b) => b.slug === slug) || null;
  // "Okuduğum bölümde" süzgeci okuma konumunu buradan okur.
  if (book) durum.currentBook = book;
  glossBolumde = null;
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
  // İnceleme listesi sunucu hesabıdır; beklenmez (çevrimdışıysa kutu gizli kalır).
  incelemeyiYukle(slug).then(() => {
    if (glossFilter === "incelenecek") yenidenSuz();
  });
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

// Bekleyen ve REDDEDİLEN düzenlemeleri sözlük ekranının başında duyur. Reddedilen
// işlem sessizce silinmez: burada sebebiyle görünür, kullanıcı tekrar dener ya da
// vazgeçer.
export function updateGlossPendingNote() {
  const note = el("glossPending");
  if (!note) return;
  const hepsi = kuyruk.islemler();
  const bekleyen = hepsi.filter((o) => o.durum === "bekliyor");
  const hatali = hepsi.filter((o) => o.durum === "hata");
  const kalici = kuyruk.kalici();
  note.replaceChildren();
  note.hidden = bekleyen.length === 0 && hatali.length === 0 && kalici;
  if (note.hidden) return;
  if (!kalici) {
    const p = document.createElement("p");
    p.className = "gloss-pending-uyari";
    p.textContent =
      "Değişiklikler cihaza YAZILAMADI (depolama dolu ya da kapalı). Sunucuya " +
      "gönderilene kadar yalnız bu oturumda duruyor — uygulamayı kapatırsan kaybolur.";
    note.appendChild(p);
  }
  if (bekleyen.length) {
    const p = document.createElement("p");
    const son = bekleyen.find((o) => o.sonHata);
    const sebep = son
      ? son.sonHata.kod === 0
        ? " Son deneme: sunucuya ulaşılamadı."
        : ` Son deneme: sunucu ${son.sonHata.kod}${son.sonHata.mesaj ? " — " + son.sonHata.mesaj : ""}.`
      : "";
    p.textContent =
      `${bekleyen.length} değişiklik ${kalici ? "cihazda" : "bellekte"} bekliyor — ` +
      `sunucuya ulaşınca kendiliğinden kaydedilecek.${sebep}`;
    note.appendChild(p);
  }
  for (const op of hatali) {
    const satir = document.createElement("div");
    satir.className = "gloss-pending-hata";
    const metin = document.createElement("span");
    const ne =
      op.tur === "sil"
        ? `${op.source} silinmesi`
        : op.tur === "geri"
          ? `${op.source} geri alınması`
          : `${op.source} → ${op.target}`;
    const cakisma = op.hata.kod === 409;
    const dene = document.createElement("button");
    dene.type = "button";
    dene.className = "pill";
    if (cakisma) {
      // ÇAKIŞMA: öteki cihazın değeri SESSİZCE ezilmez. İki değer yan yana
      // görünür, karar kullanıcınındır.
      const g = op.hata.guncel;
      const sunucuda = g
        ? `sunucuda şu an: ${g.target}${g.kosul ? " [koşul: " + g.kosul + "]" : ""}`
        : "sunucuda silinmiş";
      metin.textContent = `Başka bir cihazda değişti — senin değişikliğin: ${ne}; ${sunucuda}.`;
      dene.textContent = op.tur === "sil" ? "Yine de sil" : "Benimkini yaz";
      dene.addEventListener("click", () => {
        kuyruk.tabaniYenile(op.id, g ? g.surum : 0);
        flushGlossQueue();
      });
    } else {
      metin.textContent = `Gönderilemedi: ${ne} (${op.hata.kod}${op.hata.mesaj ? " — " + op.hata.mesaj : ""})`;
      dene.textContent = "Tekrar dene";
      dene.addEventListener("click", () => {
        kuyruk.yenidenDene(op.id);
        flushGlossQueue();
      });
    }
    const vazgec = document.createElement("button");
    vazgec.type = "button";
    vazgec.className = "pill";
    vazgec.textContent = cakisma ? "Sunucudakini kullan" : "Vazgeç";
    vazgec.addEventListener("click", async () => {
      kuyruk.vazgec(op.id);
      if (cakisma && durum.currentBookSlug === op.slug && !views.glossary.hidden) {
        renderGlossary(await fetchGlossary(op.slug)); // güncel değer ekrana gelsin
      } else {
        yenidenSuz();
      }
    });
    satir.append(metin, dene, vazgec);
    note.appendChild(satir);
  }
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
  note.textContent =
    (glossFilter === "bolumde" && glossBolumdeNot ? glossBolumdeNot + " " : "") +
    (suzuluyor ? `${toplam} terimden ${gosterilen} tanesi gösteriliyor` : `${toplam} terim`);
}

function cip(metin, sinif, baslik) {
  const c = document.createElement("span");
  c.className = "gloss-cip " + sinif;
  c.textContent = metin;
  if (baslik) c.title = baslik;
  return c;
}

export function renderGlossary(terms) {
  const list = el("glossList");
  list.replaceChildren();
  updateGlossPendingNote();
  updateGlossWarnNote();
  const uyaranlar = glossUyaranlar();
  const gorunenKosullar = overlayGloss(durum.currentBookSlug, glossTermsSonHal, glossKosullarSonHal).kosullar;
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
    // KISA SATIR: kaynak → karşılık + durum çipleri. Dokununca terim paneli açılır
    // (koşul, köken, örnek, etkilenen bölümler, silme). Her satırda bütün alanları
    // açık tutmak 267 terimlik listeyi telefonda okunmaz kılıyordu (belge bulgusu).
    const row = document.createElement("button");
    row.type = "button";
    row.className = "gloss-row";
    row.dataset.sozlukSlug = durum.currentBookSlug;
    row.dataset.sozlukKaynak = source;

    const src = document.createElement("span");
    src.className = "gloss-source";
    src.lang = "en";
    src.textContent = source;
    if (uyaranlar.has(source)) {
      // Rozet satırın kendisinde: listenin başındaki özet kaydırınca ekrandan çıkıyor.
      const uyari = document.createElement("span");
      uyari.className = "gloss-warn-chip";
      uyari.textContent = "?";
      uyari.title = "Sözlükte buna tek harf uzaklıkta başka bir terim var";
      src.appendChild(uyari);
    }

    const arrow = document.createElement("span");
    arrow.className = "gloss-arrow";
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "→";

    const tgt = document.createElement("span");
    tgt.className = "gloss-target-metin";
    tgt.textContent = glossIngilizceKorunan(source, target) ? "aynen" : target;

    const cipler = document.createElement("span");
    cipler.className = "gloss-cipler";
    // KOŞUL görünür kalır: prompt'a çıkan bir kural; saklanırsa terim beklenmedik
    // çevrildiğinde sebebi hiçbir yerde okunamaz. Tam metni panelde.
    if (gorunenKosullar[source]) cipler.appendChild(cip("KOŞULLU", "gloss-cip-kosul", gorunenKosullar[source]));
    const kok = glossRows[source] || {};
    if (kok.origin === "auto") cipler.appendChild(cip("OTO", "gloss-cip-oto", "Çeviri sırasında otomatik eklendi"));
    if (kok.first_chapter) cipler.appendChild(cip("B" + kok.first_chapter, "gloss-cip-bolum", "İlk eklendiği bölüm"));
    const ek = glossEkler[source];
    if (ek && ek.anlamlar.length) {
      cipler.appendChild(cip(`${ek.anlamlar.length + 1} ANLAM`, "gloss-cip-kosul", "Bağlama göre birden çok karşılık"));
    }
    if (ek && ek.yazimlar.length) {
      cipler.appendChild(cip(`+${ek.yazimlar.length} YAZIM`, "gloss-cip-yazim", ek.yazimlar.join(", ")));
    }
    if (incelenecekler.has(anahtarla(source))) cipler.appendChild(cip("İNCELE", "gloss-cip-incele", "İnceleme listesinde"));

    row.append(src, arrow, tgt, cipler);
    row.setAttribute("aria-label", `${source} → ${tgt.textContent}. Ayrıntı için aç`);
    row.addEventListener("click", () => terimPaneliAc({ slug: durum.currentBookSlug, source }));
    list.appendChild(row);
  }
  refreshGlossPendingUi();
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

/* Arama ve süzgeç YEREL: sunucuya istek atmaz, tazeleme yapmaz — yalnız hâlihazırda
   çizili listeyi yeniden süzer. Sunucudan tazelemek çevrimdışıyken listeyi
   boşaltırdı (bekleyen kayıtlar `overlayGloss` üzerinden geliyor). */
export function yenidenSuz() {
  if (!durum.currentBookSlug || views.glossary.hidden) return;
  renderGlossary(overlayGloss(durum.currentBookSlug, glossTermsSonHal, glossKosullarSonHal).terms);
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
    // İKİ biçim: tam kayıtlı yedek (`kayitlar`, koşul + köken) ve eski biçim
    // (`terms` eşlemesi ya da düz {kaynak: karşılık} nesnesi).
    let yuk;
    try {
      const veri = JSON.parse(await dosya.text());
      if (veri && Array.isArray(veri.kayitlar)) {
        yuk = { kayitlar: veri.kayitlar };
      } else {
        const terms = veri && typeof veri === "object" ? veri.terms || veri : null;
        if (!terms || typeof terms !== "object" || Array.isArray(terms)) {
          throw new Error("ne kayitlar ne terms alanı var");
        }
        yuk = { terms };
      }
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
          body: JSON.stringify({ ...yuk, strateji: ezsin ? "dosya" : "mevcut" }),
        }
      );
      if (!res.ok) throw new Error("sunucu " + res.status);
      const veri = await res.json();
      const parcalar = [`${veri.gelen} kayıttan ${veri.eklenen} tanesi eklendi`];
      if (veri.guncellenen) parcalar.push(`${veri.guncellenen} tanesi güncellendi`);
      if (veri.atlanan) parcalar.push(`${veri.atlanan} tanesi zaten kayıtlıydı, korundu`);
      if (veri.gecersiz) parcalar.push(`${veri.gecersiz} tanesi geçersizdi, atlandı`);
      setGlossIoState(parcalar.join(", ") + ".");
      renderGlossary(await fetchGlossary(durum.currentBookSlug));
    } catch (err) {
      setGlossIoState("Yüklenemedi (" + err.message + ") — sunucu açıkken tekrar dene.");
    }
  });
  el("glossTurSuz")?.addEventListener("change", (e) => {
    glossTurSuzgeci = e.target.value;
    yenidenSuz();
  });
  el("glossSearch")?.addEventListener("input", (e) => {
    glossQuery = e.target.value.trim();
    yenidenSuz();
  });
  for (const btn of document.querySelectorAll("[data-gloss-filter]")) {
    btn.addEventListener("click", async () => {
      glossFilter = btn.getAttribute("data-gloss-filter");
      if (glossFilter === "incelenecek") await incelemeyiYukle(durum.currentBookSlug);
      markSegment("glossFilter", glossFilter, "data-gloss-filter");
      if (glossFilter === "bolumde") await bolumdeGecenleriYukle();
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

  // Sürüm 1 kuyruğunda bekleyen değişiklikler kaybolmasın: bir kez yeni biçime taşınır.
  kuyruk.eskiKuyruguTasi();

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
