// SAF (DOM'suz, Node testli): okuyucunun otomatik kaydırma hızı ve kare adımı.
//
// Hız birimi harf/dk (hızlı okuma planı §3, 2026-11-08): okur "Hız 4" yerine kendi
// okuma hızını görür ve yazı boyutu değişince akış hızı kaymaz. Ekrandaki piksel/sn,
// aktif bölümün çizilmiş yüksekliği ile harf sayısından hesaplanır.

// Eski 12 seviyeli px/sn tablosu YALNIZ bir kezlik çevrim için durur: kaydedilmiş
// `kaydirmaSeviyesi` ilk başlatmada o anki kaydırma hızı korunarak harf/dk'ya çevrilir.
export const ESKI_HIZLAR = [6, 9, 12, 16, 20, 25, 31, 38, 47, 58, 72, 90];
// ~6,5 harfli Türkçe sözcükle yaklaşık 110-690 sözcük/dk. Alt sınır bilerek düşük:
// sözcük/dk eklemeli dilde İngilizceden düşük çıkar.
export const HIZ_ALT = 700;
export const HIZ_UST = 4500;
export const YEDEK_HIZ = 1495; // 230 sözcük/dk × 6,5: kişisel hız bilinmeden önceki tahmin
export const ADIM_ORANI = 0.05;
// Sekme arka plandayken rAF durur; dönüşte birikmiş koca bir aralık sayfayı
// tek karede zıplatmasın.
const EN_UZUN_KARE_MS = 100;

export function hizSinirla(hdk) {
  const h = Math.round(Number(hdk));
  if (!Number.isFinite(h)) return YEDEK_HIZ;
  return Math.min(HIZ_UST, Math.max(HIZ_ALT, h));
}

// − / + düğmesi: yüzde 5 adım, sınır içinde.
export function hizAdimi(hdk, yon) {
  return hizSinirla(hizSinirla(hdk) * (1 + ADIM_ORANI * Math.sign(yon)));
}

// harf/dk → piksel/sn. Bölüm henüz çizilmemişse (yükseklik ya da harf 0) null döner;
// çağıran son geçerli değeri korur, NaN/Infinity akışa hiç girmez.
export function pxSn(hdk, yukseklikPx, harf) {
  if (!(yukseklikPx > 0) || !(harf > 0)) return null;
  return (hizSinirla(hdk) / 60) * (yukseklikPx / harf);
}

// Eski seviye → harf/dk, o anki çizime göre: aynı px/sn'yi veren harf/dk.
export function seviyedenHiz(seviye, yukseklikPx, harf) {
  const s = Math.min(ESKI_HIZLAR.length, Math.max(1, Math.round(Number(seviye)) || 4));
  if (!(yukseklikPx > 0) || !(harf > 0)) return null;
  return hizSinirla(ESKI_HIZLAR[s - 1] * 60 * (harf / yukseklikPx));
}

// Kumandadaki çentik: hızın sınırlar arasındaki yeri, 1..adet dolu.
export function centikDolu(hdk, adet) {
  const oran = (hizSinirla(hdk) - HIZ_ALT) / (HIZ_UST - HIZ_ALT);
  return 1 + Math.round(oran * (adet - 1));
}

// Bir karede kaç TAM piksel kaydırılacağı. Kesir birikir: yavaş hızda kare başına
// 0,1 px düşer ve yuvarlamak kaydırmayı hiç ilerletmezdi.
export function adim(birikim, pxSn, ms) {
  const toplam = birikim + (pxSn * Math.min(Math.max(ms, 0), EN_UZUN_KARE_MS)) / 1000;
  const px = Math.floor(toplam);
  return { px, birikim: toplam - px };
}
