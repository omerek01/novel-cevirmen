// Sözlük yazma kuyruğu (sürüm 2) — saf mantık testleri. Çalıştırma:
//   node --test tests/js
// Varsayılan pytest koşusu bunu tests/test_js_birim.py üzerinden çağırır (Node
// yoksa atlar).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ESKI_KUYRUK_ANAHTARI,
  KUYRUK_ANAHTARI,
  anahtarla,
  kuyrukOlustur,
} from "../../app/web/js/sozluk-kuyruk.js";

function bellekDepo() {
  const m = new Map();
  return {
    m,
    bozuk: false,
    oku(k) {
      return m.has(k) ? m.get(k) : null;
    },
    yaz(k, v) {
      if (this.bozuk) throw Object.assign(new Error("dolu"), { name: "QuotaExceededError" });
      m.set(k, v);
    },
    sil(k) {
      m.delete(k);
    },
  };
}

// Her çağrıyı kaydeden, yanıtı testin elle vermesini bekleyen gönderici.
function elleGonderici() {
  const bekleyen = [];
  const gonder = (op) =>
    new Promise((coz, reddet) => bekleyen.push({ op: structuredClone(op), coz, reddet }));
  return { gonder, bekleyen };
}

const tamam = (govde = {}) => ({ durum: 200, govde });
const bekle = () => new Promise((r) => setTimeout(r, 0));

test("anahtarla yazım varyantlarını birleştirir, Türkçe yerel ayarı KULLANMAZ", () => {
  assert.equal(anahtarla("Ore Empire"), anahtarla("OreEmpire"));
  assert.equal(anahtarla("Ore-Empire"), "oreempire");
  assert.equal(anahtarla("Ice"), "ice"); // tr yerel ayarı "ıce" yapardı
});

test("YARIŞ: gönderim sürerken aynı terime yazılan yeni değer kuyrukta kalır ve gider", async () => {
  const depo = bellekDepo();
  const g = elleGonderici();
  const k = kuyrukOlustur({ depo, gonder: g.gonder });

  k.ekle("kitap", "Saint", { tur: "yaz", target: "Aziz" });
  const ucus = k.bosalt();
  await bekle();
  assert.equal(g.bekleyen.length, 1);
  assert.equal(g.bekleyen[0].op.target, "Aziz");

  // A uçuştayken B yazılıyor.
  k.ekle("kitap", "Saint", { tur: "yaz", target: "Ermiş" });
  g.bekleyen[0].coz(tamam());
  await bekle();
  await bekle();

  // A tamamlandı; B SİLİNMEDİ ve aynı turda gönderildi.
  assert.equal(g.bekleyen.length, 2);
  assert.equal(g.bekleyen[1].op.target, "Ermiş");
  g.bekleyen[1].coz(tamam());
  const sonuc = await ucus;
  assert.equal(sonuc.gonderilen, 2);
  assert.equal(k.islemler().length, 0);
});

test("gönderilmemiş işlemler birleşir: yazarken her değişiklik ayrı istek olmaz", () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: elleGonderici().gonder });
  k.ekle("kitap", "Saint", { tur: "yaz", target: "A" });
  k.ekle("kitap", "Saint", { tur: "yaz", target: "Az" });
  k.ekle("kitap", "Saint", { tur: "yaz", target: "Aziz" });
  const liste = k.islemler();
  assert.equal(liste.length, 1);
  assert.equal(liste[0].target, "Aziz");
});

test("koşul verilmeyen düzeltme az önce yazılan koşulu taşır; boş koşul temizler", () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: elleGonderici().gonder });
  k.ekle("kitap", "Great", { tur: "yaz", target: "Ulu", kosul: "rütbe" });
  k.ekle("kitap", "Great", { tur: "yaz", target: "Ulu!" });
  assert.equal(k.islemler()[0].kosul, "rütbe");
  k.ekle("kitap", "Great", { tur: "yaz", target: "Ulu", kosul: "" });
  assert.equal(k.islemler()[0].kosul, "");
});

test("köken örneği olmayan düzeltme az önce eklenen terimin örneğini taşır", () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: elleGonderici().gonder });
  const ornek = { bolum: 4, kaynak_cumle: "Great rank." };
  k.ekle("kitap", "Great", { tur: "yaz", target: "Ulu", ornek });
  k.ekle("kitap", "Great", { tur: "yaz", target: "Yüce" });
  assert.equal(k.islemler().length, 1);
  assert.deepEqual(k.islemler()[0].ornek, ornek);
  assert.equal(k.islemler()[0].target, "Yüce");
});

test("koşul hiç verilmediyse işlem koşul ALANI taşımaz (sunucu mevcut koşulu korur)", () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: elleGonderici().gonder });
  k.ekle("kitap", "Great", { tur: "yaz", target: "Ulu" });
  assert.equal("kosul" in k.islemler()[0], false);
});

test("DEPOLAMA HATASI yutulmaz: bellekte tutulur, olay yayılır, gönderim yine olur", async () => {
  const depo = bellekDepo();
  depo.bozuk = true;
  const olaylar = [];
  const k = kuyrukOlustur({ depo, gonder: async () => tamam(), olay: (ad, v) => olaylar.push([ad, v]) });

  const sonuc = k.ekle("kitap", "Kaan", { tur: "yaz", target: "Kaan" });
  assert.equal(sonuc.kalici, false);
  assert.equal(k.kalici(), false);
  assert.ok(olaylar.some(([ad, v]) => ad === "depolama" && v.kalici === false));
  assert.equal(k.islemler().length, 1, "işlem bellekte görünmeli");

  const bosaltma = await k.bosalt();
  assert.equal(bosaltma.gonderilen, 1);
  assert.equal(k.islemler().length, 0);
});

test("depolama düzelince kalıcılık geri gelir ve bellekteki işlemler yazılır", () => {
  const depo = bellekDepo();
  depo.bozuk = true;
  const k = kuyrukOlustur({ depo, gonder: elleGonderici().gonder });
  k.ekle("kitap", "Kaan", { tur: "yaz", target: "Kaan" });
  depo.bozuk = false;
  k.ekle("kitap", "Mira", { tur: "yaz", target: "Mira" });
  assert.equal(k.kalici(), true);
  const kayitli = JSON.parse(depo.m.get(KUYRUK_ANAHTARI));
  assert.deepEqual(kayitli.islemler.map((o) => o.source), ["Kaan", "Mira"]);
});

test("4xx işlemi SİLMEZ: hata durumunda saklanır, diğer terimler gönderilmeye devam eder", async () => {
  const k = kuyrukOlustur({
    depo: bellekDepo(),
    gonder: async (op) => (op.source === "Bozuk" ? { durum: 422, mesaj: "geçersiz" } : tamam()),
  });
  k.ekle("kitap", "Bozuk", { tur: "yaz", target: "x" });
  k.ekle("kitap", "Kaan", { tur: "yaz", target: "Kaan" });
  const sonuc = await k.bosalt();
  assert.equal(sonuc.hatali, 1);
  assert.equal(sonuc.gonderilen, 1);
  const kalan = k.islemler();
  assert.equal(kalan.length, 1);
  assert.equal(kalan[0].durum, "hata");
  assert.equal(kalan[0].hata.kod, 422);
  assert.equal(k.kaynakDurumu("kitap", "Bozuk"), "hata");
});

test("aynı terimin YENİ işlemi başarılı olunca eski hata işlemi düşer", async () => {
  let reddet = true;
  const k = kuyrukOlustur({
    depo: bellekDepo(),
    gonder: async () => (reddet ? { durum: 400, mesaj: "hayır" } : tamam()),
  });
  k.ekle("kitap", "Saint", { tur: "yaz", target: "X" });
  await k.bosalt();
  assert.equal(k.islemler()[0].durum, "hata");
  // Hata işlemi uçuşta değil ama durumu "hata": yeni yazım onu BİRLEŞTİRİR.
  reddet = false;
  k.ekle("kitap", "Saint", { tur: "yaz", target: "Aziz" });
  await k.bosalt();
  assert.equal(k.islemler().length, 0);
});

for (const kod of [429, 408, 500, 503]) {
  test(`${kod} yeniden denenir: işlem bekliyor kalır, tur durur`, async () => {
    const cagrilar = [];
    const k = kuyrukOlustur({
      depo: bellekDepo(),
      gonder: async (op) => {
        cagrilar.push(op.source);
        return { durum: kod, mesaj: "sonra" };
      },
    });
    k.ekle("kitap", "A", { tur: "yaz", target: "a" });
    k.ekle("kitap", "B", { tur: "yaz", target: "b" });
    const sonuc = await k.bosalt();
    assert.equal(sonuc.yenidenDenenecek, true);
    assert.deepEqual(cagrilar, ["A"], "ilk yeniden-denenir yanıtta tur durmalı");
    const [a] = k.islemler();
    assert.equal(a.durum, "bekliyor");
    assert.equal(a.deneme, 1);
    assert.equal(a.sonHata.kod, kod);
  });
}

test("ağ hatası (fırlatma) yeniden denenir", async () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: async () => { throw new Error("ağ"); } });
  k.ekle("kitap", "A", { tur: "yaz", target: "a" });
  const sonuc = await k.bosalt();
  assert.equal(sonuc.yenidenDenenecek, true);
  assert.equal(k.islemler()[0].durum, "bekliyor");
});

test("yenidenDene hatayı bekliyora çevirir, vazgec işlemi siler", async () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: async () => ({ durum: 400 }) });
  k.ekle("kitap", "A", { tur: "yaz", target: "a" });
  await k.bosalt();
  const [op] = k.islemler();
  k.yenidenDene(op.id);
  assert.equal(k.islemler()[0].durum, "bekliyor");
  k.vazgec(op.id);
  assert.equal(k.islemler().length, 0);
});

test("TEK UÇUŞ: eşzamanlı boşaltma aynı işlemi iki kez göndermez", async () => {
  let cagri = 0;
  const k = kuyrukOlustur({
    depo: bellekDepo(),
    gonder: async () => {
      cagri += 1;
      await bekle();
      return tamam();
    },
  });
  k.ekle("kitap", "A", { tur: "yaz", target: "a" });
  await Promise.all([k.bosalt(), k.bosalt(), k.bosalt()]);
  assert.equal(cagri, 1);
});

test("eski kuyruk biçimi göç eder ve eski anahtar silinir", () => {
  const depo = bellekDepo();
  depo.m.set(ESKI_KUYRUK_ANAHTARI, JSON.stringify({ kitap: { Kaan: "Kaan", Eski: null } }));
  const k = kuyrukOlustur({ depo, gonder: elleGonderici().gonder });
  assert.equal(k.eskiKuyruguTasi(), 2);
  const liste = k.islemler("kitap");
  assert.deepEqual(liste.map((o) => [o.source, o.tur]), [["Kaan", "yaz"], ["Eski", "sil"]]);
  assert.equal(depo.m.has(ESKI_KUYRUK_ANAHTARI), false);
});

test("göç depolamaya yazılamazsa eski anahtar SİLİNMEZ (tek kalıcı kopya odur)", () => {
  const depo = bellekDepo();
  depo.m.set(ESKI_KUYRUK_ANAHTARI, JSON.stringify({ kitap: { Kaan: "Kaan" } }));
  depo.bozuk = true;
  const k = kuyrukOlustur({ depo, gonder: elleGonderici().gonder });
  k.eskiKuyruguTasi();
  assert.equal(depo.m.has(ESKI_KUYRUK_ANAHTARI), true);
});

test("bindir: bekleyen yazma/silme ve koşul sunucu listesinin üstüne gelir", () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: elleGonderici().gonder });
  k.ekle("kitap", "OreEmpire", { tur: "yaz", target: "Ork İmparatorluğu", kosul: "ırk" });
  k.ekle("kitap", "Eski", { tur: "sil" });
  k.ekle("kitap", "Yeni", { tur: "yaz", target: "Yeni" });
  k.ekle("baska", "Kaan", { tur: "sil" });
  const { terms, kosullar } = k.bindir(
    "kitap",
    { "Ore Empire": "Maden İmparatorluğu", Eski: "x", Kaan: "Kaan" },
    { Eski: "silinecek" }
  );
  assert.deepEqual(terms, { "Ore Empire": "Ork İmparatorluğu", Kaan: "Kaan", Yeni: "Yeni" });
  assert.deepEqual(kosullar, { "Ore Empire": "ırk" });
});

test("bindir: reddedilen (hata) değer ekrandan kaybolmaz", async () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: async () => ({ durum: 400 }) });
  k.ekle("kitap", "Saint", { tur: "yaz", target: "Aziz" });
  await k.bosalt();
  assert.equal(k.bindir("kitap", {}).terms.Saint, "Aziz");
});

test("gonderildi olayı yanıt gövdesini taşır (liste sunucu hâliyle tazelenebilsin)", async () => {
  const olaylar = [];
  const k = kuyrukOlustur({
    depo: bellekDepo(),
    gonder: async () => tamam({ terms: { Kaan: "Kaan" } }),
    olay: (ad, v) => olaylar.push([ad, v]),
  });
  k.ekle("kitap", "Kaan", { tur: "yaz", target: "Kaan" });
  await k.bosalt();
  const [, veri] = olaylar.find(([ad]) => ad === "gonderildi");
  assert.deepEqual(veri.govde, { terms: { Kaan: "Kaan" } });
  assert.equal(veri.islem.source, "Kaan");
});

test("geri işlemi silinen kaydı karşılığı ve koşuluyla listeye bindirir", () => {
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: elleGonderici().gonder });
  k.ekle("kitap", "Great", { tur: "sil" });
  k.ekle("kitap", "Great", {
    tur: "geri",
    kayit: { source: "Great", target: "Ulu", kosul: "rütbe", origin: "auto", first_chapter: 4 },
  });
  const liste = k.islemler();
  assert.equal(liste.length, 1, "geri, bekleyen silmeyle birleşir");
  assert.equal(liste[0].tur, "geri");
  const { terms, kosullar } = k.bindir("kitap", {});
  assert.equal(terms.Great, "Ulu");
  assert.equal(kosullar.Great, "rütbe");
});

test("uçuştaki silmenin kimliği okunabilir (geri alma uçuştaki işleme dokunmasın)", async () => {
  const g = elleGonderici();
  const k = kuyrukOlustur({ depo: bellekDepo(), gonder: g.gonder });
  const { id } = k.ekle("kitap", "Great", { tur: "sil" });
  const ucus = k.bosalt();
  await bekle();
  assert.equal(k.ucustakiKimlik(), id);
  g.bekleyen[0].coz(tamam({ silinen: { source: "Great", target: "Ulu" } }));
  await ucus;
  assert.equal(k.ucustakiKimlik(), null);
});
