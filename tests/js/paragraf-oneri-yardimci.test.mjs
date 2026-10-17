// Paragraf önerisi ve sözlük damgası saf yardımcıları. Çalıştırma: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  damgaOzeti, damgaSatiri, hataMetni, kaydetGovdesi, oneriDurumu, oneriGovdesi,
} from "../../app/web/js/paragraf-oneri-yardimci.js";

test("bilinmeyen mod yeniden çeviriye düşer", () => {
  assert.deepEqual(oneriGovdesi("u", 2, "x"), { url: "u", sira: 2, mod: "yeniden" });
  assert.equal(oneriGovdesi("u", 2, "onar").mod, "onar");
});

test("kaydet gövdesi sunucunun gösterdiği mevcut metni taşır", () => {
  assert.deepEqual(kaydetGovdesi("u", 1, { mevcut: "eski", aday: "yeni" }),
    { url: "u", sira: 1, mevcut: "eski", metin: "yeni" });
});

test("adaysız ya da aynı öneri gösterilmez", () => {
  assert.equal(oneriDurumu({ aday: null, mevcut: "a" }).tur, "yok");
  assert.equal(oneriDurumu({ aday: " a ", mevcut: "a" }).tur, "yok");
  const d = oneriDurumu({ aday: "b", mevcut: "a", kalan: [{}] });
  assert.equal(d.tur, "var");
  assert.match(d.not, /1 şüphe/);
  assert.equal(oneriDurumu({ aday: "b", mevcut: "a" }).not, "");
});

test("hata metinleri: çakışma, bağlantı, sunucu ayrıntısı", () => {
  assert.match(hataMetni(409), /değişmiş/);
  assert.match(hataMetni(0), /ulaşılamadı/);
  assert.equal(hataMetni(500, "kota"), "kota");
});

test("damga: bilinmeyen ve boş fark sessiz, değişen kayıt satırı", () => {
  assert.equal(damgaOzeti(null), null);
  assert.equal(damgaOzeti([]), null);
  assert.match(damgaOzeti([{}, {}]), /^2 terim/);
  assert.equal(damgaSatiri({ source: "Hollow", eski: "Kovan", yeni: "Oyuk" }),
    "Hollow: “Kovan” → “Oyuk”");
  assert.match(damgaSatiri({ source: "X", eski: "Y", yeni: null }), /artık yok/);
});
