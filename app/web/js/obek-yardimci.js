// SAF (DOM'suz, Node testli): öbek modunda bir paragrafın çizim parçaları
// (hızlı okuma planı §7). Öbekler SABİT BOYLUDUR (kullanıcı kararı 2026-11-08: "2 kelime
// 3 kelime gibi öbekler olsun, okuma hızı gibi arttırılabilsin"): görme alıştırmasında
// boy adım adım büyütülür. Cümle sonu öbeği erken bitirir. Arama eşleşmesi öbek sınırını
// aşabilir; o zaman iki parçaya bölünür ve aynı `eslesme` kimliğini taşır.

export const OBEK_EN_KUCUK = 2;
export const OBEK_EN_BUYUK = 6;
const CUMLE_SONU = /[.!?…:;]["”’)]*$/;

export function obekBoyuSinirla(boy) {
  const b = Math.round(Number(boy));
  if (!Number.isFinite(b)) return 3;
  return Math.min(OBEK_EN_BUYUK, Math.max(OBEK_EN_KUCUK, b));
}

// Paragraf başına öbek BİTİŞ konumları: `boy` sözcükte bir, cümle sonunda erken.
export function sabitObekler(metin, boy) {
  const n = obekBoyuSinirla(boy);
  const sinir = [];
  let say = 0;
  const re = /\S+/g;
  let m;
  while ((m = re.exec(metin))) {
    say++;
    const son = m.index + m[0].length;
    if (say >= n || CUMLE_SONU.test(m[0])) {
      sinir.push(son);
      say = 0;
    }
  }
  if (say > 0) sinir.push(metin.trimEnd().length);
  return sinir;
}

// Sunucudaki kitap içi aramayla aynı kural (cache._tr_kucuk): Türkçe küçült, ı = i.
const kat = (s) => s.toLocaleLowerCase("tr").replace(/ı/g, "i");

export function eslesmeler(metin, q) {
  const out = [];
  if (!q) return out;
  const lower = kat(metin);
  const ql = kat(q);
  let i = 0;
  let idx;
  while (ql && (idx = lower.indexOf(ql, i)) !== -1) {
    out.push([idx, idx + q.length]);
    i = idx + q.length;
  }
  return out;
}

// Sınırlar paragrafla uyuşuyor mu: artan, son öğe metnin sonu.
export function gecerliSinirlar(metin, sinirlar) {
  if (!Array.isArray(sinirlar) || !sinirlar.length) return false;
  let onceki = 0;
  for (const s of sinirlar) {
    if (!Number.isInteger(s) || s <= onceki || s > metin.length) return false;
    onceki = s;
  }
  return metin.slice(onceki).trim() === "";
}

// [{t, obek: sıra|null, eslesme: sıra|null}] — öbek başındaki boşluk öbeğe girmez.
export function parcalar(metin, sinirlar, q) {
  const obekler = [];
  if (gecerliSinirlar(metin, sinirlar)) {
    let bas = 0;
    for (const son of sinirlar) {
      let a = bas;
      while (a < son && /\s/.test(metin[a])) a++;
      if (a < son) obekler.push([a, son]);
      bas = son;
    }
  }
  const esler = eslesmeler(metin, q);
  const noktalar = new Set([0, metin.length]);
  for (const [a, b] of [...obekler, ...esler]) {
    noktalar.add(a);
    noktalar.add(b);
  }
  const sirali = [...noktalar].sort((x, y) => x - y);
  const icinde = (aralik, a) => aralik.findIndex(([x, y]) => a >= x && a < y);
  const out = [];
  for (let i = 0; i + 1 < sirali.length; i++) {
    const [a, b] = [sirali[i], sirali[i + 1]];
    if (a === b) continue;
    const o = icinde(obekler, a);
    const e = icinde(esler, a);
    const parca = { t: metin.slice(a, b), obek: o < 0 ? null : o, eslesme: e < 0 ? null : e };
    const son = out[out.length - 1];
    if (son && son.obek === parca.obek && son.eslesme === parca.eslesme) son.t += parca.t;
    else out.push(parca);
  }
  return out;
}
