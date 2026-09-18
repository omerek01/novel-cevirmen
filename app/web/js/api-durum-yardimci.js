/* API durum panelinin SAF yardımcıları (DOM yok; Node ile test edilir:
   tests/js/api-durum-yardimci.test.mjs).

   Karar mantığı (kart durumu, "neden bu model?") SUNUCUDA durur, burada değil:
   aynı kuralın iki yerde yazılması bu projede defalarca ayrışmayla sonuçlandı.
   Burada yalnız BİÇİM ve panelin kendi durumu (bayatlık, sayfa birleştirme) var. */

export const YENILEME_MS = 15000;

// Türkiye kalıcı UTC+3; tarayıcının saat dilimi ne olursa olsun TSİ gösterilir
// (kota sıfırlanması "TSİ 10:00" diye okunmalı, telefon yurt dışındayken bile).
const SAAT = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul", hour: "2-digit", minute: "2-digit", second: "2-digit",
});
const TARIH_SAAT = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul", day: "2-digit", month: "2-digit",
  hour: "2-digit", minute: "2-digit",
});

/** Sunucu zamanı (epoch SANİYE) → "15:08:25" (TSİ). */
export function saat(ts) {
  return ts ? SAAT.format(new Date(ts * 1000)) : "-";
}

/** Sunucu zamanı (epoch SANİYE) → "18.09 15:08" (TSİ).

    Parçalardan kurulur: `tr-TR` gün/ay ayırıcısı ortama göre değişiyor (Node'un
    ICU'su "18/09" verdi), oysa ekranda her yerde aynı biçim görünmeli. */
export function tarihSaat(ts) {
  if (!ts) return "-";
  const p = Object.fromEntries(
    TARIH_SAAT.formatToParts(new Date(ts * 1000)).map((x) => [x.type, x.value])
  );
  return `${p.day}.${p.month} ${p.hour}:${p.minute}`;
}

/** Kalan süre: "3 sa 12 dk" · "4 dk" · "45 sn". Geçmişse boş. */
export function kalanSure(bitis, simdi) {
  const sn = Math.round(bitis - simdi);
  if (!(sn > 0)) return "";
  if (sn < 60) return `${sn} sn`;
  const dk = Math.floor(sn / 60);
  if (dk < 60) return `${dk} dk`;
  const sa = Math.floor(dk / 60);
  return dk % 60 ? `${sa} sa ${dk % 60} dk` : `${sa} sa`;
}

/** "gemini-3.6-flash" → "3.6-flash". */
export function kisaModel(m) {
  return String(m || "?").replace(/^gemini-/, "");
}

/** Durum işareti: renk TEK başına anlam taşımasın diye metnin yanında durur. */
export function isaret(ton) {
  return { iyi: "✓", bekle: "◷", uyari: "!", hata: "✕", notr: "–" }[ton] || "–";
}

/* Bağlantı satırı. Veri BAYAT sayılır: son yenileme başarısızsa ya da son
   başarılı yanıt iki yenileme aralığından eskiyse (sekme uyuduysa). Eski veri
   SİLİNMEZ, zamanıyla birlikte ekranda kalır — boş ekran "hiçbir şey yok"
   gibi okunurdu. */
export function baglantiDurumu({ sonBasari, sonHata, simdiMs }) {
  if (!sonBasari) {
    return sonHata
      ? { metin: "Sunucuya ulaşılamadı. Kayıt okunamadı.", bayat: true }
      : { metin: "Yükleniyor…", bayat: false };
  }
  const zaman = SAAT.format(new Date(sonBasari));
  const hataSonra = sonHata && sonHata >= sonBasari;
  const eski = simdiMs - sonBasari > 2 * YENILEME_MS;
  if (hataSonra) {
    return { metin: `Sunucuya ulaşılamadı. Gösterilen veri ${zaman} tarihli (bayat).`, bayat: true };
  }
  if (eski) return { metin: `Son güncelleme ${zaman} (bayat).`, bayat: true };
  return { metin: `Bağlı · son güncelleme ${zaman}`, bayat: false };
}

/** Geçişin bölüm etiketi: "Deneme · 595. bölüm" ya da URL'nin son parçası. */
export function bolumEtiketi(olay) {
  const b = olay && olay.bolum;
  if (b) {
    const kitap = b.kitap_adi || b.kitap || "";
    const no = b.no != null ? `${b.no}. bölüm` : b.baslik || "";
    return [kitap, no].filter(Boolean).join(" · ");
  }
  const url = olay && olay.url;
  if (!url) return "";
  return url.replace(/\/+$/, "").split("/").slice(-2).join("/");
}

/** Geçişin nedeni: sunucu özeti "3.6-flash → 3.5-flash: <neden>" biçimindedir. */
export function gecisNedeni(olay) {
  const ozet = (olay && olay.ozet) || "";
  const i = ozet.indexOf(": ");
  return i >= 0 ? ozet.slice(i + 2) : "";
}

/* Otomatik yenileme ilk sayfayı yeniden çeker. Kullanıcı "Daha eski" ile ek
   sayfalar yüklediyse onlar KORUNUR: yeni ilk sayfa + ondan eski kayıtlar.
   Aksi halde 15 saniyede bir okunan liste gözünün önünde kısalırdı. */
export function sayfalariBirlestir(yeniIlk, mevcut) {
  if (!mevcut || !mevcut.length) return yeniIlk.slice();
  if (!yeniIlk.length) return mevcut.slice();
  const enEski = Math.min(...yeniIlk.map((o) => o.id));
  return yeniIlk.concat(mevcut.filter((o) => o.id < enEski));
}
