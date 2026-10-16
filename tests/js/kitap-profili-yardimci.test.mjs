// Kitap profili kartının saf yardımcıları. Çalıştırma: node --test "tests/js/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  alanDurumu,
  bekleyenSayisi,
  cikarimMetni,
  degerMetni,
  duzeltmeMetni,
  gosterilenDeger,
  kanitlar,
  metindenDeger,
  siraliAlanlar,
} from "../../app/web/js/kitap-profili-yardimci.js";

const model = (deger, durum = "aday", kanit = []) => ({ origin: "model", durum, deger, kanit });

test("alanDurumu öncelik sırası: kod > elle > onaylı > reddedildi > öneri > boş", () => {
  assert.equal(alanDurumu({ kod: true, elle: {}, model: model("x") }).anahtar, "kod");
  assert.equal(alanDurumu({ kod: false, elle: { deger: "y" }, model: model("x") }).anahtar, "elle");
  assert.equal(alanDurumu({ model: model("x", "onayli") }).anahtar, "onayli");
  assert.equal(alanDurumu({ model: model("x", "reddedildi") }).anahtar, "reddedildi");
  assert.equal(alanDurumu({ model: model("x") }).anahtar, "aday");
  assert.equal(alanDurumu({ model: null, elle: null }).anahtar, "bos");
});

test("gosterilenDeger etkin değeri, yoksa önerilen değeri verir", () => {
  assert.equal(gosterilenDeger({ etkin: "Shi Feng", model: model("Başka") }), "Shi Feng");
  assert.equal(gosterilenDeger({ etkin: null, model: model("Shi Feng") }), "Shi Feng");
  assert.equal(gosterilenDeger({ etkin: null, elle: null, model: null }), null);
});

test("degerMetni tür adını, listeyi ve dizileri okunur yazar", () => {
  assert.equal(degerMetni("kitap_turu", "kultivasyon"), "Kültivasyon");
  assert.equal(degerMetni("sistem_sesi", ["System", "Quest"]), "System, Quest");
  assert.equal(degerMetni("diziler", { esya_kalitesi: ["Common", "Rare", "Epic"], tier: ["Tier 1", "Tier 2"] }),
    "esya kalitesi: Common → Rare → Epic\ntier: Tier 1 → Tier 2");
  assert.equal(degerMetni("ana_karakter", null), "");
});

test("düzeltme metni ile değer gidiş-dönüş aynı kalır", () => {
  const diziler = { rutbe: ["Bronze", "Silver", "Gold"] };
  assert.deepEqual(metindenDeger("diziler", duzeltmeMetni("diziler", diziler)), diziler);
  assert.deepEqual(metindenDeger("sistem_anahtarlari", " Cooldown,  Price ,"), ["Cooldown", "Price"]);
  assert.equal(metindenDeger("ana_karakter", "  Shi Feng "), "Shi Feng");
  assert.equal(metindenDeger("kitap_turu", "duz"), "duz");
});

test("metindenDeger hatalı girdiyi yerinde açıklar", () => {
  assert.throws(() => metindenDeger("ana_karakter", "  "), /Boş/);
  assert.throws(() => metindenDeger("kitap_turu", "romantik"), /Tür/);
  assert.throws(() => metindenDeger("diziler", "Bronze, Silver"), /ad: basamak/);
  assert.throws(() => metindenDeger("diziler", "rutbe: Tek"), /en az iki/);
  assert.throws(() => metindenDeger("yok", "x"), /Bilinmeyen/);
});

test("kanitlar en çok iki fiş ve geçiş sayısı verir", () => {
  const a = { model: model("x", "aday", [{ bolum: 3, alinti: "a", sayi: 118 }, { bolum: 4, alinti: "b" },
    { bolum: 5, alinti: "c" }]) };
  assert.deepEqual(kanitlar(a).map((k) => [k.bolum, k.ek]), [[3, "118 geçiş"], [4, ""]]);
  assert.deepEqual(kanitlar({ model: null }), []);
});

test("kanitlar aynı cümleyi tek fişte birleştirir", () => {
  const a = { model: model([], "aday", [{ bolum: 7, alinti: "aynı", deger: "Skills", sayi: 10 },
    { bolum: 7, alinti: "aynı", deger: "Spells", sayi: 23 }, { bolum: 8, alinti: "başka", deger: "Class", sayi: 4 }]) };
  assert.deepEqual(kanitlar(a), [{ bolum: 7, alinti: "aynı", ek: "Skills 10 geçiş · Spells 23 geçiş" },
    { bolum: 8, alinti: "başka", ek: "4 geçiş" }]);
});

test("siraliAlanlar sabit sıra, bekleyenSayisi yalnız önerileri sayar", () => {
  const veri = { alanlar: [{ alan: "diziler", model: model({}) }, { alan: "kitap_turu", model: model("sistem", "onayli") },
    { alan: "ana_karakter", model: model("X") }, { alan: "sistem_sesi", kod: true, model: model(["S"]) }] };
  assert.deepEqual(siraliAlanlar(veri).map((a) => a.alan), ["kitap_turu", "ana_karakter", "sistem_sesi", "diziler"]);
  assert.equal(bekleyenSayisi(veri), 2);
  assert.equal(bekleyenSayisi(null), 0);
});

test("cikarimMetni çalışma, hata ve özet durumlarını söyler", () => {
  assert.match(cikarimMetni({ calisiyor: true }), /okunuyor/);
  assert.equal(cikarimMetni({ son: null }), "Henüz öneri çıkarılmadı.");
  assert.match(cikarimMetni({ son: { hata: "kota" } }), /başarısız: kota/);
  assert.equal(cikarimMetni({ son: { bolumler: [1710, 1711, 1719], profil: ["a", "b"], on_tarama: { yazilan: ["x"] } } }),
    "3 bölümden önerildi (bölüm 1710–1719) · 2 alan · sözlüğe 1 aday");
});
