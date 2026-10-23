// Vertex kredi göstergesinin saf yardımcıları. Çalıştırma: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  bitisMetni, dokumMetni, hizMetni, kaynakMetni, ozet, para, tarihMetni, zamanOrani,
} from "../../app/web/js/kredi-yardimci.js";

const D = {
  tutar: 300, kullanilan: 166, kalan: 134, oran: 0.5533, tahmin: 1, son_7_gun: 35,
  bitis: "2026-12-10", kalan_gun: 48, deneme_gun: 90,
  okuma: { tutar: 165, zaman: "2026-10-23T10:15:00+00:00" },
  modeller: [
    { model: "gemini-3.8-flash", maliyet: 56.2 },
    { model: "gemini-9-ultra", maliyet: 0, fiyat_bilinmiyor: true },
  ],
};

test("para: 10 $ üstü tam, altı iki basamak", () => {
  assert.equal(para(166.4), "166 $");
  assert.equal(para(1.15), "1,15 $");
});

test("tarih Türkçe ay adıyla yazılır", () => {
  assert.equal(tarihMetni("2026-12-10"), "10 Aralık 2026");
  assert.equal(tarihMetni("2026-10-23T10:15:00+00:00"), "23 Ekim 2026");
});

test("özet kullanılan, oran ve kalanı verir", () => {
  assert.deepEqual(ozet(D), { baslik: "≈166 $", toplam: "/ 300 $", alt: "%55 kullanıldı · 134 $ kaldı", yuzde: 55 });
});

test("hız süre dolmadan bitecekse uyarır", () => {
  const h = hizMetni(D); // günde 5 $ → 26 gün < 48
  assert.equal(h.uyari, true);
  assert.equal(h.metin, "Son 7 gün 35 $ (günde ≈5,00 $). Bu hızla ≈26 günde biter, süre dolmadan.");
});

test("hız yavaşsa kullanılmamış kalacak tutarı söyler", () => {
  const h = hizMetni({ ...D, son_7_gun: 7 }); // günde 1 $ → 134 gün > 48
  assert.equal(h.uyari, false);
  assert.match(h.metin, /≈134 günde biter; süre dolduğunda ≈86 \$ kullanılmamış kalır\.$/);
});

test("ölçüm yoksa ya da tarih yoksa uydurulmaz", () => {
  assert.equal(hizMetni({ ...D, son_7_gun: 0 }).metin, "Son 7 günde ölçülen harcama yok.");
  assert.match(hizMetni({ ...D, kalan_gun: null }).metin, /günde biter\.$/);
  assert.equal(bitisMetni({ ...D, bitis: null }), "Bitiş tarihi girilmedi.");
  assert.equal(zamanOrani({ ...D, kalan_gun: null }), null);
});

test("bitiş ve geçen süre oranı", () => {
  assert.equal(bitisMetni(D), "Bitiş 10 Aralık 2026 · 48 gün kaldı");
  assert.equal(bitisMetni({ ...D, kalan_gun: 0 }), "Süre doldu (10 Aralık 2026).");
  assert.ok(Math.abs(zamanOrani(D) - 42 / 90) < 1e-9);
});

test("döküm fiyatı bilinmeyen modeli saklamaz", () => {
  assert.equal(dokumMetni(D), "Okumadan sonra: 3.8-flash 56 $ · 9-ultra (fiyatı bilinmiyor)");
  assert.equal(dokumMetni({ ...D, okuma: null }), "3.8-flash 56 $ · 9-ultra (fiyatı bilinmiyor)");
});

test("kaynak konsol okumasını ya da Google ölçümünü söyler", () => {
  assert.equal(kaynakMetni(D), "Konsol okuması 165 $ (23 Ekim 2026) + sonrasının tahmini 1,00 $.");
  assert.match(kaynakMetni({ ...D, okuma: null, ilk_olcum: "2026-09-11T17:00Z" }), /^Google'ın token ölçümü × fiyat tablosu, 11 Eylül 2026 itibarıyla\./);
});
