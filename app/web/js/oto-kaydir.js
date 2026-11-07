/* Otomatik kaydırma (2026-11-01, kullanıcı isteği "hızlı okuma için bölümü aşağı
   doğru kaydıran, hızı ayarlanabilen bir sistem").

   Yalnız okur başlatır (alt çubuktaki "Kaydır"); hiçbir zaman kendiliğinden açılmaz.
   Parmak ekrandayken durur, bırakınca sürer: okur konumu elle düzeltebilsin.
   Kaydırma sürerken ekran kararmasın diye ekran kilidi (Wake Lock) istenir;
   duraklayınca bırakılır. Sonsuz akışta sonraki bölüm eklenince kendiliğinden devam
   eder: sayfa sonunda döngü yalnız bekler. Hız seviyesi ayarlarda saklanır.
   Hız ve adım hesabı saf `oto-kaydir-yardimci.js`'te. */
import { saveSettings, settings } from "./ayarlar.js";
import { HIZLAR, adim, hiz, seviyeSinirla } from "./oto-kaydir-yardimci.js";
import { el } from "./temel.js";

let durum = "kapali"; // kapali | akiyor | duraklatildi
let parmakla = false; // parmak ekranda: geçici duraklama
let kare = 0;
let sonZaman = 0;
let birikim = 0;
let kilit = null;
let kilitIstegi = null; // yanıtı beklenen kilit isteği: ikinci istek açılmasın
let sonY = 0; // önceki karedeki kaydırma konumu
let sonHareket = 0; // konumun en son değiştiği an (sayfa sonu algısı)
// Sayfa sonunda bu kadar ilerleyemezse ve sonraki bölüm yüklenmiyorsa durur: döngü
// boşuna dönüp ekran kilidini saatlerce tutmasın. Yükleme sürerken bekler.
const DIP_BEKLEME_MS = 4000;

const ikonlar = {
  durdur: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="5" width="3.6" height="14" rx="1"/><rect x="13.9" y="5" width="3.6" height="14" rx="1"/></svg>',
  surdur: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6a.8.8 0 0 0 1.2.7l10.6-6.8a.8.8 0 0 0 0-1.4L9.2 4.5A.8.8 0 0 0 8 5.2z"/></svg>',
};

function seviye() {
  return seviyeSinirla(settings.kaydirmaSeviyesi);
}

function okuyucuAcik() {
  const v = el("readerView");
  // Açık bir diyalog (ayarlar, terim paneli, defter…) okumayı böler: metin altından akmasın.
  return v && !v.hidden && !document.querySelector("dialog[open]");
}

async function kilitAl() {
  if (kilit || kilitIstegi || !("wakeLock" in navigator) || document.visibilityState !== "visible")
    return;
  try {
    kilitIstegi = navigator.wakeLock.request("screen");
    const yeni = await kilitIstegi;
    // İstek yanıtlanana dek okur duraklatmış ya da kapatmış olabilir: kilit tutulmaz.
    if (durum !== "akiyor") {
      yeni.release().catch(() => {});
      return;
    }
    kilit = yeni;
    yeni.addEventListener("release", () => {
      if (kilit === yeni) kilit = null;
    });
  } catch {
    // pil tasarrufu ya da izin yok: kaydırma yine çalışır
  } finally {
    kilitIstegi = null;
  }
}

function kilitBirak() {
  if (kilit) kilit.release().catch(() => {});
  kilit = null;
}

// Seçili metin varken akış durur: uzun basınca tarayıcı sözcük seçimini devralıp
// `pointercancel` gönderiyor, "parmak kalktı" sanılıp seçim altından kayıyordu
// (kullanıcı bulgusu 2026-11-01). Seçim kalkınca kendiliğinden sürer.
function seciliMetinVar() {
  const secim = window.getSelection?.();
  return !!secim && !secim.isCollapsed && secim.toString().trim() !== "";
}

function dongu(zaman) {
  kare = 0;
  if (durum !== "akiyor") return;
  if (!okuyucuAcik()) {
    // Okuyucudan çıkıldıysa tamamen kapat; diyalog açıksa yalnız bekle.
    if (el("readerView")?.hidden) return kapat();
  } else if (!parmakla && !seciliMetinVar()) {
    const sonuc = adim(birikim, hiz(seviye()), sonZaman ? zaman - sonZaman : 0);
    birikim = sonuc.birikim;
    if (sonuc.px) window.scrollBy(0, sonuc.px);
    const y = window.scrollY;
    if (y !== sonY || document.querySelector("#streamEnd .stream-loading")) sonHareket = zaman;
    sonY = y;
    if (zaman - sonHareket > DIP_BEKLEME_MS) return duraklat();
  } else {
    sonHareket = zaman; // diyalog / parmak / seçim beklemesi sayfa sonu sayılmaz
  }
  sonZaman = zaman;
  kare = requestAnimationFrame(dongu);
}

function calistir() {
  sonZaman = 0;
  birikim = 0;
  sonY = window.scrollY;
  sonHareket = performance.now();
  if (!kare) kare = requestAnimationFrame(dongu);
}

function ciz() {
  const kutu = el("otoKaydir");
  if (!kutu) return;
  kutu.hidden = durum === "kapali";
  document.body.classList.toggle("oto-kaydiriyor", durum !== "kapali");
  const akiyor = durum === "akiyor";
  const dugme = el("otoKaydirDurdur");
  dugme.innerHTML = akiyor ? ikonlar.durdur : ikonlar.surdur;
  dugme.setAttribute("aria-label", akiyor ? "Kaydırmayı duraklat" : "Kaydırmayı sürdür");
  dugme.setAttribute("aria-pressed", String(!akiyor));
  const s = seviye();
  el("otoKaydirDeger").textContent = String(s);
  [...el("otoKaydirCentik").children].forEach((c, i) => c.classList.toggle("dolu", i < s));
  el("otoKaydirYavas").disabled = s <= 1;
  el("otoKaydirHizli").disabled = s >= HIZLAR.length;
}

export function otoKaydirBaslat() {
  durum = "akiyor";
  ciz();
  kilitAl();
  calistir();
}

function duraklat() {
  durum = "duraklatildi";
  kilitBirak();
  ciz();
}

export function kapat() {
  durum = "kapali";
  parmakla = false;
  if (kare) cancelAnimationFrame(kare);
  kare = 0;
  kilitBirak();
  ciz();
}

function hizDegistir(fark) {
  settings.kaydirmaSeviyesi = seviyeSinirla(seviye() + fark);
  saveSettings();
  ciz();
}

export function otoKaydirKur() {
  const centik = el("otoKaydirCentik");
  centik.replaceChildren(...HIZLAR.map(() => document.createElement("i")));
  el("otoKaydirDurdur").addEventListener("click", () =>
    durum === "akiyor" ? duraklat() : otoKaydirBaslat());
  el("otoKaydirYavas").addEventListener("click", () => hizDegistir(-1));
  el("otoKaydirHizli").addEventListener("click", () => hizDegistir(1));
  el("otoKaydirKapat").addEventListener("click", kapat);

  // Parmak metnin üstündeyken dur, bırakınca sür (sürükleyerek konum düzeltmek için).
  const govde = el("readerBody");
  govde.addEventListener("pointerdown", () => { parmakla = true; }, { passive: true });
  const birak = () => {
    if (!parmakla) return;
    parmakla = false;
    sonZaman = 0; // duraklamadaki süre bir kerede kaydırılmasın
  };
  for (const ad of ["pointerup", "pointercancel"]) window.addEventListener(ad, birak, { passive: true });

  // Okuyucudan çıkılınca kapat: duraklatılmışken döngü koşmadığı için kapanış hiç
  // tetiklenmiyor, eski kumanda sonraki açılışta alt çubuğun yerinde kalıyordu.
  new MutationObserver(() => {
    if (el("readerView").hidden && durum !== "kapali") kapat();
  }).observe(el("readerView"), { attributes: true, attributeFilter: ["hidden"] });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && durum === "akiyor") {
      kilitAl(); // sistem, sekme gizlenince kilidi kendisi bırakır
      sonZaman = 0;
    }
  });
  ciz();
}
