/* Sözlük İNCELEME listesi: otomatik eklenen ve çakışan/belirsiz kayıtlar, nedenleriyle.

   Belge kararı: okumayı durduran zorunlu onay YOK. Liste sözlük ekranında katlanır
   bir kutudur; çakışanlar öne çıkar. Kararlar (onay, ret) sunucuda saklanır ve
   reddedilen aday bir daha otomatik eklenmez. Nedenleri üreten ikinci bir denetim
   motoru yazılmadı — sunucudaki bakım fonksiyonları açıklanabilir uyarıya dönüşüyor.

   Kararlar ÇEVRİMİÇİ yapılır (kuyruğa girmez): ret bir silme + kalıcı bir kural,
   çevrimdışı birikip ertesi gün sessizce uygulanması kullanıcıyı şaşırtırdı. */

import { bildir } from "./bildirim.js";
import { durum, views } from "./durum.js";
import {
  fetchGlossary,
  fetchWithTimeout,
  glossRows,
  kuyruk,
  kuyrukDinle,
  flushGlossQueue,
  renderGlossary,
} from "./sozluk.js";
import { anahtarla } from "./sozluk-kuyruk.js";
import { terimPaneliAc } from "./terim-paneli.js";
import { el } from "./temel.js";

// Süzgeç için: incelenecek kayıtların anahtarları (yazım varyantından bağımsız).
export let incelenecekler = new Set();

const NEDEN_ETIKETI = {
  karsilik_cakismasi: "ÇAKIŞMA",
  yakin_yazim: "YAKIN YAZIM",
  kardes_tutarsizligi: "STİL",
  yeni_otomatik: "YENİ",
  // Yazma kapısı ve doğrulama (sunucu `sozluk_kapi` / `sozluk_dogrulama`).
  bicim: "BİÇİM",
  sayi_uyumsuzlugu: "TEKİL/ÇOĞUL",
  yasak_karsilik: "YASAK",
  politika: "POLİTİKA",
  kalip_tutarsizligi: "KALIP",
  ihlal_suphesi: "MODELLER UYMUYOR",
  dogrulama: "DOĞRULAMA",
  sozcuk_karismasi: "SINIF SÖZCÜĞÜ",
  ad_tutarliligi: "AD POLİTİKASI",
};

function dugme(metin, fn, sinif = "pill") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = sinif;
  b.textContent = metin;
  b.addEventListener("click", fn);
  return b;
}

// Liste sunucuda HESAPLANIR; ilk hesap sunucuda on saniyeleri bulabiliyor (sonra
// önbellekten gelir). 8 sn'lik sınır listeyi telefonda hiç açtırmıyordu ve her
// karardan sonraki tazeleme de düşüp eski listeyi bırakıyordu.
const INCELEME_ZAMAN_ASIMI = 60000;

// Panelden (Düzenle) kaydedilen ya da silinen kayıt incelenmiş sayılır: kartı hemen
// düşür, listeyi kısa bir gecikmeyle sunucudan tazele. Panel kuyruk üzerinden yazar ve
// listeyi hiç tazelemiyordu — kayıt kaydedildiği hâlde listede duruyordu.
let kuyrukBagli = false;
let tazelemeZamanlayici = null;

function kuyrugaBaglan() {
  if (kuyrukBagli) return;
  kuyrukBagli = true;
  kuyrukDinle((ad, veri) => {
    if (ad !== "gonderildi" || !veri || !veri.islem) return;
    const op = veri.islem;
    if (op.slug !== durum.currentBookSlug) return;
    const anahtar = anahtarla(op.source);
    if (!incelenecekler.has(anahtar)) return;
    const kutu = el("glossReviewList");
    for (const kart of kutu ? kutu.querySelectorAll(".inceleme-kart") : []) {
      if (anahtarla(kart.dataset.sozlukKaynak || "") === anahtar) {
        kart.remove();
        sayaciAzalt();
      }
    }
    incelenecekler.delete(anahtar);
    clearTimeout(tazelemeZamanlayici);
    tazelemeZamanlayici = setTimeout(() => incelemeyiYukle(op.slug), 800);
  });
}

function sayaciAzalt() {
  const sayi = el("glossReviewSayi");
  const m = /\((\d+)\)/.exec(sayi.textContent);
  if (m) sayi.textContent = `İNCELENECEKLER (${Math.max(0, Number(m[1]) - 1)})`;
}

export async function incelemeyiYukle(slug) {
  const kutu = el("glossReviewBox");
  if (!kutu) return;
  kuyrugaBaglan();
  const sayi = el("glossReviewSayi");
  if (kutu.hidden || !sayi.textContent.includes("(")) {
    kutu.hidden = false;
    sayi.textContent = "İNCELENECEKLER (hesaplanıyor…)";
  }
  let veri;
  try {
    const res = await fetchWithTimeout(
      `/api/book/${encodeURIComponent(slug)}/glossary/review`, {}, INCELEME_ZAMAN_ASIMI
    );
    if (!res.ok) throw new Error("sunucu " + res.status);
    veri = await res.json();
  } catch (err) {
    if (slug !== durum.currentBookSlug) return;
    if (!navigator.onLine) {
      // Çevrimdışı: kutu gizlenir (inceleme sunucu hesabıdır), liste çalışmaya devam eder.
      incelenecekler = new Set();
      kutu.hidden = true;
      return;
    }
    // Sessizce gizlemek "kararım kaydedilmedi" gibi görünüyordu: hata görünür, yeniden denenir.
    kutu.hidden = false;
    sayi.textContent = "İNCELENECEKLER (yüklenemedi)";
    const govde = el("glossReviewList");
    const p = document.createElement("p");
    p.className = "gloss-hint";
    p.textContent = `Liste yüklenemedi (${err.name === "AbortError" ? "zaman aşımı" : err.message}). `;
    p.appendChild(dugme("Tekrar dene", () => incelemeyiYukle(slug)));
    govde.replaceChildren(p);
    return;
  }
  if (slug !== durum.currentBookSlug) return;
  incelenecekler = new Set(veri.liste.map((x) => anahtarla(x.source)));
  ciz(slug, veri);
}

function ciz(slug, { liste, red }) {
  const kutu = el("glossReviewBox");
  kutu.hidden = liste.length === 0 && red.length === 0;
  el("glossReviewSayi").textContent = `İNCELENECEKLER (${liste.length})`;
  const govde = el("glossReviewList");
  govde.replaceChildren();
  govde.appendChild(dogrulamaSatiri(slug));
  if (!liste.length) {
    const p = document.createElement("p");
    p.className = "gloss-hint";
    p.textContent = "İncelenecek kayıt yok.";
    govde.appendChild(p);
  }
  for (const x of liste) govde.appendChild(satir(slug, x));
  if (red.length) {
    const baslik = document.createElement("p");
    baslik.className = "terim-etiket";
    baslik.textContent = `REDDEDİLENLER (${red.length}) — bir daha otomatik eklenmez`;
    govde.appendChild(baslik);
    for (const r of red) {
      const d = document.createElement("div");
      d.className = "inceleme-red";
      const m = document.createElement("span");
      m.lang = "en";
      m.textContent = `${r.source}${r.target ? " → " + r.target : ""}`;
      d.append(m, dugme("Reddi kaldır", () => reddiKaldir(slug, r.source)));
      govde.appendChild(d);
    }
  }
}

function satir(slug, x) {
  const kart = document.createElement("div");
  kart.className = "inceleme-kart";
  kart.dataset.sozlukSlug = slug;
  kart.dataset.sozlukKaynak = x.source;
  const ust = document.createElement("p");
  ust.className = "inceleme-ust";
  const ad = document.createElement("span");
  ad.className = "gloss-source";
  ad.lang = "en";
  ad.textContent = x.source;
  ust.append(ad, document.createTextNode(" → " + x.target));
  // TUTULDU: kapıya takılan aday prompt'a GİRMİYOR. Okuyucu bunu bilmeli —
  // "Doğru" demek terimi çeviride kural yapar.
  if (x.durum === "tutuldu") {
    const t = document.createElement("span");
    t.className = "gloss-cip inceleme-tutuldu";
    t.textContent = "TUTULDU";
    t.title = "Kapıya takıldı: çeviride kullanılmıyor. Onaylarsan kural olur.";
    ust.appendChild(t);
  }
  for (const n of x.nedenler) {
    const c = document.createElement("span");
    c.className = "gloss-cip inceleme-neden inceleme-" + n.tur;
    c.textContent = NEDEN_ETIKETI[n.tur] || n.tur;
    ust.appendChild(c);
  }
  kart.appendChild(ust);
  for (const n of x.nedenler) {
    if (n.tur === "yeni_otomatik") continue;
    const p = document.createElement("p");
    p.className = "inceleme-aciklama";
    p.textContent = n.aciklama;
    kart.appendChild(p);
  }
  if (x.tanim) {
    const t = document.createElement("p");
    t.className = "inceleme-aciklama inceleme-tanim";
    t.textContent = "Tanım: " + x.tanim;
    kart.appendChild(t);
  }
  if (x.kaynak_cumle) {
    const c = document.createElement("p");
    c.className = "terim-ornek-cumle";
    c.lang = "en";
    c.textContent = `“${x.kaynak_cumle}”` + (x.first_chapter ? ` — bölüm ${x.first_chapter}` : "");
    kart.appendChild(c);
  }
  const eylem = document.createElement("div");
  eylem.className = "inceleme-eylem";
  eylem.append(
    dugme("Doğru", () => karar(slug, x, "onayla", kart), "pill"),
    dugme("Reddet", () => karar(slug, x, "reddet", kart), "pill terim-sil"),
    dugme("Düzenle", () => terimPaneliAc({ slug, source: x.source }), "pill")
  );
  kart.appendChild(eylem);
  return kart;
}

// MODEL DOĞRULAMASI: İNCELENECEK kayıtları ücretsiz zincire sordurur (arka planda,
// sunucuda). Eskiden sözlüğün TAMAMINI (1100+ kayıt) sorduruyordu; sunucu yalnız bağlam
// hazırlığında saatler harcıyor, ekran da ilerleme göstermediği için "takıldı" sanılıyordu.
// Şimdi ilerleme 4 sn'de bir okunur, iş durdurulabilir, bitince liste kendiliğinden tazelenir.
const DOGRULAMA_ARALIK = 4000;
let dogrulamaZamanlayici = null;

function dogrulamaUcu(slug) {
  return `/api/book/${encodeURIComponent(slug)}/glossary/verify`;
}

function dogrulamaSatiri(slug) {
  const d = document.createElement("div");
  d.className = "inceleme-eylem inceleme-dogrula";
  const durumMetni = document.createElement("span");
  durumMetni.className = "gloss-hint";
  const baslat = dugme("İncelenecekleri doğrula", async () => {
    try {
      const res = await fetchWithTimeout(dogrulamaUcu(slug), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kapsam: "bekleyen" }),
      });
      const veri = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((veri && veri.detail) || "sunucu " + res.status);
      if (veri.basladi) bildir("Doğrulama başladı. İlerleme bu satırda görünür; bitince liste tazelenir.");
      else if (veri.calisiyor) bildir("Doğrulama zaten sürüyor.");
      else bildir("Doğrulama başlatılamadı (sunucuda kapalı ya da anahtar yok).");
      izle(slug, d, durumMetni, baslat, durdur);
    } catch (err) {
      bildir("Doğrulama başlatılamadı (" + err.message + ").");
    }
  });
  baslat.title = "İnceleme listesindeki kayıtları ücretsiz modele, kitaptaki cümleleriyle sordurur. "
    + "Uygun bulunan otomatik kayıtlar kural olur; sorunlu olanlar burada kalır.";
  const durdur = dugme("Durdur", async () => {
    try {
      await fetchWithTimeout(dogrulamaUcu(slug), { method: "DELETE" });
      durumMetni.textContent = "durduruluyor…";
    } catch {
      bildir("Durdurulamadı (sunucuya ulaşılamadı).");
    }
  }, "pill terim-sil");
  durdur.hidden = true;
  d.append(baslat, durdur, durumMetni);
  izle(slug, d, durumMetni, baslat, durdur);
  return d;
}

function izle(slug, satir, durumMetni, baslat, durdur) {
  clearTimeout(dogrulamaZamanlayici);
  let sonCalisiyor = null;
  const tur = async () => {
    if (!satir.isConnected || slug !== durum.currentBookSlug) return;
    let v = null;
    try {
      const r = await fetchWithTimeout(dogrulamaUcu(slug), {}, 8000);
      v = r.ok ? await r.json() : null;
    } catch {
      v = null;
    }
    if (v) {
      baslat.disabled = v.calisiyor;
      durdur.hidden = !v.calisiyor;
      if (v.calisiyor) {
        durumMetni.textContent = v.durduruluyor
          ? "durduruluyor…"
          : "doğrulama sürüyor" + (v.ilerleme ? " — " + v.ilerleme.mesaj : "…");
      } else if (v.son && v.son.hata) {
        durumMetni.textContent = "son doğrulama hata verdi: " + v.son.hata;
      } else if (v.son) {
        durumMetni.textContent = `son doğrulama${v.son.durduruldu ? " (durduruldu)" : ""}: `
          + `${v.son.islenen} kayıt, ${v.son.sorunlu} sorunlu`;
      } else {
        durumMetni.textContent = "";
      }
      // Bitti: sonuçlar listeyi değiştirdi, kendiliğinden tazele.
      if (sonCalisiyor === true && !v.calisiyor) {
        await incelemeyiYukle(slug);
        return;
      }
      sonCalisiyor = v.calisiyor;
      if (!v.calisiyor) return;
    }
    dogrulamaZamanlayici = setTimeout(tur, DOGRULAMA_ARALIK);
  };
  tur();
}

async function karar(slug, x, tur, kart) {
  const govde = { source: x.source, karar: tur };
  // Taban sürüm İNCELEME satırının kendi sürümüdür: sözlük ekranının satırı (glossRows)
  // tazelenmemiş olabiliyordu ve her denemede 409 dönüyordu.
  const surum = Number.isFinite(x.surum) ? x.surum : (glossRows[x.source] || {}).surum;
  if (tur === "reddet" && Number.isFinite(surum)) govde.taban_surum = surum;
  if (kart) {
    kart.classList.add("inceleme-isleniyor");
    kart.querySelectorAll("button").forEach((b) => (b.disabled = true));
  }
  let veri;
  try {
    const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(slug)}/glossary/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
    });
    veri = await res.json().catch(() => ({}));
    if (res.status === 409) {
      bildir(`${x.source} bu arada değişti (arka plan doğrulaması ya da başka cihaz) — liste tazelendi, tekrar bak.`);
    } else if (!res.ok) {
      throw new Error((veri && veri.detail) || "sunucu " + res.status);
    }
  } catch (err) {
    if (kart) {
      kart.classList.remove("inceleme-isleniyor");
      kart.querySelectorAll("button").forEach((b) => (b.disabled = false));
    }
    bildir("Karar kaydedilemedi (" + err.message + "). İnceleme çevrimiçi yapılır.");
    return;
  }
  // Karar kaydedildi: kart HEMEN düşer (liste tazelenmesi sürse bile kabul edildiği görünür).
  if (kart && veri && veri.ok) {
    kart.remove();
    incelenecekler.delete(anahtarla(x.source));
    sayaciAzalt();
    if (tur === "onayla") bildir(`${x.source} doğru olarak işaretlendi.`);
  }
  if (tur === "reddet" && veri && veri.silinen) {
    const silinen = veri.silinen;
    bildir(`${x.source} reddedildi; bir daha otomatik eklenmeyecek.`, {
      eylem: {
        etiket: "GERİ AL",
        fn: async () => {
          await reddiKaldir(slug, silinen.source, false);
          kuyruk.ekle(slug, silinen.source, { tur: "geri", kayit: silinen });
          await flushGlossQueue();
          await tazele(slug);
          bildir(`${x.source} geri alındı.`);
        },
      },
    });
  }
  await tazele(slug);
}

async function reddiKaldir(slug, source, tazeleSonra = true) {
  try {
    await fetchWithTimeout(
      `/api/book/${encodeURIComponent(slug)}/glossary/red?source=${encodeURIComponent(source)}`,
      { method: "DELETE" }
    );
  } catch {
    bildir("Ret kaldırılamadı (sunucuya ulaşılamadı).");
    return;
  }
  if (tazeleSonra) await tazele(slug);
}

async function tazele(slug) {
  if (slug === durum.currentBookSlug && !views.glossary.hidden) {
    renderGlossary(await fetchGlossary(slug));
  }
  await incelemeyiYukle(slug);
}
