// Terim paneli saf yardımcıları. Çalıştırma: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  adayTerimler,
  cumleBul,
  sonucEtiketi,
  terimDeseni,
  trimSecim,
} from "../../app/web/js/terim-yardimci.js";

test("trimSecim çevresel noktalamayı kırpar, iyelik ekini korur", () => {
  assert.equal(trimSecim("  “Silverwing Town.” "), "Silverwing Town");
  assert.equal(trimSecim("Sunny's"), "Sunny's");
});

test("terimDeseni yazım varyantlarını yakalar, sözcük içinde eşleşmez", () => {
  const d = terimDeseni("Ore Empire");
  assert.ok(d.test("the OreEmpire army"));
  assert.ok(d.test("Ore-Empire"));
  assert.ok(!terimDeseni("Rain").test("Training"));
});

test("cumleBul terimin geçtiği cümleyi döndürür", () => {
  const metin = "Kaan lit a lantern. The Silver Tower rang! Mira froze.";
  assert.equal(cumleBul(metin, "Silver Tower"), "The Silver Tower rang!");
  assert.equal(cumleBul(metin, "Yok"), null);
});

test("adayTerimler: kayıtlılar önce ve karşılığıyla; cümle başı sözcüğü aday değil", () => {
  const p = "The bell of the Silver Tower rang, and Mira looked at Kaan. Then silence.";
  const adaylar = adayTerimler(p, { "Silver Tower": "Gümüş Kule", Kaan: "Kaan" });
  assert.deepEqual(adaylar.slice(0, 2), [
    { source: "Silver Tower", target: "Gümüş Kule", kayitli: true },
    { source: "Kaan", target: "Kaan", kayitli: true },
  ]);
  const kaynaklar = adaylar.map((a) => a.source);
  assert.ok(kaynaklar.includes("Mira"));
  assert.ok(!kaynaklar.includes("The"));
  assert.ok(!kaynaklar.includes("Then"));
  assert.ok(!kaynaklar.includes("Tower"), "kayıtlı uzun terimin parçası ayrıca aday olmaz");
});

test("adayTerimler 'of the' bağlı adı tek aday sayar", () => {
  const adaylar = adayTerimler("He bowed to the Lord of the Nine Heavens.");
  assert.ok(adaylar.some((a) => a.source === "Lord of the Nine Heavens"));
});

test("sonucEtiketi hizalama/ihlal/hata bilgisini söyler", () => {
  assert.equal(sonucEtiketi({ durum: "hata", mesaj: "meşgul" }), "HATA: meşgul");
  assert.equal(
    sonucEtiketi({ durum: "tamam", hizali: false, ihlal: 2, kalinti: 0, model: "gemini-3.6-flash" }),
    "YENİLENDİ · hizalama tutmadı · 2 sözlük ihlali · gemini-3.6-flash"
  );
});

test("onbellekBayatMi: sonradan yeniden çevrilen bölüm bayattır, bilinmeyen değil", async () => {
  const { onbellekBayatMi } = await import("../../app/web/js/terim-yardimci.js");
  const indirildi = Date.parse("2026-09-16T10:00:00Z");
  assert.equal(onbellekBayatMi(indirildi, indirildi / 1000 - 5), false);
  assert.equal(onbellekBayatMi(indirildi, indirildi / 1000 + 1), false, "aynı istek payı");
  assert.equal(onbellekBayatMi(indirildi, indirildi / 1000 + 3600), true);
  assert.equal(onbellekBayatMi(NaN, indirildi / 1000 + 3600), false);
  assert.equal(onbellekBayatMi(indirildi, null), false);
});
