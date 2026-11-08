import { test } from "node:test";
import assert from "node:assert/strict";
import { bolumBitti, yanit, yeniDurum } from "../../app/web/js/yoklama-yardimci.js";
import { kartHtml } from "../../app/web/js/hiz-karti-yardimci.js";

function tempoBolumleri(n, etkin = true) {
  let d = yeniDurum();
  const out = [];
  for (let i = 0; i < n; i++) {
    const s = bolumBitti(d, { tempo: true, etkin });
    d = s.durum;
    out.push(s);
  }
  return { d, out };
}

test("iki tempo bölümünde bir yoklama, beşincide ölçüm önerisi", () => {
  const { out } = tempoBolumleri(10);
  assert.deepEqual(out.map((s) => s.goster),
    [null, "yoklama", null, "yoklama", "olcum", "yoklama", null, "yoklama", null, "olcum"]);
});

test("serbest bölüm sayacı sıfırlar", () => {
  let { d } = tempoBolumleri(3);
  d = bolumBitti(d, { tempo: false, etkin: true }).durum;
  assert.equal(bolumBitti(d, { tempo: true, etkin: true }).goster, null);
});

test("masadaki telefon: üç etkinliksiz tempo bölümünde durdurma", () => {
  const { out } = tempoBolumleri(3, false);
  assert.deepEqual(out.map((s) => s.duraklat), [false, false, true]);
});

test("Zorlandım hemen -%4; Rahattı yalnız art arda ikincide +%4; İdare eder sıfırlar", () => {
  let d = yeniDurum();
  assert.equal(yanit(d, "zorlandim", 2000).hiz, 1920);
  let s = yanit(d, "rahatti", 2000);
  assert.equal(s.hiz, 2000);
  s = yanit(s.durum, "rahatti", 2000);
  assert.equal(s.hiz, 2080);
  s = yanit(yanit(d, "rahatti", 2000).durum, "idare", 2000);
  assert.equal(yanit(s.durum, "rahatti", 2000).hiz, 2000);
  d = { ...d, etkinsiz: 2 };
  assert.equal(yanit(d, "idare", 2000).durum.etkinsiz, 0);
  assert.equal(yanit(d, "zorlandim", 700).hiz, 700); // alt sınır
});

test("kart: veri yokken yönlendirme, veriyle dakika, hız, değişim, grafik, öbek", () => {
  assert.match(kartHtml(null), /0<\/b> dk/);
  assert.match(kartHtml(null), /hızın burada görünecek/);
  const v = { bugun_dk: 12.5, oturum_sayisi: 11, degisim: 0.1,
    kisisel_hiz: { hdk: 1650, sdk: 254 },
    gunluk: [{ gun: "a", hdk: 1500, sdk: 230, tempo_hdk: null }, { gun: "b", hdk: 1650, sdk: 254, tempo_hdk: 1800 }],
    obek_hizlari: { 3: { hdk: 1700, sdk: 260, n: 4 } } };
  const h = kartHtml(v);
  assert.match(h, /12,5<\/b> dk/);
  assert.match(h, /254<\/b> kel\/dk/);
  assert.match(h, /\+%10/);
  assert.match(h, /<svg class="hk-grafik"/);
  assert.match(h, /Öbek 3 sözcük: <b>260<\/b>/);
});
