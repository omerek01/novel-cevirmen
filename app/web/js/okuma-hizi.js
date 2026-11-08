/* Okuma hızı ölçümü (hızlı okuma planı Adım A, 2026-11-08).

   Okur hiçbir şey yapmaz: bir bölüm baştan sona okununca süresi ve harf sayısı
   sunucuya gider, kişisel hız oradan hesaplanır (tek doğru kaynak sunucu). Hesap saf
   `okuma-hizi-yardimci.js`'te; burada yalnız okuyucu olaylarına bağlanır.

   Döngüsel içe aktarma olmasın diye okuyucu ve otomatik kaydırma bu modüle BAĞLANIR
   (`okumaHiziKur({ aktifBolum, tempoAkiyor })`); bu modül onları içe aktarmaz.
   Kendi `scroll` dinleyicisini AÇMAZ: okuyucunun tek kaydırma girişi
   `onReaderScroll` buraya `okumaHiziKaydir` ile haber verir. */
import {
  BITIS_ORANI, atlama, etkinlik, harfSay, oranGuncelle, oturumSonucu, sozcukSay, sureEkle, yeniOturum,
} from "./okuma-hizi-yardimci.js";
import { el, localDay } from "./temel.js";

const LS_HIZ = "novellink:okuma-hizi";
const TIK_MS = 1000;

let aktifBolum = () => null;
let tempoAkiyor = () => false;
let obekModu = () => false;
const oturumlar = new Map(); // url → açık oturum (geri kaydırınca duraklar, dönünce sürer)
const bitenler = new Set(); // bu okuyucu ziyaretinde biten url'ler: yeniden ölçülmez
let aktifUrl = null;
let tik = 0;
let gozlemci = null;
let yukseklik = 0;

function oturumKimligi() {
  // crypto.randomUUID yalnız güvenli bağlamda var; sunucu Tailscale üstünden http.
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

function olculebilir(e) {
  return !!e && e.loaded && !e.html && !e.empty && Array.isArray(e.paras) && e.paras.length > 0;
}

export function bolumHarfi(e) {
  if (!e || !Array.isArray(e.paras)) return 0;
  if (e._harfIcin !== e.paras) {
    e._harfIcin = e.paras; // yeniden çeviri paras'ı değiştirirse sayım tazelenir
    e.harf = harfSay(e.paras);
    e.sozcuk = sozcukSay(e.paras);
  }
  return e.harf;
}

// Aktif bölümün çizim yoğunluğu: otomatik kaydırma harf/dk'yı piksel/sn'ye bununla çevirir.
export function yogunluk() {
  const e = aktifBolum();
  if (!olculebilir(e) || !e.el) return null;
  const harf = bolumHarfi(e);
  const y = yukseklik || e.el.getBoundingClientRect().height;
  return y > 0 && harf > 0 ? { yukseklik: y, harf, sozcuk: e.sozcuk } : null;
}

function yuksekligiIzle(e) {
  if (gozlemci) gozlemci.disconnect();
  yukseklik = 0;
  if (!e || !e.el) return;
  if (typeof ResizeObserver !== "function") return; // yogunluk() o an ölçer
  gozlemci = new ResizeObserver((girdiler) => {
    const r = girdiler[0] && girdiler[0].contentRect;
    if (r) yukseklik = r.height;
  });
  gozlemci.observe(e.el);
}

/* ---------- kişisel hız önbelleği ---------- */
export function hizIstatistigi() {
  try {
    return JSON.parse(localStorage.getItem(LS_HIZ)) || null;
  } catch {
    return null;
  }
}

export function kisiselHdk() {
  const s = hizIstatistigi();
  return (s && s.kisisel_hiz && s.kisisel_hiz.hdk) || 0;
}

export async function hizTazele() {
  try {
    const res = await fetch(`/api/reading-speed/stats?day=${localDay()}`);
    if (!res.ok) return;
    const veri = await res.json();
    try {
      localStorage.setItem(LS_HIZ, JSON.stringify(veri));
    } catch {
      // depolama kapalı: kalan süre yedek hızla hesaplanır
    }
  } catch {
    // çevrimdışı: son önbellek değeri kalır
  }
}

/* ---------- gönderim ---------- */
function gonder(o, bitti) {
  const govde = { ...oturumSonucu(o, bitti), day: localDay() };
  if (!govde.active_ms && !bitti) return; // hiç okunmamış: satır açma
  fetch("/api/reading-speed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(govde),
    keepalive: true, // sayfa kapanırken de gitsin
  })
    .then((res) => {
      if (res.status === 422) console.warn("[okuma-hizi] reddedildi", govde);
      else if (bitti && res.ok) hizTazele();
    })
    .catch(() => {});
}

function bitir(url, bitti) {
  const o = oturumlar.get(url);
  if (!o) return;
  oturumlar.delete(url);
  bitenler.add(url);
  gonder(o, bitti);
}

function tikla() {
  const o = aktifUrl && oturumlar.get(aktifUrl);
  if (!o) return;
  sureEkle(o, performance.now(), {
    gorunur: document.visibilityState === "visible",
    diyalog: !!document.querySelector("dialog[open]"),
    tempoAkiyor: tempoAkiyor(),
  });
}

/* ---------- okuyucudan gelen olaylar ---------- */

// Aktif bölüm değişti. İleri geçişte eski bölüm biter (yeterince okunduysa geçerli);
// geri geçişte eski oturum duraklar ve o bölüme dönünce sürer.
export function okumaHiziAktif(e, oran, akis) {
  tikla();
  const eski = aktifUrl;
  aktifUrl = e ? e.url : null;
  if (eski && eski !== aktifUrl && oturumlar.has(eski)) {
    const eskiSira = akis.findIndex((c) => c.url === eski);
    const yeniSira = akis.findIndex((c) => c.url === aktifUrl);
    if (yeniSira > eskiSira) {
      const o = oturumlar.get(eski);
      bitir(eski, o.enCokOran >= BITIS_ORANI);
    }
  }
  yuksekligiIzle(e);
  if (!olculebilir(e) || bitenler.has(e.url) || oturumlar.has(e.url)) return;
  const harf = bolumHarfi(e);
  oturumlar.set(e.url, yeniOturum({
    id: oturumKimligi(), url: e.url, slug: e.bookSlug || "", harf, sozcuk: e.sozcuk,
    acilisOrani: oran, simdi: performance.now(), obek: obekModu(),
  }));
}

// Okuyucunun tek kaydırma girişinden: oran, etkinlik ve bölüm sonu.
export function okumaHiziKaydir(e, oran) {
  const o = e && oturumlar.get(e.url);
  if (!o) return;
  // Otomatik kaydırmanın kendi scrollBy'ı da buraya düşer: okur etkinliği sayılmaz.
  if (!tempoAkiyor()) etkinlik(o, performance.now());
  oranGuncelle(o, oran);
  if (e.el && e.el.getBoundingClientRect().bottom <= window.innerHeight) {
    tikla();
    bitir(e.url, true);
  }
}

// Dokunma (otomatik kaydırmanın pointerdown dinleyicisinden) ve diğer okur izleri.
export function okumaHiziEtkinlik() {
  const o = aktifUrl && oturumlar.get(aktifUrl);
  if (o) etkinlik(o, performance.now());
}

// Arama gezintisi ya da konuma zıplama: bu bölüm okunarak geçilmedi.
// Öbek modu oturum ortasında açıldı/kapandı: karışık bölüm ne normal ne öbek hızına girer.
export function okumaHiziKarisik() {
  const o = aktifUrl && oturumlar.get(aktifUrl);
  if (o) atlama(o);
}

export function okumaHiziAtlama() {
  const o = aktifUrl && oturumlar.get(aktifUrl);
  if (o) atlama(o);
}

function hepsiniBirak() {
  tikla();
  for (const url of [...oturumlar.keys()]) bitir(url, false);
  bitenler.clear();
  aktifUrl = null;
}

export function okumaHiziKur(baglanti) {
  aktifBolum = baglanti.aktifBolum;
  tempoAkiyor = baglanti.tempoAkiyor;
  if (baglanti.obekModu) obekModu = baglanti.obekModu;
  if (!tik) tik = setInterval(tikla, TIK_MS);
  // Sekme gizlenince o anki durum aynı oturum_id ile gider; Android PWA'da pagehide
  // çoğu zaman gelmez. Oturum kapanmaz, dönünce sürer.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "hidden") return;
    tikla();
    const o = aktifUrl && oturumlar.get(aktifUrl);
    if (o) gonder(o, false);
  });
  window.addEventListener("pagehide", () => {
    tikla();
    for (const o of oturumlar.values()) gonder(o, false);
  });
  // Okuyucudan çıkış: açık oturumlar yarım olarak gider, biten listesi sıfırlanır.
  new MutationObserver(() => {
    if (el("readerView").hidden) hepsiniBirak();
    else hizTazele();
  }).observe(el("readerView"), { attributes: true, attributeFilter: ["hidden"] });
  hizTazele();
}
