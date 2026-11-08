import { test } from "node:test";
import assert from "node:assert/strict";
import { gecerliSinirlar, obekBoyuSinirla, parcalar, sabitObekler } from "../../app/web/js/obek-yardimci.js";

const P = "Kaan fenerini yaktı ve dar geçidin sonundaki kapıya baktı.";
const S = [19, 34, 58];  // "Kaan fenerini yaktı" | " ve dar geçidin" | " sonundaki kapıya baktı."

test("öbekler sırayla, aradaki boşluk öbek dışında", () => {
  const p = parcalar(P, S, "");
  assert.deepEqual(p.map((x) => [x.t, x.obek]), [
    ["Kaan fenerini yaktı", 0], [" ", null], ["ve dar geçidin", 1], [" ", null],
    ["sonundaki kapıya baktı.", 2]]);
  assert.equal(p.map((x) => x.t).join(""), P);  // metin aynen korunur
});

test("öbek sınırını aşan eşleşme iki parçaya bölünür, aynı kimliği taşır", () => {
  const p = parcalar(P, S, "yaktı ve");
  const esler = p.filter((x) => x.eslesme !== null);
  assert.deepEqual(esler.map((x) => [x.t, x.obek, x.eslesme]), [
    ["yaktı", 0, 0], [" ", null, 0], ["ve", 1, 0]]);
});

test("ı ile i aynı sayılır (sunucudaki aramayla aynı kural)", () => {
  const p = parcalar(P, S, "BAKTI");
  assert.deepEqual(p.filter((x) => x.eslesme !== null).map((x) => x.t), ["baktı"]);
});

test("uyuşmayan sınırlar öbeksiz düz metne döner", () => {
  assert.equal(gecerliSinirlar(P, [19, 10, 58]), false);  // artmıyor
  assert.equal(gecerliSinirlar(P, [19, 34]), false);  // metnin sonuna varmıyor
  assert.equal(gecerliSinirlar(P, [19, 999]), false);
  assert.equal(gecerliSinirlar(P, null), false);
  assert.deepEqual(parcalar(P, [5, 999], ""), [{ t: P, obek: null, eslesme: null }]);
});

function bol(metin, boy) {
  let bas = 0;
  return sabitObekler(metin, boy).map((s) => { const t = metin.slice(bas, s).trim(); bas = s; return t; });
}

test("sabit boylu öbek: boy kadar sözcük, cümle sonu erken bitirir", () => {
  assert.deepEqual(bol("Kaan fenerini yaktı ve dar geçidin sonundaki kapıya baktı.", 3),
    ["Kaan fenerini yaktı", "ve dar geçidin", "sonundaki kapıya baktı."]);
  assert.deepEqual(bol("Mira durdu. Sonra geri dönüp kapıya baktı.", 2),
    ["Mira durdu.", "Sonra geri", "dönüp kapıya", "baktı."]);
  assert.deepEqual(bol("\"Leydi Nephis... rüzgar...\"", 4), ["\"Leydi Nephis...", "rüzgar...\""]);
  assert.deepEqual(sabitObekler("", 3), []);
});

test("öbek boyu 2-6 aralığında, geçersiz değer 3", () => {
  assert.equal(obekBoyuSinirla(1), 2);
  assert.equal(obekBoyuSinirla(9), 6);
  assert.equal(obekBoyuSinirla(undefined), 3);
});

test("sabit öbekler parçalara dönünce metin aynen korunur", () => {
  const m = "Gümüş Kule'nin çanı uzaktan üç kez çaldı ve ikisi de olduğu yerde durdu.";
  for (const boy of [2, 3, 4, 5, 6]) {
    assert.equal(parcalar(m, sabitObekler(m, boy), "").map((x) => x.t).join(""), m);
  }
});
