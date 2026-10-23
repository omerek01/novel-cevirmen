// Vertex kredi göstergesi (`/api/settings/kredi`) için saf yardımcılar: DOM'a dokunmaz,
// `node --test` ile sınanır.

const AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
  "Eylül", "Ekim", "Kasım", "Aralık"];

/* Dolar: 10 $ üstü tam sayı (göstergede kuruş gürültü), altı iki basamak. */
export function para(n) {
  const v = Number(n) || 0;
  const basamak = Math.abs(v) >= 10 ? 0 : 2;
  return `${v.toLocaleString("tr-TR", { minimumFractionDigits: basamak, maximumFractionDigits: basamak })} $`;
}

export function tarihMetni(iso) {
  const [y, a, g] = String(iso).slice(0, 10).split("-").map(Number);
  if (!y || !a || !g) return "";
  return `${g} ${AYLAR[a - 1]} ${y}`;
}

/* Süre işareti: deneme kredisi 90 gün; geçen sürenin oranı harcama oranıyla kıyaslanır. */
export function zamanOrani(d) {
  if (!d || d.kalan_gun === null || d.kalan_gun === undefined || !d.deneme_gun) return null;
  return Math.min(1, Math.max(0, 1 - d.kalan_gun / d.deneme_gun));
}

/* Son 7 günün hızıyla kalan kredi kaç günde biter; süre dolmadan bitecekse uyarı. */
export function hizMetni(d) {
  if (!d || !d.son_7_gun) return { metin: "Son 7 günde ölçülen harcama yok.", uyari: false };
  const gunluk = d.son_7_gun / 7;
  const gun = Math.floor(d.kalan / gunluk);
  let metin = `Son 7 gün ${para(d.son_7_gun)} (günde ≈${para(gunluk)}). `;
  if (d.kalan <= 0) return { metin: `${metin}Kredi bitti.`, uyari: true };
  metin += `Bu hızla ≈${gun} günde biter`;
  if (d.kalan_gun === null || d.kalan_gun === undefined) return { metin: `${metin}.`, uyari: false };
  if (gun < d.kalan_gun) return { metin: `${metin}, süre dolmadan.`, uyari: true };
  const artan = d.kalan - gunluk * d.kalan_gun;
  return { metin: `${metin}; süre dolduğunda ≈${para(artan)} kullanılmamış kalır.`, uyari: false };
}

export function bitisMetni(d) {
  if (!d || !d.bitis) return "Bitiş tarihi girilmedi.";
  if (d.kalan_gun === 0) return `Süre doldu (${tarihMetni(d.bitis)}).`;
  return `Bitiş ${tarihMetni(d.bitis)} · ${d.kalan_gun} gün kaldı`;
}

/* Model dökümü: en pahalıdan; fiyatı bilinmeyen model saklanmaz, tutarsız toplam söylenir. */
export function dokumMetni(d) {
  const ms = (d && d.modeller) || [];
  if (!ms.length) return "";
  const parca = ms.map((m) => {
    const ad = m.model.replace(/^gemini-/, "");
    return m.fiyat_bilinmiyor ? `${ad} (fiyatı bilinmiyor)` : `${ad} ${para(m.maliyet)}`;
  });
  // Konsol okuması varsa döküm yalnız okumadan SONRAKİ saatleri kapsar (sunucu öyle sayar).
  return `${d.okuma ? "Okumadan sonra: " : ""}${parca.join(" · ")}`;
}

/* Rakamın nereden geldiği: konsol okuması + sonrası tahmin ya da yalnız Google ölçümü. */
export function kaynakMetni(d) {
  if (!d) return "";
  if (d.okuma) {
    return `Konsol okuması ${para(d.okuma.tutar)} (${tarihMetni(d.okuma.zaman)}) + sonrasının tahmini ${para(d.tahmin)}.`;
  }
  if (d.ilk_olcum) {
    return `Google'ın token ölçümü × fiyat tablosu, ${tarihMetni(d.ilk_olcum)} itibarıyla. Kesin rakam konsolda; girersen ona bağlanır.`;
  }
  return "Henüz Google ölçümü yok.";
}

export function ozet(d) {
  const yuzde = Math.round((d.oran || 0) * 100);
  return {
    baslik: `≈${para(d.kullanilan)}`,
    toplam: `/ ${para(d.tutar)}`,
    alt: `%${yuzde} kullanıldı · ${para(d.kalan)} kaldı`,
    yuzde,
  };
}
