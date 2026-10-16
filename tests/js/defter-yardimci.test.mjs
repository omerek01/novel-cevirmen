// Defter ekranı saf yardımcıları. Çalıştırma: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  SEKMELER,
  SISTEM_SEKMESI,
  gorunenSekmeler,
  sistemAltMetni,
  sistemSatirlari,
  alanEtiketi,
  egoDugumleri,
  formdanKayit,
  hitapNotu,
  kayitFormu,
  sayacMetinleri,
  sekmeSatirlari,
  sinirMetni,
  tr,
} from "../../app/web/js/defter-yardimci.js";

const VERI = {
  sinir: 983,
  kisiler: [
    { kimlik: "a", ad: "Sunny", tr: "Sunny", takma: ["Sunless", "Mongrel"], bolum_sayisi: 881 },
    { kimlik: "b", ad: "Nephis", tr: "Nephis", takma: ["Changing Star"], bolum_sayisi: 366 },
  ],
  yaratiklar: [{ ad: "Mirror Beast", tr: "Ayna Mahluğu", alanlar: { rutbe: "Ascended" } }],
  anilar: [{ ad: "Azure Blade", tr: null, alanlar: {}, efsun_sayisi: 2 }],
  nitelikler: [],
  yankilar: [],
  gruplar: [],
};

test("sekmeSatirlari aramada takma adları ve karşılığı da tarar", () => {
  assert.deepEqual(sekmeSatirlari(VERI, "kisiler", "").map((k) => k.ad), ["Sunny", "Nephis"]);
  assert.deepEqual(sekmeSatirlari(VERI, "kisiler", "changing").map((k) => k.ad), ["Nephis"]);
  assert.deepEqual(sekmeSatirlari(VERI, "kisiler", "MONGREL").map((k) => k.ad), ["Sunny"]);
  assert.deepEqual(sekmeSatirlari(VERI, "yaratiklar", "ayna").map((k) => k.ad), ["Mirror Beast"]);
  assert.deepEqual(sekmeSatirlari(VERI, "yok", ""), []);
});

test("SEKMELER her sekmeye bir veri anahtarı ve eklenebilir tür verir", () => {
  const anahtarlar = SEKMELER.map((s) => s.anahtar);
  assert.deepEqual(anahtarlar, ["kisiler", "yaratiklar", "anilar", "nitelikler", "yankilar", "gruplar"]);
  assert.equal(SEKMELER.find((s) => s.anahtar === "anilar").tur, "ani");
});

test("alanEtiketi bilinen rün alanlarını Türkçeler, bilinmeyeni aynen bırakır", () => {
  assert.equal(alanEtiketi("rutbesi"), "Rütbe");
  assert.equal(alanEtiketi("Shadow Cores"), "Gölge çekirdeği");
  assert.equal(alanEtiketi("Bilinmez Alan"), "Bilinmez Alan");
});

test("tr önce sözlük karşılığını, yoksa bilinen eşya türünü, yoksa değeri verir", () => {
  assert.equal(tr("Awakened", { Awakened: "Uyanmış" }), "Uyanmış");
  assert.equal(tr("Weapon", {}), "Silah");
  assert.equal(tr("Bitter", {}), "Bitter");
  assert.equal(tr("", {}), "");
});

test("hitapNotu kararlı, karışık ve elle kararı ayrı söyler", () => {
  assert.equal(hitapNotu({ n: 15, oran: 1, bicim: "sen", kararli: true, son_bolum: 980 }),
    "Son 15 kaydın 15’i “sen” · son bölüm 980");
  assert.equal(hitapNotu({ n: 7, oran: 0.57, bicim: "sen", kararli: false, son_bolum: 900 }),
    "7 kaydın 4’ü “sen” · karışık; seçersen sonraki çeviriler buna uyar");
  assert.equal(hitapNotu({ n: 0, oran: 1, bicim: "siz", kararli: true, elle: true }), "Senin kararın: “siz”");
});

test("sinirMetni okuma konumunu ve tüm kitabı ayırır", () => {
  assert.equal(sinirMetni(983), "Bölüm 983’e kadar");
  assert.equal(sinirMetni(30), "Bölüm 30’a kadar");
  assert.equal(sinirMetni(null), "Tüm kitap");
});

test("egoDugumleri en güçlü bağları sınırlar ve çember üstüne dizer", () => {
  const baglar = Array.from({ length: 9 }, (_, i) => ({
    diger_kimlik: `k${i}`, diger_ad: `Kişi ${i}`, etiket: "yoldaşı", destek: i, durum: "onaylandi", guven: 1,
  }));
  baglar.push({ diger_kimlik: "k0", diger_ad: "Kişi 0", etiket: "düşmanı", destek: 50, durum: "aday", guven: 0.5 });
  const d = egoDugumleri(baglar, 6);
  assert.equal(d.length, 6);
  assert.equal(d[0].ad, "Kişi 0"); // en yüksek destek; aynı kişinin iki bağı tek düğüm
  assert.equal(d[0].aday, false); // onaylı bağı olan düğüm aday çizilmez
  assert.ok(d.every((x) => x.x >= 0 && x.x <= 340 && x.y >= 0 && x.y <= 200));
});

test("kayitFormu ve formdanKayit türün alanlarını kurar ve boşları atar", () => {
  const alanlar = kayitFormu("ani").map((a) => a.ad);
  assert.deepEqual(alanlar, ["ad", "rutbe", "kademe", "tur", "ilk_bolum"]);
  const k = formdanKayit("ani", { ad: " Endless Spring ", rutbe: "", kademe: "I", tur: "Tool", ilk_bolum: "18" }, "Sunny");
  assert.deepEqual(k, { tur: "ani", sahip: "Sunny", ad: "Endless Spring", ilk_bolum: 18, alanlar: { kademe: "I", tur: "Tool" } });
  const alan = formdanKayit("alan", { ad: "rutbesi", deger: "Master", ilk_bolum: "" }, "Sunny");
  assert.deepEqual(alan, { tur: "alan", sahip: "Sunny", ad: "rutbesi", deger: "Master", alanlar: {} });
  assert.throws(() => formdanKayit("ani", { ad: "  " }, "Sunny"), /Ad boş/);
  assert.throws(() => formdanKayit("ani", { ad: "X", ilk_bolum: "-3" }, "Sunny"), /Bölüm/);
});

test("Türkçe sayı ekleri okunuşun son sözcüğüne uyar", async () => {
  const { yonelmeEki, iyelikEki } = await import("../../app/web/js/defter-yardimci.js");
  assert.deepEqual([2, 6, 9, 10, 20, 40, 70, 100, 1000].map(yonelmeEki),
    ["2’ye", "6’ya", "9’a", "10’a", "20’ye", "40’a", "70’e", "100’e", "1000’e"]);
  assert.deepEqual([1, 2, 3, 6, 7, 9, 20, 40, 100, 0].map(iyelikEki),
    ["1’i", "2’si", "3’ü", "6’sı", "7’si", "9’u", "20’si", "40’ı", "100’ü", "0’ı"]);
});

test("runSatirlari bilinen alanları sıraya dizer, yetenekleri tek satırda toplar", async () => {
  const { runSatirlari } = await import("../../app/web/js/defter-yardimci.js");
  const run = [
    { ad: "Shadow Cores", deger: "4/7" }, { ad: "yetenegi", deger: "Shadow Step" },
    { ad: "rutbesi", deger: "Ascended" }, { ad: "yetenegi", deger: "Shadow Dance" },
    { ad: "gercek_adi", deger: "Lost from Light" },
  ];
  const s = runSatirlari(run);
  assert.deepEqual(s.map((x) => x.ad), ["gercek_adi", "rutbesi", "yetenegi", "Shadow Cores"]);
  assert.deepEqual(s[2].kayitlar.map((k) => k.deger), ["Shadow Step", "Shadow Dance"]);
  assert.equal(s[0].kayitlar.length, 1);
});

test("kademeMetni Roma rakamını sıra sayısı yapar, bilinmeyeni gizler", async () => {
  const { kademeMetni } = await import("../../app/web/js/defter-yardimci.js");
  assert.equal(kademeMetni("V"), "V. kademe");
  assert.equal(kademeMetni("unknown"), "");
  assert.equal(kademeMetni("—"), "");
  assert.equal(kademeMetni(""), "");
});

test("sayacMetinleri anı ve gölge sayaçlarını Türkçe etiketle verir", () => {
  assert.deepEqual(sayacMetinleri({ "Shadow Fragments": "146/200", rutbe: "Ascended", "Death Charge": "0/1000" }),
    ["Gölge parçası 146/200", "Ölüm yükü 0/1000"]);
  assert.deepEqual(sayacMetinleri({}), []);
  assert.deepEqual(sayacMetinleri(undefined), []);
});

test("gorunenSekmeler sistem sekmesini yalnız sunucu isterse ekler", () => {
  assert.equal(gorunenSekmeler(null), SEKMELER);
  assert.equal(gorunenSekmeler({ sistem_sekmesi: false }), SEKMELER);
  assert.deepEqual(gorunenSekmeler({ sistem_sekmesi: true }).at(-1), SISTEM_SEKMESI);
  assert.equal(SISTEM_SEKMESI.tur, null); // elle eklenecek kayıt türü yok
});

test("sistemSatirlari en yeni bölümü üste alır, bölüm içi sırayı korur, üç alanda arar", () => {
  const m = [
    { bolum: 3, metin: "[Görev kabul edildi.]", en: "[Quest accepted.]", anahtarlar: [] },
    { bolum: 3, metin: "Ödül: 200 Altın", en: "Reward: 200 Gold", anahtarlar: ["Reward"] },
    { bolum: 9, metin: "[Seviye atladın!]", en: "[Level up!]", anahtarlar: [] },
  ];
  assert.deepEqual(sistemSatirlari(m, "").map((x) => x.en), ["[Level up!]", "[Quest accepted.]", "Reward: 200 Gold"]);
  assert.deepEqual(sistemSatirlari(m, "GÖREV").map((x) => x.bolum), [3]);
  assert.deepEqual(sistemSatirlari(m, "level").map((x) => x.bolum), [9]);
  assert.deepEqual(sistemSatirlari(m, "reward").map((x) => x.metin), ["Ödül: 200 Altın"]);
  assert.deepEqual(sistemSatirlari(null, "x"), []);
});

test("sistemAltMetni bölüm, anahtarlar ve hizasız çeviri notu", () => {
  assert.equal(sistemAltMetni({ bolum: 12, anahtarlar: ["Cooldown", "Mana"], turkce: false }),
    "Bölüm 12 · Cooldown, Mana · İngilizce");
  assert.equal(sistemAltMetni({ bolum: 4, anahtarlar: [], turkce: true }), "Bölüm 4");
});
