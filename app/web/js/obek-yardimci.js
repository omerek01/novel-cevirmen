// SAF (DOM'suz, Node testli): öbek modunda bir paragrafın çizim parçaları
// (hızlı okuma planı §7). Öbek sınırları sunucudan gelir (`/api/chapter/obekler`):
// paragraf başına öbek BİTİŞ konumları. Arama eşleşmesi öbek sınırını aşabilir; o zaman
// iki parçaya bölünür ve aynı `eslesme` kimliğini taşır (sayaç onu tek sayar).

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
