// Çeviri aşaması düğmeleri (`/api/settings/asamalar`) için saf yardımcılar: DOM'a
// dokunmaz, `node --test` ile sınanır.

const GECERLILIK = "Seçim yalnız yeni çevrilen bölümlerde geçerli.";

/* Süre SUNUCUNUN gerçek çağrı kaydından gelir (`api_olay`). Ölçüm yoksa süre
   uydurulmaz: yanlış bir rakam, kullanıcıyı yanlış aşamayı kapatmaya iter. */
export function asamaSureMetni(ad, olcum) {
  const a = olcum && olcum.bolum ? (olcum.asamalar || {})[ad] : null;
  if (!a) return "Henüz ölçüm yok";
  if (!a.ort_sn) return `Son ${olcum.bolum} bölümde hiç çalışmadı`;
  const kac = Math.round(a.bolum_orani * olcum.bolum);
  return `Bölüm başına +${Math.round(a.ort_sn)} sn · son ${olcum.bolum} bölümün ${kac}'${ekSinde(kac)} çalıştı`;
}

export function olcumOzeti(olcum) {
  if (!olcum || !olcum.bolum) return GECERLILIK;
  return `Son ${olcum.bolum} bölüm: bölüm başına ortalama ${Math.round(olcum.toplam_ort_sn)} sn ` +
    `model süresi, bunun ${Math.round(olcum.ceviri_ort_sn)} sn'si çevirinin kendisi. ${GECERLILIK}`;
}

export function asamaGovdesi(ad, acik) {
  return { ad, acik: acik === "1" };
}

/* Sayıdan sonra gelen "-(s)inde" ekinin ünlü uyumu (son okunan sözcüğe göre). */
const EKLER = {
  0: "ında", 1: "inde", 2: "sinde", 3: "ünde", 4: "ünde", 5: "inde", 6: "sında",
  7: "sinde", 8: "inde", 9: "unda",
};
const ONLAR = {
  10: "unda", 20: "sinde", 30: "unda", 40: "ında", 50: "sinde", 60: "ında",
  70: "inde", 80: "inde", 90: "ında",
};
function ekSinde(n) {
  if (n === 0) return "ında";
  if (n % 100 === 0) return "ünde";
  if (n % 10) return EKLER[n % 10];
  return ONLAR[n % 100];
}
