/* Kitap profili kartının SAF yardımcıları (DOM yok; Node testli: tests/js/kitap-profili-yardimci.test.mjs).

   Veri `/api/book/{slug}/profil` yanıtıdır: her alan için kod kaydı var mı, etkin değer, modelin
   önerisi (`model`) ve elle satır (`elle`). Etkin değer = istemlere ve denetimlere fiilen giren. */

export const ALANLAR = {
  kitap_turu: { etiket: "Kitap türü", not: "Sistem/oyun, kültivasyon ya da düz anlatı.", tip: "secim" },
  ana_karakter: { etiket: "Ana karakter", not: "Rün mesajlarındaki “sen” bu kişidir.", tip: "metin" },
  sistem_sesi: { etiket: "Sistem sesi", not: "Satır başında konuşan sistem (System, Spell…).", tip: "liste" },
  sistem_anahtarlari: { etiket: "Sistem anahtarları", not: "Sistem mesajındaki “Anahtar: değer” adları.", tip: "liste" },
  diziler: { etiket: "Sıralı diziler", not: "Rütbe, seviye ya da kalite basamakları; düşükten yükseğe.", tip: "dizi" },
  kategori_terimleri: { etiket: "Kategori terimleri", not: "Bir varlığı değil türü adlandıran sistem sözcükleri.", tip: "liste" },
  gercek_ad_sozcugu: { etiket: "Gerçek Ad sözcüğü", not: "Sistemin kişiye verdiği özel ad kavramı.", tip: "liste" },
};
export const TURLER = { sistem: "Sistem / oyun", kultivasyon: "Kültivasyon", duz: "Düz anlatı" };
const SIRA = Object.keys(ALANLAR);

/* Alanın kart üstündeki durumu: kodda > elle > onaylı > reddedildi > öneri > boş. */
export function alanDurumu(a) {
  if (a.kod) return { anahtar: "kod", etiket: "Kodda tanımlı" };
  if (a.elle) return { anahtar: "elle", etiket: "Senin düzeltmen" };
  const d = a.model && a.model.durum;
  if (d === "onayli") return { anahtar: "onayli", etiket: "Onaylı" };
  if (d === "reddedildi") return { anahtar: "reddedildi", etiket: "Reddedildi" };
  if (d === "aday") return { anahtar: "aday", etiket: "Öneri" };
  return { anahtar: "bos", etiket: "Boş" };
}

/* Kartta gösterilecek değer: etkin değer yoksa (öneri/ret) modelin önerdiği. */
export function gosterilenDeger(a) {
  if (a.etkin != null) return a.etkin;
  if (a.elle) return a.elle.deger;
  return a.model ? a.model.deger : null;
}

export function degerMetni(alan, deger) {
  if (deger == null) return "";
  if (alan === "kitap_turu") return TURLER[deger] || String(deger);
  if (alan === "diziler") {
    return Object.entries(deger).map(([ad, sira]) => `${ad.replaceAll("_", " ")}: ${[...sira].join(" → ")}`).join("\n");
  }
  return Array.isArray(deger) ? deger.join(", ") : String(deger);
}

/* Düzeltme kutusunun ilk metni ve geri dönüşü (sunucu da denetler; burada erken ve yerinde hata). */
export function duzeltmeMetni(alan, deger) {
  if (deger == null) return "";
  if (alan === "diziler") return Object.entries(deger).map(([ad, sira]) => `${ad}: ${[...sira].join(", ")}`).join("\n");
  if (Array.isArray(deger)) return deger.join(", ");
  return String(deger);
}

const parcala = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export function metindenDeger(alan, metin) {
  const m = String(metin ?? "").trim();
  const tip = (ALANLAR[alan] || {}).tip;
  if (!tip) throw new Error("Bilinmeyen alan");
  if (!m) throw new Error("Boş bırakılamaz");
  if (tip === "secim") {
    if (!(m in TURLER)) throw new Error("Tür seçilmeli");
    return m;
  }
  if (tip === "metin") return m;
  if (tip === "liste") return parcala(m);
  const out = {};
  for (const satir of m.split("\n").map((s) => s.trim()).filter(Boolean)) {
    const i = satir.indexOf(":");
    if (i < 1) throw new Error("Her satır “ad: basamak, basamak” olmalı");
    const sira = parcala(satir.slice(i + 1));
    if (sira.length < 2) throw new Error(`“${satir.slice(0, i).trim()}” dizisinde en az iki basamak olmalı`);
    out[satir.slice(0, i).trim()] = sira;
  }
  return out;
}

/* Kanıt fişleri: en çok `sinir` FARKLI alıntı. Aynı cümle birden çok değeri kanıtlıyorsa (iki
   kategori terimi tek cümlede) tek fiş olur: "Skills 10 geçiş · Spells 23 geçiş". */
export function kanitlar(a, sinir = 2) {
  const fisler = new Map();
  for (const x of (a.model && a.model.kanit) || []) {
    if (!fisler.has(x.alinti)) fisler.set(x.alinti, { bolum: x.bolum, alinti: x.alinti, kayitlar: [] });
    fisler.get(x.alinti).kayitlar.push(x);
  }
  return [...fisler.values()].slice(0, sinir).map(({ bolum, alinti, kayitlar }) => ({
    bolum, alinti,
    ek: kayitlar.length > 1
      ? kayitlar.map((x) => [x.deger, x.sayi && `${x.sayi} geçiş`].filter(Boolean).join(" ")).join(" · ")
      : kayitlar[0].sayi ? `${kayitlar[0].sayi} geçiş` : "",
  }));
}

export function siraliAlanlar(veri) {
  return [...((veri && veri.alanlar) || [])].sort((a, b) => SIRA.indexOf(a.alan) - SIRA.indexOf(b.alan));
}

export function bekleyenSayisi(veri) {
  return siraliAlanlar(veri).filter((a) => alanDurumu(a).anahtar === "aday").length;
}

/* Son çıkarım işinin tek satırlık özeti. */
export function cikarimMetni(c) {
  if (!c) return "";
  if (c.calisiyor) return "İlk bölümler okunuyor… (bir dakika kadar sürebilir)";
  const s = c.son;
  if (!s) return "Henüz öneri çıkarılmadı.";
  if (s.hata) return `Son deneme başarısız: ${s.hata}`;
  const b = s.bolumler || [];
  const aralik = b.length ? `bölüm ${b[0]}–${b[b.length - 1]}` : "bölüm yok";
  const parca = [`${b.length} bölümden önerildi (${aralik})`];
  if (s.profil) parca.push(`${s.profil.length} alan`);
  if (s.on_tarama) parca.push(`sözlüğe ${s.on_tarama.yazilan.length} aday`);
  return parca.join(" · ");
}
