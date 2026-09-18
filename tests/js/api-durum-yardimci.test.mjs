// API durum paneli saf yardımcıları. Çalıştırma: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  YENILEME_MS,
  baglantiDurumu,
  bolumEtiketi,
  gecisNedeni,
  isaret,
  kalanSure,
  kisaModel,
  saat,
  sayfalariBirlestir,
  tarihSaat,
} from "../../app/web/js/api-durum-yardimci.js";

test("saat ve tarih TSİ gösterilir (UTC+3)", () => {
  const ts = Date.UTC(2026, 8, 18, 12, 8, 25) / 1000; // 12:08:25 UTC
  assert.equal(saat(ts), "15:08:25");
  assert.equal(tarihSaat(ts), "18.09 15:08");
  assert.equal(saat(null), "-");
});

test("kalan süre okunur biçimde, geçmişte boş", () => {
  assert.equal(kalanSure(1045, 1000), "45 sn");
  assert.equal(kalanSure(1000 + 4 * 60, 1000), "4 dk");
  assert.equal(kalanSure(1000 + 3 * 3600 + 12 * 60, 1000), "3 sa 12 dk");
  assert.equal(kalanSure(1000 + 2 * 3600, 1000), "2 sa");
  assert.equal(kalanSure(900, 1000), "");
});

test("model kısaltılır, her tonun metin dışı bir işareti var", () => {
  assert.equal(kisaModel("gemini-3.6-flash"), "3.6-flash");
  for (const ton of ["iyi", "bekle", "uyari", "hata", "notr"]) {
    assert.ok(isaret(ton));
  }
  assert.notEqual(isaret("iyi"), isaret("hata"));
});

test("bağlantı: ilk yükleme, bağlı, bağlantı kopunca eski veri BAYAT", () => {
  const simdi = 1_000_000;
  assert.equal(baglantiDurumu({ sonBasari: 0, sonHata: 0, simdiMs: simdi }).bayat, false);
  assert.match(baglantiDurumu({ sonBasari: 0, sonHata: simdi, simdiMs: simdi }).metin,
    /ulaşılamadı/);
  const bagli = baglantiDurumu({ sonBasari: simdi - 1000, sonHata: null, simdiMs: simdi });
  assert.equal(bagli.bayat, false);
  assert.match(bagli.metin, /^Bağlı/);
  const kopuk = baglantiDurumu({ sonBasari: simdi - 20000, sonHata: simdi, simdiMs: simdi });
  assert.equal(kopuk.bayat, true);
  assert.match(kopuk.metin, /bayat/);
  // Hata yok ama sekme uyudu: iki aralıktan eski veri de bayattır.
  const uyudu = baglantiDurumu({
    sonBasari: simdi - 3 * YENILEME_MS, sonHata: null, simdiMs: simdi,
  });
  assert.equal(uyudu.bayat, true);
});

test("bölüm etiketi başlıktan, yoksa URL'den", () => {
  assert.equal(
    bolumEtiketi({ bolum: { kitap_adi: "Shadow Slave", no: 595 } }),
    "Shadow Slave · 595. bölüm",
  );
  assert.equal(
    bolumEtiketi({ url: "https://s.com/novel/shadow-slave/chapter-595/" }),
    "shadow-slave/chapter-595",
  );
  assert.equal(bolumEtiketi({}), "");
});

test("geçiş nedeni özetten ayrılır", () => {
  assert.equal(
    gecisNedeni({ ozet: "3.6-flash → 3.5-flash: 3.6-flash: 3 anahtarda günlük kota" }),
    "3.6-flash: 3 anahtarda günlük kota",
  );
  assert.equal(gecisNedeni({ ozet: "3.6-flash → 3.5-flash" }), "");
});

test("otomatik yenileme 'Daha eski' ile yüklenen sayfaları KORUR", () => {
  const mevcut = [{ id: 9 }, { id: 8 }, { id: 5 }, { id: 4 }];
  const yeni = [{ id: 11 }, { id: 9 }, { id: 8 }];
  assert.deepEqual(sayfalariBirlestir(yeni, mevcut).map((o) => o.id), [11, 9, 8, 5, 4]);
  assert.deepEqual(sayfalariBirlestir(yeni, []).map((o) => o.id), [11, 9, 8]);
  assert.deepEqual(sayfalariBirlestir([], mevcut).map((o) => o.id), [9, 8, 5, 4]);
});
