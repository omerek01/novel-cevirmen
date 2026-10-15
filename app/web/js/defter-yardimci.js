/* Defter ekranının SAF yardımcıları (DOM yok; Node testli: tests/js/defter-yardimci.test.mjs).

   Veri `/api/book/{slug}/defter` (liste) ve `/defter/kart` (karakter kartı) yanıtıdır.
   Sunucu süzgeci (spoiler) zaten uygulanmıştır; burada yalnız arama, etiket ve yerleşim. */

export const SEKMELER = [
  { anahtar: "kisiler", etiket: "Kişiler", tekil: "kişi", tur: null },
  { anahtar: "yaratiklar", etiket: "Yaratıklar", tekil: "yaratık", tur: "yaratik" },
  { anahtar: "anilar", etiket: "Anılar", tekil: "anı", tur: "ani" },
  { anahtar: "nitelikler", etiket: "Nitelikler", tekil: "nitelik", tur: "nitelik" },
  { anahtar: "yankilar", etiket: "Gölge ve yankılar", tekil: "gölge/yankı", tur: "yanki" },
  { anahtar: "gruplar", etiket: "Klan ve gruplar", tekil: "grup", tur: null },
];

const ALAN_ETIKETLERI = {
  gercek_adi: "Gerçek ad", rutbesi: "Rütbe", sinifi: "Sınıf", gorunusu: "Görünüş",
  gorunus_rutbesi: "Görünüş rütbesi", kusuru: "Kusur", ruya_capasi: "Rüya çapası", yetenegi: "Yetenekler",
  "Shadow Cores": "Gölge çekirdeği", "Shadow Fragments": "Gölge parçası", "Soul Cores": "Ruh çekirdeği",
  "Soul Fragments": "Ruh parçası", Soul: "Ruh", "Shadow Core": "Çekirdek rütbesi", "Soul Core": "Çekirdek rütbesi",
  "Shadow Dance Mastery Level": "Gölge Dansı ustalığı", "Death Charge": "Ölüm yükü",
  "Vanquished Foes": "Yenilen düşman", "Nightmares required": "Gereken kabus", "Dormant Nightmares": "Uykuda kabus",
  rutbe: "Rütbe", kademe: "Kademe", tur: "Tür", sinif: "Sınıf", aciklama: "Açıklama", nitelikler: "Nitelikler",
  yetenekler: "Yetenekler",
};
// Anı ve gölgelerin rün sayaçları (Dying Wish'in ölüm yükü, Saint'in gölge parçası…).
const SAYAC_ALANLARI = ["Shadow Fragments", "Nightmares required", "Dormant Nightmares", "Death Charge",
  "Vanquished Foes"];

/* Kaydın sayaçları okunur metin olarak: ["Gölge parçası 146/200", …]. */
export function sayacMetinleri(alanlar) {
  return SAYAC_ALANLARI.filter((a) => alanlar && alanlar[a] != null).map((a) => `${alanEtiketi(a)} ${alanlar[a]}`);
}
export const RUN_ALANLARI = ["gercek_adi", "rutbesi", "sinifi", "gorunusu", "gorunus_rutbesi", "kusuru",
  "ruya_capasi", "yetenegi"];

/* Rün listesi satırları: bilinen alanlar sabit sırada, sonra sayaçlar; çok değerli alan
   (yetenekler) tek satırda toplanır. Her satır {ad, kayitlar: [...]} */
export function runSatirlari(run) {
  const gruplar = new Map();
  for (const k of run || []) {
    if (!gruplar.has(k.ad)) gruplar.set(k.ad, []);
    gruplar.get(k.ad).push(k);
  }
  const sira = (ad) => (RUN_ALANLARI.includes(ad) ? RUN_ALANLARI.indexOf(ad) : RUN_ALANLARI.length);
  return [...gruplar.entries()]
    .sort(([a], [b]) => sira(a) - sira(b) || a.localeCompare(b))
    .map(([ad, kayitlar]) => ({ ad, kayitlar }));
}

/* Anı kademesi: rünlerde Roma rakamı (I–IX); "unknown" gibi değerler gösterilmez. */
export function kademeMetni(kademe) {
  const k = (kademe || "").trim();
  return /^[IVX]+$/.test(k) ? `${k}. kademe` : "";
}

export function alanEtiketi(ad) {
  return ALAN_ETIKETLERI[ad] || ad;
}

// Rünlerdeki eşya türleri sözlükte çoğu zaman yok; okunur kalsın diye sabit karşılık.
const ESYA_TURLERI = {
  Weapon: "Silah", Armor: "Zırh", Tool: "Araç", Charm: "Tılsım", Ornament: "Süs", Jewel: "Mücevher",
  Shield: "Kalkan", Clothing: "Giysi", Vessel: "Kap", Trinket: "Biblo",
};

/* Rün değerinin okunur hâli: sözlük karşılığı > bilinen eşya türü > değerin kendisi. */
export function tr(deger, karsiliklar) {
  if (!deger) return "";
  return (karsiliklar && karsiliklar[deger]) || ESYA_TURLERI[deger] || deger;
}

const kucuk = (s) => (s || "").toLocaleLowerCase("tr");

export function sekmeSatirlari(veri, sekme, sorgu) {
  const satirlar = (veri && veri[sekme]) || [];
  const q = kucuk(sorgu).trim();
  if (!q) return satirlar;
  return satirlar.filter((k) => [k.ad, k.tr, ...(k.takma || []), ...(k.takma_tr || [])]
    .some((x) => kucuk(x).includes(q)));
}

/* ---------- Türkçe sayı ekleri (983'e, 30'a; 15'i, 4'ü) ---------- */
function sonOkunus(n) {
  // Sayının okunuşundaki SON sözcüğün ünlüsü ek seçer: 983 -> "üç", 30 -> "otuz", 100 -> "yüz".
  n = Math.abs(Math.trunc(n));
  if (n === 0) return "sıfır";
  const birler = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"];
  const onlar = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"];
  if (n % 10) return birler[n % 10];
  if (n % 100) return onlar[(n % 100) / 10];
  if (n % 1000) return "yüz";
  if (n % 1000000) return "bin";
  return "milyon";
}
function sonUnlu(sozcuk) {
  const m = sozcuk.match(/[aeıioöuü](?=[^aeıioöuü]*$)/);
  return m ? m[0] : "e";
}
const unluyleBiter = (s) => /[aeıioöuü]$/.test(s);

export function yonelmeEki(n) {
  const s = sonOkunus(n);
  const ek = "aıou".includes(sonUnlu(s)) ? "a" : "e";
  return `${n}’${unluyleBiter(s) ? "y" : ""}${ek}`;
}
export function iyelikEki(n) {
  const s = sonOkunus(n);
  const u = sonUnlu(s);
  const ek = { a: "ı", ı: "ı", o: "u", u: "u", e: "i", i: "i", ö: "ü", ü: "ü" }[u];
  return `${n}’${unluyleBiter(s) ? "s" : ""}${ek}`;
}

export function sinirMetni(sinir) {
  return sinir == null ? "Tüm kitap" : `Bölüm ${yonelmeEki(sinir)} kadar`;
}

export function hitapNotu(h) {
  if (h.elle) return `Senin kararın: “${h.bicim}”`;
  const uyan = Math.round((h.oran || 0) * (h.n || 0));
  if (h.kararli) return `Son ${h.n} kaydın ${iyelikEki(uyan)} “${h.bicim}” · son bölüm ${h.son_bolum}`;
  return `${h.n} kaydın ${iyelikEki(uyan)} “${h.bicim}” · karışık; seçersen sonraki çeviriler buna uyar`;
}

/* ---------- bağ çizimi: seçili kişinin en güçlü komşuları ---------- */
export function egoDugumleri(baglar, sinir = 6) {
  const kisiler = new Map();
  for (const b of baglar || []) {
    const onayli = b.durum === "onaylandi" || (b.guven || 0) >= 0.8;
    const k = kisiler.get(b.diger_kimlik) || { kimlik: b.diger_kimlik, ad: b.diger_ad, etiket: b.etiket, destek: -1, aday: true };
    if ((b.destek || 0) > k.destek) Object.assign(k, { etiket: b.etiket, destek: b.destek || 0 });
    if (onayli) k.aday = false;
    kisiler.set(b.diger_kimlik, k);
  }
  const secilen = [...kisiler.values()].sort((a, b) => b.destek - a.destek).slice(0, sinir);
  const n = secilen.length;
  return secilen.map((k, i) => {
    const aci = -Math.PI * 0.85 + (i * 2 * Math.PI) / Math.max(n, 1);
    return { ...k, x: Math.round(170 + 128 * Math.cos(aci)), y: Math.round(100 + 70 * Math.sin(aci)) };
  });
}

/* ---------- elle kayıt formu ---------- */
const BOLUM = { ad: "ilk_bolum", etiket: "İlk bölüm (boş = okuma konumun)", tip: "sayi" };
const FORMLAR = {
  ani: [{ ad: "ad", etiket: "Anının adı (İngilizce)", tip: "metin" }, { ad: "rutbe", etiket: "Rütbe", tip: "metin" },
    { ad: "kademe", etiket: "Kademe", tip: "metin" }, { ad: "tur", etiket: "Tür (Weapon, Armor…)", tip: "metin" }, BOLUM],
  efsun: [{ ad: "ad", etiket: "Efsunun adı (İngilizce)", tip: "metin" },
    { ad: "aciklama", etiket: "Açıklama", tip: "uzun" }, BOLUM],
  nitelik: [{ ad: "ad", etiket: "Niteliğin adı (İngilizce)", tip: "metin" }, BOLUM],
  golge: [{ ad: "ad", etiket: "Gölgenin adı", tip: "metin" }, { ad: "rutbe", etiket: "Rütbe", tip: "metin" },
    { ad: "sinif", etiket: "Sınıf", tip: "metin" }, BOLUM],
  yanki: [{ ad: "ad", etiket: "Yankının adı", tip: "metin" }, { ad: "rutbe", etiket: "Rütbe", tip: "metin" },
    { ad: "sinif", etiket: "Sınıf", tip: "metin" }, BOLUM],
  yaratik: [{ ad: "ad", etiket: "Yaratığın adı (İngilizce)", tip: "metin" }, { ad: "rutbe", etiket: "Rütbe", tip: "metin" },
    { ad: "sinif", etiket: "Sınıf", tip: "metin" }, BOLUM],
  alan: [{ ad: "ad", etiket: "Alan", tip: "secim", secenekler: RUN_ALANLARI },
    { ad: "deger", etiket: "Değer", tip: "metin" }, BOLUM],
};

export function kayitFormu(tur) {
  return FORMLAR[tur] || [];
}

export function formdanKayit(tur, degerler, sahip) {
  const ad = (degerler.ad || "").trim();
  if (!ad) throw new Error("Ad boş olamaz");
  const kayit = { tur, sahip: sahip || "", ad, alanlar: {} };
  const bolum = String(degerler.ilk_bolum ?? "").trim();
  if (bolum) {
    const n = Number(bolum);
    if (!Number.isInteger(n) || n < 0) throw new Error("Bölüm numarası geçersiz");
    kayit.ilk_bolum = n;
  }
  for (const alan of kayitFormu(tur)) {
    if (["ad", "ilk_bolum"].includes(alan.ad)) continue;
    const v = String(degerler[alan.ad] ?? "").trim();
    if (!v) continue;
    if (alan.ad === "deger") kayit.deger = v;
    else kayit.alanlar[alan.ad] = v;
  }
  return kayit;
}
