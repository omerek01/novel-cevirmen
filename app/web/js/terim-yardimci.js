/* Terim paneli için SAF yardımcılar (DOM yok; Node'da test edilir:
   tests/js/terim-yardimci.test.mjs). */

/* `glossary.normalize_source`'un hafif JS eşi: çevresel noktalama kırpılır, İngilizce
   iyelik eki KORUNUR (kullanıcı ne eklediğini görsün, sunucu zaten köke indiriyor).
   Sunucudaki `set_term` normalize ETMEZ — kırpma burada olmazsa sözlükte
   "Silverwing Town." gibi noktalı anahtarlar birikir. */
export function trimSecim(text) {
  return (text || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[^\p{L}\p{N}]+/u, "")
    .replace(/[^\p{L}\p{N}'’]+$/u, "");
}

function kacis(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/* `translate._term_regex`'in hafif eşi: kelime parçaları arasına esnek ayırıcı
   (`Ore Empire` · `OreEmpire` · `Ore-Empire`, düz/kıvrık kesme). Çekim eki
   toleransı sunucuda; burada yalnız "paragrafta geçiyor mu" sorusu soruluyor. */
export function terimDeseni(terim) {
  const parcalar = (terim || "")
    .trim()
    .split(/[\s\-_'’]+/)
    .flatMap((p) => p.split(/(?<=[a-z])(?=[A-Z])/))
    .filter(Boolean)
    .map(kacis);
  if (!parcalar.length) return null;
  return new RegExp(`(?<![\\p{L}\\p{N}])${parcalar.join("[\\s\\-_'’]*")}(?![\\p{L}\\p{N}])`, "iu");
}

export const ORNEK_CUMLE_MAX = 300; // glossary KOKEN_CUMLE_MAX ile aynı

/* Terimin geçtiği ilk cümle (sunucudaki `translate.cumle_bul` ile aynı ayırıcı). */
export function cumleBul(metin, terim) {
  const desen = terimDeseni(terim);
  if (!desen || !metin) return null;
  for (const satir of metin.split(/\n/)) {
    for (const cumle of satir.split(/(?<=[.!?…])\s+/)) {
      const c = cumle.trim();
      if (c && desen.test(c)) return c.slice(0, ORNEK_CUMLE_MAX);
    }
  }
  return null;
}

/* Cümle başında büyük harfle gelen sıradan sözcükler özel ad ADAYI değildir. */
const BASLANGIC_SOZCUKLERI = new Set(
  (
    "The A An He She It They We I You His Her Its Their Our My Your But And Or Then " +
    "When What Why How Who Where This That These Those There If As In On At So Yes No " +
    "Was Were Did Do Does Is Are Be Of To For With After Before Still Even Now Just Not " +
    "Only Once Also Well Oh Ah Hmm Perhaps Maybe All Some Every Each Instead However"
  ).split(" ")
);

const BUYUK_DIZI =
  /[A-Z][\p{L}\p{N}'’-]*(?:\s+(?:of\s+the\s+|of\s+|the\s+)?[A-Z][\p{L}\p{N}'’-]*)*/gu;

/* Kaynak terim ADAYLARI — okuyucu Türkçe metinden seçim yaptığında hizalı İngilizce
   paragraftan çıkarılır. Belge kuralı: hizalı paragraf kelime hizalaması DEĞİLDİR,
   yani aday OTOMATİK SEÇİLMEZ; kullanıcı dokunarak seçer.
   Sıra: önce sözlükte KAYITLI olup paragrafta geçenler (karşılıklarıyla), sonra
   büyük harfle başlayan diziler. */
export function adayTerimler(paragraf, terms = {}, max = 12) {
  const cikti = [];
  const gorulen = new Set();
  const anahtar = (s) => s.replace(/[\s\-_'’]+/g, "").toLowerCase();
  const ekle = (source, target) => {
    const k = anahtar(source);
    if (!k || gorulen.has(k) || cikti.length >= max) return;
    gorulen.add(k);
    cikti.push({ source, target: target ?? null, kayitli: target != null });
  };
  if (!paragraf) return cikti;
  // Uzun kayıt önce: "Silver Tower" kayıtlıyken "Tower" ayrıca aday olmasın.
  const kayitlilar = Object.keys(terms).sort((a, b) => b.length - a.length);
  const kapsanan = [];
  for (const kaynak of kayitlilar) {
    const desen = terimDeseni(kaynak);
    const m = desen && paragraf.match(desen);
    if (!m) continue;
    ekle(kaynak, terms[kaynak]);
    kapsanan.push(anahtar(m[0]));
  }
  for (const m of paragraf.matchAll(BUYUK_DIZI)) {
    let sozcukler = m[0].split(/\s+/);
    while (sozcukler.length && BASLANGIC_SOZCUKLERI.has(sozcukler[0])) sozcukler = sozcukler.slice(1);
    const aday = trimSecim(sozcukler.join(" "));
    if (!aday || aday.length < 2) continue;
    const k = anahtar(aday);
    if (kapsanan.some((c) => c.includes(k))) continue;
    ekle(aday, null);
  }
  return cikti;
}

/* Yeniden çeviri işinin bir bölüm sonucunu tek satırlık metne çevirir. */
export function sonucEtiketi(sonuc) {
  if (!sonuc) return "";
  if (sonuc.durum === "hata") return "HATA" + (sonuc.mesaj ? ": " + sonuc.mesaj : "");
  const parcalar = ["YENİLENDİ"];
  if (!sonuc.hizali) parcalar.push("hizalama tutmadı");
  if (sonuc.ihlal) parcalar.push(`${sonuc.ihlal} sözlük ihlali`);
  if (sonuc.kalinti) parcalar.push(`${sonuc.kalinti} İngilizce kalıntı`);
  if (sonuc.model) parcalar.push(sonuc.model);
  return parcalar.join(" · ");
}

/* Telefondaki bölüm kopyası bayat mı: sunucudaki çeviri (ceviri_zamani, sn) kopyanın
   indirildiği andan (Date başlığı, ms) SONRA mı yazıldı. Date saniye çözünürlüklüdür;
   2 sn pay, aynı istekte çevrilip indirilen bölümü "bayat" saymamak için. Bilinmeyen
   değerde bayat DENMEZ — gereksiz yeniden indirme, eksik tazelemeden pahalı değil
   ama sonsuz döngüye dönebilirdi. */
export function onbellekBayatMi(indirilmeMs, ceviriZamaniSn) {
  if (!Number.isFinite(indirilmeMs) || !Number.isFinite(ceviriZamaniSn)) return false;
  return ceviriZamaniSn * 1000 > indirilmeMs + 2000;
}
