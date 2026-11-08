import { test } from "node:test";
import assert from "node:assert/strict";
import {
  BOSTA_MS, atlama, etkinlik, harfSay, oranGuncelle, oturumSonucu, sozcukDk, sozcukSay, sureEkle, yeniOturum,
} from "../../app/web/js/okuma-hizi-yardimci.js";

const ACIK = { gorunur: true, diyalog: false, tempoAkiyor: false };
const TEMPO = { gorunur: true, diyalog: false, tempoAkiyor: true };

function oturum(over = {}) {
  return yeniOturum({ id: "oturum-0001", url: "u1", slug: "s", harf: 3000, sozcuk: 460,
    acilisOrani: 0, simdi: 0, ...over });
}

// Saniyelik tık: 0..ms arası her saniyede bir sureEkle (gerçek zamanlayıcıyı taklit eder).
function tikla(o, bas, bit, durum, etkinlikAni = []) {
  for (let t = bas + 1000; t <= bit; t += 1000) {
    if (etkinlikAni.includes(t)) etkinlik(o, t);
    sureEkle(o, t, durum);
  }
}

test("harf boşluk dışı karakter, sözcük boşlukla ayrılan parça", () => {
  assert.equal(harfSay(["Bir iki.", "  üç  "]), 9);
  assert.equal(sozcukSay(["Bir iki.", "  üç  ", ""]), 3);
});

test("serbest okumada süre birikir, 90 sn etkinlik yoksa fazlası sayılmaz", () => {
  const o = oturum();
  tikla(o, 0, 60_000, ACIK, [30_000]);
  assert.equal(o.aktifMs, 60_000);
  tikla(o, 60_000, 300_000, ACIK); // son etkinlik 30. sn: 120. sn'den sonrası sayılmaz
  assert.equal(o.aktifMs, 30_000 + BOSTA_MS);
});

test("sekme gizliyken ve diyalog açıkken süre sayılmaz", () => {
  const o = oturum();
  tikla(o, 0, 10_000, ACIK, [5_000]);
  tikla(o, 10_000, 20_000, { ...ACIK, gorunur: false });
  tikla(o, 20_000, 30_000, { ...ACIK, diyalog: true });
  assert.equal(o.aktifMs, 10_000);
});

test("kısılmış zamanlayıcıdan sonra koca aralık sayılmaz", () => {
  const o = oturum();
  sureEkle(o, 60_000, ACIK);
  assert.equal(o.aktifMs, 2_000);
});

test("tempo akarken etkinlik olmasa da süre birikir; karışık bölüm tempo sayılır", () => {
  const o = oturum();
  tikla(o, 0, 30_000, ACIK, [1_000]);
  tikla(o, 30_000, 230_000, TEMPO, [100_000]);
  const s = oturumSonucu(o, true);
  assert.equal(s.mode, "tempo");
  assert.equal(s.active_ms, 230_000);
});

test("masadaki telefon: tempo bölümünde hiç dokunma yoksa süre 0 ve geçersiz", () => {
  const o = oturum();
  tikla(o, 0, 200_000, TEMPO);
  const s = oturumSonucu(o, true);
  assert.equal(s.active_ms, 0);
  assert.equal(s.gecerli, false);
});

test("geçerlilik: bitmiş, 1500 harf, 60 sn, 400-5000 harf/dk", () => {
  const o = oturum();
  tikla(o, 0, 120_000, ACIK, [30_000, 60_000, 90_000]);
  assert.equal(oturumSonucu(o, true).gecerli, true); // 1500 harf/dk
  assert.equal(oturumSonucu(o, false).gecerli, false); // yarım
  const kisa = oturum({ harf: 1000 });
  tikla(kisa, 0, 120_000, ACIK, [30_000, 60_000, 90_000]);
  assert.equal(oturumSonucu(kisa, true).gecerli, false);
  const hizli = oturum({ harf: 12000 });
  tikla(hizli, 0, 120_000, ACIK, [30_000, 60_000, 90_000]);
  assert.equal(oturumSonucu(hizli, true).gecerli, false); // 6000 harf/dk: göz gezdirme
});

test("ortadan başlanan bölüm ve atlama ölçümü geçersiz yapar", () => {
  const orta = oturum({ acilisOrani: 0.4 });
  tikla(orta, 0, 120_000, ACIK, [30_000, 60_000, 90_000]);
  assert.equal(oturumSonucu(orta, true).gecerli, false);

  const sicrama = oturum();
  oranGuncelle(sicrama, 0.1);
  oranGuncelle(sicrama, 0.35); // tek adımda 0,25
  tikla(sicrama, 0, 120_000, ACIK, [30_000, 60_000, 90_000]);
  assert.equal(oturumSonucu(sicrama, true).gecerli, false);

  const arama = oturum();
  tikla(arama, 0, 120_000, ACIK, [30_000, 60_000, 90_000]);
  atlama(arama);
  assert.equal(oturumSonucu(arama, true).gecerli, false);
});

test("geçersiz oturumun süresi yine gönderilir (pratik dakikası)", () => {
  const o = oturum({ acilisOrani: 0.5 });
  tikla(o, 0, 30_000, ACIK, [10_000]);
  const s = oturumSonucu(o, false);
  assert.equal(s.active_ms, 30_000);
  assert.equal(s.chars, 3000);
  assert.equal(s.words, 460);
});

test("sözcük/dk o bölümün sözcük uzunluğuyla, bilinmiyorsa 6,5 ile", () => {
  assert.equal(sozcukDk(1500, 3000, 500), 250);
  assert.equal(sozcukDk(1300, 0, 0), 200);
});

test("öbek modunda açılan oturum bayrağını taşır", () => {
  assert.equal(oturumSonucu(oturum({ obek: true }), false).obek, true);
  assert.equal(oturumSonucu(oturum(), false).obek, false);
});
