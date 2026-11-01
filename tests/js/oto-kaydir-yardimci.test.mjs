import { test } from "node:test";
import assert from "node:assert/strict";
import { HIZLAR, VARSAYILAN_SEVIYE, adim, hiz, seviyeSinirla } from "../../app/web/js/oto-kaydir-yardimci.js";

test("seviye 1..12 aralığında kalır, geçersiz değer varsayılana döner", () => {
  assert.equal(seviyeSinirla(0), 1);
  assert.equal(seviyeSinirla(99), HIZLAR.length);
  assert.equal(seviyeSinirla(undefined), VARSAYILAN_SEVIYE);
  assert.equal(seviyeSinirla("7"), 7);
});

test("hızlar sıralı artar, seviye hıza çevrilir", () => {
  for (let i = 1; i < HIZLAR.length; i++) assert.ok(HIZLAR[i] > HIZLAR[i - 1]);
  assert.equal(hiz(1), HIZLAR[0]);
  assert.equal(hiz(HIZLAR.length), HIZLAR.at(-1));
});

test("yavaş hızda kesir birikir, kaydırma yine ilerler", () => {
  let b = 0, toplam = 0;
  for (let i = 0; i < 60; i++) {  // 60 kare x 16,67 ms = 1 sn, 6 px/sn
    const s = adim(b, 6, 1000 / 60);
    b = s.birikim; toplam += s.px;
  }
  assert.equal(toplam, 5);  // 6'ya çok yakın: kalan kesir sonraki kareye taşınır
  assert.ok(b > 0.9 && b < 1);
});

test("arka plandan dönüşte koca aralık tek karede zıplatmaz", () => {
  assert.equal(adim(0, 90, 60_000).px, 9);  // 100 ms ile sınırlı
  assert.equal(adim(0, 90, -5).px, 0);
});
