import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ESKI_HIZLAR, HIZ_ALT, HIZ_UST, YEDEK_HIZ, adim, centikDolu, hizAdimi, hizSinirla, pxSn, seviyedenHiz,
} from "../../app/web/js/oto-kaydir-yardimci.js";

test("hız 700-4500 harf/dk aralığında kalır, geçersiz değer yedeğe döner", () => {
  assert.equal(hizSinirla(100), HIZ_ALT);
  assert.equal(hizSinirla(99999), HIZ_UST);
  assert.equal(hizSinirla(undefined), YEDEK_HIZ);
  assert.equal(hizSinirla("2000"), 2000);
});

test("− / + yüzde 5 adımla değişir, sınırı aşmaz", () => {
  assert.equal(hizAdimi(2000, 1), 2100);
  assert.equal(hizAdimi(2000, -1), 1900);
  assert.equal(hizAdimi(4400, 1), HIZ_UST);
  assert.equal(hizAdimi(710, -1), HIZ_ALT);
});

test("harf/dk piksel/sn'ye bölümün çizilmiş yoğunluğuyla çevrilir", () => {
  // 3000 harf 1500 px'e çizilmiş: 1800 harf/dk = 30 harf/sn = 15 px/sn.
  assert.equal(pxSn(1800, 1500, 3000), 15);
  // Yazı büyüyünce (aynı harf daha yüksek) aynı okuma hızı daha hızlı kaydırır.
  assert.equal(pxSn(1800, 3000, 3000), 30);
});

test("çizilmemiş bölümde NaN/Infinity yerine null döner", () => {
  assert.equal(pxSn(1800, 0, 3000), null);
  assert.equal(pxSn(1800, 1500, 0), null);
  assert.equal(seviyedenHiz(4, 0, 3000), null);
});

test("eski seviye o anki çizimle aynı px/sn'yi veren harf/dk'ya çevrilir", () => {
  // Telefonda satır ~40 harf, 33 px: 3000 harf ≈ 2475 px. Seviye 4 = 16 px/sn.
  const h = seviyedenHiz(4, 2475, 3000);
  assert.ok(Math.abs(pxSn(h, 2475, 3000) - ESKI_HIZLAR[3]) < 0.02);
  // Sınır dışına düşen seviye sınırlanır (seviye 12 çok hızlı).
  assert.equal(seviyedenHiz(12, 2475, 3000), HIZ_UST);
  assert.equal(seviyedenHiz(1, 2475, 3000), HIZ_ALT);
});

test("çentik hızın sınırlar arasındaki yerini gösterir", () => {
  assert.equal(centikDolu(HIZ_ALT, 12), 1);
  assert.equal(centikDolu(HIZ_UST, 12), 12);
  assert.equal(centikDolu(2600, 12), 7);
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
