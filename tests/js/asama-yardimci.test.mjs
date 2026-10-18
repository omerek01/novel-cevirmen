// Çeviri aşaması düğmelerinin saf yardımcıları. Çalıştırma: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";

import { asamaGovdesi, asamaSureMetni, olcumOzeti } from "../../app/web/js/asama-yardimci.js";

const OLCUM = {
  bolum: 40, toplam_ort_sn: 125.3, ceviri_ort_sn: 41.1,
  asamalar: {
    cilalama: { bolum_orani: 0.92, ort_sn: 43.0 },
    terim_alani: { bolum_orani: 0, ort_sn: 0 },
  },
};

test("çalışan aşama bölüm başına süresini ve kaç bölümde çalıştığını söyler", () => {
  assert.equal(asamaSureMetni("cilalama", OLCUM), "Bölüm başına +43 sn · son 40 bölümün 37'sinde çalıştı");
});

test("çalışmayan aşama bunu açıkça söyler", () => {
  assert.equal(asamaSureMetni("terim_alani", OLCUM), "Son 40 bölümde hiç çalışmadı");
});

test("ölçüm yoksa ya da aşama ölçümde yoksa uydurma süre yazılmaz", () => {
  assert.equal(asamaSureMetni("cilalama", { bolum: 0, asamalar: {} }), "Henüz ölçüm yok");
  assert.equal(asamaSureMetni("cilalama", null), "Henüz ölçüm yok");
  assert.equal(asamaSureMetni("yeni", OLCUM), "Henüz ölçüm yok");
});

test("özet toplam süreyi ve çevirinin kendi payını verir", () => {
  assert.equal(olcumOzeti(OLCUM),
    "Son 40 bölüm: bölüm başına ortalama 125 sn model süresi, bunun 41 sn'si çevirinin kendisi. " +
    "Seçim yalnız yeni çevrilen bölümlerde geçerli.");
  assert.equal(olcumOzeti({ bolum: 0 }), "Seçim yalnız yeni çevrilen bölümlerde geçerli.");
});

test("gövde açık/kapalıyı boolean taşır", () => {
  assert.deepEqual(asamaGovdesi("kalite", "0"), { ad: "kalite", acik: false });
  assert.deepEqual(asamaGovdesi("kalite", "1"), { ad: "kalite", acik: true });
});
