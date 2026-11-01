// SAF (DOM'suz, Node testli): okuyucunun otomatik kaydırma hızı ve kare adımı.
//
// Hız seviyeleri piksel/saniye. Ölçek: 19 px yazı, 1,75 satır aralığında bir satır
// ~33 px ve dar ekranda ~10 sözcük. Seviye 1 (6 px/sn) dakikada ~110 sözcük,
// seviye 4 (16 px/sn) ~290 (rahat okuma), seviye 12 (90 px/sn) göz gezdirme.
export const HIZLAR = [6, 9, 12, 16, 20, 25, 31, 38, 47, 58, 72, 90];
export const VARSAYILAN_SEVIYE = 4;
// Sekme arka plandayken rAF durur; dönüşte birikmiş koca bir aralık sayfayı
// tek karede zıplatmasın.
const EN_UZUN_KARE_MS = 100;

export function seviyeSinirla(seviye) {
  const s = Math.round(Number(seviye));
  if (!Number.isFinite(s)) return VARSAYILAN_SEVIYE;
  return Math.min(HIZLAR.length, Math.max(1, s));
}

export function hiz(seviye) {
  return HIZLAR[seviyeSinirla(seviye) - 1];
}

// Bir karede kaç TAM piksel kaydırılacağı. Kesir birikir: yavaş hızda kare başına
// 0,1 px düşer ve yuvarlamak kaydırmayı hiç ilerletmezdi.
export function adim(birikim, pxSn, ms) {
  const toplam = birikim + (pxSn * Math.min(Math.max(ms, 0), EN_UZUN_KARE_MS)) / 1000;
  const px = Math.floor(toplam);
  return { px, birikim: toplam - px };
}
