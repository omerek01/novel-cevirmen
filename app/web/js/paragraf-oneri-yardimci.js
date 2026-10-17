// Paragraf önerisi (Ö2 yeniden çeviri, Ö4 onarım) ve sözlük damgası (Ö3) için saf
// yardımcılar: DOM'a dokunmaz, `node --test` ile sınanır.

export const MODLAR = {
  yeniden: { dugme: "Bu paragrafı yeniden çevir", bekleme: "Paragraf yeniden çevriliyor…" },
  onar: { dugme: "Onarım önerisi al", bekleme: "Onarım önerisi hazırlanıyor…" },
};

export function oneriGovdesi(url, sira, mod) {
  return { url, sira, mod: MODLAR[mod] ? mod : "yeniden" };
}

export function kaydetGovdesi(url, sira, oneri) {
  return { url, sira, mevcut: oneri.mevcut, metin: oneri.aday };
}

/* Sunucu yanıtından okura gösterilecek durum. `aday` yoksa öneri yok demektir:
   onarım değişiklik gerektirmedi ya da model aynı metni verdi. */
export function oneriDurumu(yanit) {
  if (!yanit || !yanit.aday) {
    return { tur: "yok", metin: "Öneri çıkmadı: model bu paragrafta değişiklik önermedi." };
  }
  if (yanit.aday.trim() === (yanit.mevcut || "").trim()) {
    return { tur: "yok", metin: "Öneri mevcut çeviriyle aynı çıktı." };
  }
  const kalan = (yanit.kalan || []).length;
  return {
    tur: "var",
    not: kalan ? `Öneride ${kalan} şüphe kaldı; kabul etmeden önce okuyun.` : "",
  };
}

export function hataMetni(durum, detay) {
  if (durum === 409) return detay || "Bölüm bu arada değişmiş; sayfayı yenileyin.";
  if (durum === 0) return "Sunucuya ulaşılamadı.";
  return detay || `Öneri alınamadı (sunucu ${durum}).`;
}

/* Bölüm çevrildikten SONRA değişen ve bölümde geçen kayıtlar (`sozluk_degisen`).
   null: damgasız eski bölüm, bilinmiyor — hiçbir şey söylenmez. */
export function damgaOzeti(degisen) {
  if (!Array.isArray(degisen) || degisen.length === 0) return null;
  return `${degisen.length} terim bu çeviriden sonra değişti`;
}

export function damgaSatiri(d) {
  return d.yeni == null
    ? `${d.source}: “${d.eski}” (kayıt artık yok)`
    : `${d.source}: “${d.eski}” → “${d.yeni}”`;
}
