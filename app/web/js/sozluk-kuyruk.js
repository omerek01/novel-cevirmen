/* Sözlük yazma KUYRUĞU (sürüm 2) — saf mantık, tarayıcıdan bağımsız.

   Her ekleme/düzeltme/silme ÖNCE kuyruğa yazılır, sonra sunucuya gönderilir:
   sunucu kapalıyken kayıt cihazda durur, bağlantı gelince kendiliğinden gider.
   Depolama ve gönderim DIŞARIDAN verilir (`kuyrukOlustur`), böylece bu dosya
   Node'da test edilir (tests/js/sozluk-kuyruk.test.mjs).

   Sürüm 1'in iki arızası (2026-09-16 araştırması, ikisi de koddan doğrulandı):

   * YARIŞ: gönderim bitince kayıt terim ANAHTARIYLA siliniyordu. İstek sürerken
     aynı terime yeni bir değer yazılırsa, sunucuya hiç gitmemiş yeni değer de
     siliniyordu. Artık her işlemin KİMLİĞİ var ve yalnız gönderilen kimlik düşer.
   * SESSİZ KAYIP: localStorage yazma hatası yutuluyordu (kayıt "kuyrukta" görünüp
     hiçbir yere yazılmıyordu) ve 500 dışındaki HER yanıtta (429 dahil) işlem
     düşürülüyordu. Artık depolama hatası görünür bir durumdur, 4xx işlemi SİLMEZ
     (kullanıcı görüp karar verir), 429/5xx/ağ hatası yeniden denenir.

   Kural: kaydedilmemiş bir değer hiçbir zaman kaydedilmiş gibi görünmez. */

export const KUYRUK_ANAHTARI = "novellink:glossQueue2";
export const ESKI_KUYRUK_ANAHTARI = "novellink:glossQueue";

// Beklemeyle düzelebilecek yanıtlar: işlem KORUNUR ve sonra yeniden gönderilir.
// Kalan 4xx isteğin kendisinin bozuk olduğunu söyler; tekrar denemek düzeltmez
// ama işlemi SESSİZCE silmek de kullanıcının yazdığını yok ederdi.
const YENIDEN_DENENIR = new Set([408, 425, 429]);

/* Terimi kuyruk içi karşılaştırma anahtarına indirger. Sunucudaki `fold_term`
   ile aynı ayırıcılar: "Ore Empire" ile "OreEmpire" aynı sözlük satırına yazar,
   kuyrukta da aynı terimdir. Yerel ayarsız küçük harf BİLİNÇLİ: Türkçe yerel
   ayarı "I"yı "ı" yapar ve İngilizce terimlerin anahtarı sunucununkinden ayrışır. */
export function anahtarla(source) {
  return (source || "").trim().replace(/[\s\-_'’.·]+/g, "").toLowerCase();
}

function bosDurum() {
  return { surum: 2, sayac: 0, islemler: [] };
}

function gecerliDurum(d) {
  return d && d.surum === 2 && Array.isArray(d.islemler) && Number.isFinite(d.sayac);
}

export function kuyrukOlustur({ depo, gonder, simdi = () => Date.now(), olay = () => {} }) {
  let bellek = null; // son bilinen durum (depolama okunamaz/yazılamazsa tek kaynak)
  let kalici = true; // son yazım depolamaya ulaştı mı
  let ucustakiId = null;
  let ucusVaadi = null;

  function oku() {
    if (!kalici && bellek) return structuredClone(bellek);
    try {
      const ham = depo.oku(KUYRUK_ANAHTARI);
      const d = ham ? JSON.parse(ham) : null;
      if (gecerliDurum(d)) {
        bellek = d;
        return structuredClone(d);
      }
    } catch {
      // Okunamayan depolama: bellekteki kopya varsa o geçerlidir.
    }
    return structuredClone(bellek || bosDurum());
  }

  function yaz(d) {
    bellek = structuredClone(d);
    try {
      depo.yaz(KUYRUK_ANAHTARI, JSON.stringify(d));
      if (!kalici) {
        kalici = true;
        olay("depolama", { kalici: true });
      }
    } catch (hata) {
      // YUTULMAZ: işlem bellekte yaşar ama uygulama kapanırsa kaybolur ve
      // kullanıcı bunu BİLMELİ. Gönderim yine denenir.
      const ilk = kalici;
      kalici = false;
      if (ilk) olay("depolama", { kalici: false, hata: String(hata && hata.name || hata) });
    }
  }

  function eskiKuyruguTasi() {
    let eski;
    try {
      eski = JSON.parse(depo.oku(ESKI_KUYRUK_ANAHTARI) || "null");
    } catch {
      return 0;
    }
    if (!eski || typeof eski !== "object") return 0;
    const d = oku();
    let adet = 0;
    for (const [slug, terimler] of Object.entries(eski)) {
      for (const [source, target] of Object.entries(terimler || {})) {
        d.sayac += 1;
        d.islemler.push(
          target === null
            ? { id: d.sayac, slug, source, tur: "sil", zaman: simdi(), durum: "bekliyor", deneme: 0 }
            : { id: d.sayac, slug, source, tur: "yaz", target, zaman: simdi(), durum: "bekliyor", deneme: 0 }
        );
        adet += 1;
      }
    }
    yaz(d);
    // Eski anahtar YALNIZ yeni biçim depolamaya ulaştıysa silinir: ulaşmadıysa
    // eski kuyruk tek kalıcı kopyadır.
    if (kalici) {
      try {
        depo.sil(ESKI_KUYRUK_ANAHTARI);
      } catch {}
    }
    return adet;
  }

  /* Değişikliği kuyruğa al. `alanlar`:
       { tur: "yaz", target, kosul }  — kosul undefined = GÖNDERİLMEZ (sunucu
                                        mevcut koşulu korur), "" = temizle
       { tur: "sil" }
       { tur: "geri", kayit }         — silinen kaydı TAM hâliyle geri yaz
                                        (koşul + köken; sunucunun döndürdüğü satır)
     Aynı terimin henüz gönderilmemiş işlemi YENİSİYLE birleşir (yazarken her
     tuşa ayrı istek gitmesin); UÇUŞTAKİ işleme DOKUNULMAZ — yarışın kaynağı buydu. */
  function ekle(slug, source, alanlar) {
    const d = oku();
    const anahtar = anahtarla(source);
    let kosul = alanlar.kosul;
    let ornek = alanlar.ornek;
    const kalanlar = [];
    for (const op of d.islemler) {
      const ayniTerim = op.slug === slug && anahtarla(op.source) === anahtar;
      if (!ayniTerim || op.id === ucustakiId) {
        kalanlar.push(op);
        continue;
      }
      // Birleşen eski işlemin koşulu, yeni işlem koşul VERMİYORSA taşınır:
      // karşılığı düzelten kullanıcı az önce yazdığı koşulu kaybetmemeli.
      if (alanlar.tur === "yaz" && kosul === undefined && op.tur === "yaz" && op.kosul !== undefined) {
        kosul = op.kosul;
      }
      // Köken örneği de taşınır: okurken eklenip hemen düzeltilen terim, eklendiği
      // bölümü ve cümleyi kaybetmemeli.
      if (alanlar.tur === "yaz" && ornek === undefined && op.tur === "yaz" && op.ornek) {
        ornek = op.ornek;
      }
    }
    d.sayac += 1;
    const yeni = { id: d.sayac, slug, source, tur: alanlar.tur, zaman: simdi(), durum: "bekliyor", deneme: 0 };
    if (alanlar.tur === "yaz") {
      yeni.target = alanlar.target;
      if (kosul !== undefined) yeni.kosul = kosul;
      if (ornek) yeni.ornek = ornek;
    } else if (alanlar.tur === "geri") {
      yeni.kayit = alanlar.kayit;
    }
    kalanlar.push(yeni);
    d.islemler = kalanlar;
    yaz(d);
    olay("eklendi", { islem: yeni, kalici });
    return { id: yeni.id, kalici };
  }

  function islemler(slug) {
    const liste = oku().islemler;
    return slug === undefined ? liste : liste.filter((op) => op.slug === slug);
  }

  /* Bir terimin EN SON işleminin durumu: "bekliyor" | "hata" | null. */
  function kaynakDurumu(slug, source) {
    const anahtar = anahtarla(source);
    let son = null;
    for (const op of oku().islemler) {
      if (op.slug === slug && anahtarla(op.source) === anahtar) son = op;
    }
    return son ? son.durum : null;
  }

  function islemDurumu(id) {
    const op = oku().islemler.find((o) => o.id === id);
    return op ? op.durum : "gonderildi";
  }

  /* Sunucu listesine bekleyen işlemleri bindir: ekranda daima SON hâl görünür.
     "hata" durumundaki işlem de bindirilir — kullanıcının yazdığı değer, sunucu
     reddetti diye ekrandan sessizce kaybolmamalı; satır hata rozetiyle görünür. */
  function bindir(slug, terms, kosullar = {}) {
    const t = { ...terms };
    const k = { ...kosullar };
    for (const op of islemler(slug)) {
      const kayitli = Object.keys(t).find((s) => anahtarla(s) === anahtarla(op.source));
      const ad = kayitli === undefined ? op.source : kayitli;
      if (op.tur === "sil") {
        delete t[ad];
        delete k[ad];
      } else if (op.tur === "geri") {
        t[ad] = op.kayit.target || op.kayit.source;
        if (op.kayit.kosul) k[ad] = op.kayit.kosul;
        else delete k[ad];
      } else {
        t[ad] = op.target;
        if (op.kosul !== undefined) {
          if (op.kosul) k[ad] = op.kosul;
          else delete k[ad];
        }
      }
    }
    return { terms: t, kosullar: k };
  }

  function guncelle(id, degis) {
    const d = oku();
    const op = d.islemler.find((o) => o.id === id);
    if (!op) return null;
    degis(op, d);
    yaz(d);
    return op;
  }

  function cikar(id) {
    const d = oku();
    const once = d.islemler.length;
    d.islemler = d.islemler.filter((o) => o.id !== id);
    if (d.islemler.length !== once) yaz(d);
  }

  async function tekTur() {
    const sonuc = { gonderilen: 0, hatali: 0, kaldi: 0, yenidenDenenecek: false };
    for (;;) {
      // Her tur TAZE okunur: gönderim sürerken eklenen işlem aynı turda gider.
      const op = oku().islemler.find((o) => o.durum === "bekliyor");
      if (!op) break;
      ucustakiId = op.id;
      let yanit;
      try {
        yanit = await gonder(op);
      } catch {
        ucustakiId = null;
        guncelle(op.id, (o) => {
          o.deneme += 1;
          o.sonHata = { kod: 0, mesaj: "sunucuya ulaşılamadı" };
        });
        sonuc.yenidenDenenecek = true;
        olay("bekliyor", { islem: op, sebep: "ag" });
        break;
      }
      ucustakiId = null;
      const kod = yanit.durum;
      if (kod >= 200 && kod < 300) {
        // YALNIZ GÖNDERİLEN KİMLİK düşer. Aynı terimin daha ESKİ "hata" işlemleri
        // de düşer: kullanıcının daha yeni niyeti sunucuya ulaştı, eski reddedilmiş
        // değeri "tekrar dene" ile geri getirmek onu ezerdi.
        const d = oku();
        const anahtar = anahtarla(op.source);
        d.islemler = d.islemler.filter(
          (o) =>
            o.id !== op.id &&
            !(o.durum === "hata" && o.id < op.id && o.slug === op.slug && anahtarla(o.source) === anahtar)
        );
        yaz(d);
        sonuc.gonderilen += 1;
        olay("gonderildi", { islem: op, govde: yanit.govde });
        continue;
      }
      if (kod >= 500 || YENIDEN_DENENIR.has(kod)) {
        guncelle(op.id, (o) => {
          o.deneme += 1;
          o.sonHata = { kod, mesaj: yanit.mesaj || "" };
        });
        sonuc.yenidenDenenecek = true;
        olay("bekliyor", { islem: op, sebep: kod });
        break;
      }
      guncelle(op.id, (o) => {
        o.durum = "hata";
        o.hata = { kod, mesaj: yanit.mesaj || "" };
      });
      sonuc.hatali += 1;
      olay("hata", { islem: op, kod, mesaj: yanit.mesaj || "" });
    }
    sonuc.kaldi = oku().islemler.filter((o) => o.durum === "bekliyor").length;
    return sonuc;
  }

  /* Kuyruğu sunucuya boşalt. TEK UÇUŞ: eşzamanlı çağrılar aynı vaadi paylaşır,
     aynı işlem iki kez gönderilmez. */
  function bosalt() {
    if (!ucusVaadi) {
      ucusVaadi = tekTur().finally(() => {
        ucusVaadi = null;
      });
    }
    return ucusVaadi;
  }

  function yenidenDene(id) {
    guncelle(id, (o) => {
      o.durum = "bekliyor";
      delete o.hata;
    });
    olay("eklendi", { islem: { id }, kalici });
  }

  function vazgec(id) {
    cikar(id);
    olay("vazgecildi", { id });
  }

  return {
    ekle,
    islemler,
    kaynakDurumu,
    islemDurumu,
    bindir,
    bosalt,
    yenidenDene,
    vazgec,
    eskiKuyruguTasi,
    kalici: () => kalici,
    ucusta: () => ucustakiId !== null,
    ucustakiKimlik: () => ucustakiId,
  };
}
