// SAF (DOM'suz, Node testli): tempo yoklaması (hızlı okuma planı Adım B, 2026-11-08).
//
// Tempo (otomatik kaydırma ya da öbek kılavuzu) ile BİTİRİLEN her ikinci bölümde
// "Takip edebildin mi?" sorulur; her beşinci bölümde yoklama yerine ölçüm bölümü önerilir
// (tempodan sonra serbest hızın artıp artmadığı böyle ölçülür). Öz bildirim iyimser
// olduğu için hız yalnız art arda İKİNCİ "Rahattı"da artar; "Zorlandım" hemen düşürür.
// Art arda üç tempo bölümü okurdan hiç iz olmadan biterse (masadaki telefon) tempo durur.
import { hizSinirla } from "./oto-kaydir-yardimci.js";

export const YOKLAMA_ARALIGI = 2;
export const OLCUM_ARALIGI = 5;
export const ETKINSIZ_SINIRI = 3;
export const ADIM = 0.04;

export function yeniDurum() {
  return { tempoBolum: 0, rahatti: 0, etkinsiz: 0 };
}

export function bolumBitti(d, { tempo, etkin }) {
  if (!tempo) return { durum: { ...d, tempoBolum: 0, etkinsiz: 0 }, goster: null, duraklat: false };
  const tempoBolum = d.tempoBolum + 1;
  const etkinsiz = etkin ? 0 : d.etkinsiz + 1;
  const goster = tempoBolum % OLCUM_ARALIGI === 0 ? "olcum"
    : tempoBolum % YOKLAMA_ARALIGI === 0 ? "yoklama" : null;
  return { durum: { ...d, tempoBolum, etkinsiz }, goster, duraklat: etkinsiz >= ETKINSIZ_SINIRI };
}

// Yanıt okurun ekranda olduğunu da gösterir: masadaki telefon sayacı sıfırlanır.
export function yanit(d, cevap, hiz) {
  const temel = { ...d, etkinsiz: 0 };
  if (cevap === "zorlandim") return { durum: { ...temel, rahatti: 0 }, hiz: hizSinirla(hiz * (1 - ADIM)) };
  if (cevap === "rahatti") {
    const r = d.rahatti + 1;
    return r >= 2 ? { durum: { ...temel, rahatti: 0 }, hiz: hizSinirla(hiz * (1 + ADIM)) }
      : { durum: { ...temel, rahatti: r }, hiz: hizSinirla(hiz) };
  }
  return { durum: { ...temel, rahatti: 0 }, hiz: hizSinirla(hiz) };
}
