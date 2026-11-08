// SAF (DOM'suz, Node testli): bölüm okuma oturumunun süre ve geçerlilik hesabı
// (hızlı okuma planı §1, 2026-11-08, docs/superpowers/plans/2026-11-08-hizli-okuma.md).
//
// Ölçüm birimi BÖLÜMDÜR: kaydırma konumu okunan satırı göstermez, bu yüzden kısmi
// oranlardan hız çıkarılmaz. Süre saniyelik tıkla birikir; sekme gizliyken ya da
// diyalog açıkken sayılmaz. Sunucu geçerliliği yeniden hesaplar; buradaki karar ön
// süzgeçtir (aynı sınırlar: reading_log.py).

export const HARF_SOZCUK = 6.5; // sözcük karşılığı gereken tek sabit
export const BOSTA_MS = 90_000; // serbest okumada iki etkinlik arası bundan uzunsa fazlası sayılmaz
export const EN_UZUN_TIK_MS = 2_000; // kısılmış zamanlayıcı dönüşünde koca aralık sayılmasın
export const EN_AZ_HARF = 1500;
export const EN_AZ_MS = 60_000;
export const HIZ_ALT = 400;
export const HIZ_UST = 5000;
export const ACILIS_SINIRI = 0.1; // ortadan başlanan bölüm ölçülmez
export const ATLAMA_SINIRI = 0.2; // tek adımda bundan fazla ilerleme = atlama
export const BITIS_ORANI = 0.9; // sonraki bölüme geçerken bu kadar okunmadıysa yarım

export function harfSay(paras) {
  let n = 0;
  for (const p of paras || []) n += String(p).replace(/\s+/g, "").length;
  return n;
}

export function sozcukSay(paras) {
  let n = 0;
  for (const p of paras || []) {
    const t = String(p).trim();
    if (t) n += t.split(/\s+/).length;
  }
  return n;
}

export function yeniOturum({ id, url, slug, harf, sozcuk, acilisOrani, simdi, obek = false }) {
  return {
    id, url, slug, harf, sozcuk, obek: !!obek,
    aktifMs: 0,
    sonZaman: simdi,
    sonEtkinlik: simdi,
    sonOran: acilisOrani || 0,
    enCokOran: acilisOrani || 0,
    gecersiz: (acilisOrani || 0) > ACILIS_SINIRI,
    tempo: false, // bir an bile otomatik kaydırma açıldıysa tempo
    tempoEtkin: false, // tempo bölümünde okurdan gelen dokunma ya da yanıt
  };
}

// Saniyelik tık: son tıktan beri geçen süreyi, sayılabildiği kadarıyla ekler.
export function sureEkle(o, simdi, { gorunur, diyalog, tempoAkiyor }) {
  const fark = Math.min(Math.max(simdi - o.sonZaman, 0), EN_UZUN_TIK_MS);
  o.sonZaman = simdi;
  if (tempoAkiyor) o.tempo = true;
  if (!gorunur || diyalog || fark === 0) return;
  if (tempoAkiyor) {
    o.aktifMs += fark; // akış okuru ekranda tutar; masadaki telefonu bölüm sonu yakalar
    return;
  }
  // Serbest okuma (ya da duraklatılmış tempo): son etkinlikten 90 sn sonrası sayılmaz.
  const sinir = o.sonEtkinlik + BOSTA_MS;
  o.aktifMs += Math.max(0, Math.min(simdi, sinir) - (simdi - fark));
}

export function etkinlik(o, simdi) {
  o.sonEtkinlik = simdi;
  o.tempoEtkin = true;
}

// Kaydırma sırasında bölüm içi oran. Tek adımda büyük sıçrama atlamadır.
export function oranGuncelle(o, oran) {
  if (oran - o.sonOran > ATLAMA_SINIRI) o.gecersiz = true;
  o.sonOran = oran;
  if (oran > o.enCokOran) o.enCokOran = oran;
}

export function atlama(o) {
  o.gecersiz = true;
}

// Gönderilecek gövde. `bitti`: bölüm sonuna ulaşıldı (yarım ya da ara gönderimde false).
export function oturumSonucu(o, bitti) {
  let aktif = Math.round(o.aktifMs);
  // Tempo bölümü boyunca okurdan hiç iz yoksa (masadaki telefon) süre sayılmaz.
  if (o.tempo && !o.tempoEtkin) aktif = 0;
  const hdk = aktif > 0 ? (o.harf * 60_000) / aktif : 0;
  const gecerli = !!bitti && !o.gecersiz && o.harf >= EN_AZ_HARF && aktif >= EN_AZ_MS &&
    hdk >= HIZ_ALT && hdk <= HIZ_UST;
  return {
    oturum_id: o.id,
    url: o.url,
    slug: o.slug,
    mode: o.tempo ? "tempo" : "serbest",
    chars: o.harf,
    words: Math.min(o.sozcuk, o.harf),
    active_ms: aktif,
    gecerli,
    obek: !!o.obek,
  };
}

// harf/dk → ekranda gösterilecek sözcük/dk (o bölümün ortalama sözcük uzunluğuyla).
export function sozcukDk(hizHdk, harf, sozcuk) {
  const uzunluk = harf > 0 && sozcuk > 0 ? harf / sozcuk : HARF_SOZCUK;
  return Math.round(hizHdk / uzunluk);
}
