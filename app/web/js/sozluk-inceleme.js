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

export async function incelemeyiYukle(slug) {
  const kutu = el("glossReviewBox");
  if (!kutu) return;
  let veri;
  try {
    const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(slug)}/glossary/review`, {}, 8000);
    if (!res.ok) throw new Error("sunucu " + res.status);
    veri = await res.json();
  } catch {
    // Çevrimdışı: kutu gizlenir (inceleme sunucu hesabıdır), liste çalışmaya devam eder.
    incelenecekler = new Set();
    kutu.hidden = true;
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
    dugme("Doğru", () => karar(slug, x, "onayla"), "pill"),
    dugme("Reddet", () => karar(slug, x, "reddet"), "pill terim-sil"),
    dugme("Düzenle", () => terimPaneliAc({ slug, source: x.source }), "pill")
  );
  kart.appendChild(eylem);
  return kart;
}

// MODEL DOĞRULAMASI: sözlüğün tamamını ücretsiz zincire sordurur (arka planda,
// sunucuda). Sonuç kayıtları DEĞİŞTİRMEZ; sorunlu bulunanlar bu listeye düşer.
function dogrulamaSatiri(slug) {
  const d = document.createElement("div");
  d.className = "inceleme-eylem inceleme-dogrula";
  const durumMetni = document.createElement("span");
  durumMetni.className = "gloss-hint";
  d.append(
    dugme("Sözlüğü doğrula", async () => {
      try {
        const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(slug)}/glossary/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kapsam: "hepsi" }),
        });
        const veri = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error((veri && veri.detail) || "sunucu " + res.status);
        if (veri.basladi) bildir("Doğrulama başladı (arka planda, birkaç dakika). Sonra listeyi tazele.");
        else if (veri.calisiyor) bildir("Doğrulama zaten sürüyor.");
        else bildir("Doğrulama başlatılamadı (sunucuda kapalı ya da anahtar yok).");
      } catch (err) {
        bildir("Doğrulama başlatılamadı (" + err.message + ").");
      }
    }),
    durumMetni
  );
  fetchWithTimeout(`/api/book/${encodeURIComponent(slug)}/glossary/verify`, {}, 8000)
    .then((r) => (r.ok ? r.json() : null))
    .then((v) => {
      if (!v) return;
      if (v.calisiyor) durumMetni.textContent = "doğrulama sürüyor…";
      else if (v.son && v.son.hata) durumMetni.textContent = "son doğrulama hata verdi";
      else if (v.son) durumMetni.textContent = `son doğrulama: ${v.son.islenen} kayıt, ${v.son.sorunlu} sorunlu`;
    })
    .catch(() => {});
  return d;
}

async function karar(slug, x, tur) {
  const govde = { source: x.source, karar: tur };
  const satirBilgisi = glossRows[x.source];
  if (tur === "reddet" && satirBilgisi && Number.isFinite(satirBilgisi.surum)) {
    govde.taban_surum = satirBilgisi.surum;
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
      bildir(`${x.source} başka bir cihazda değişti — liste tazelendi, tekrar bak.`);
    } else if (!res.ok) {
      throw new Error((veri && veri.detail) || "sunucu " + res.status);
    }
  } catch (err) {
    bildir("Karar kaydedilemedi (" + err.message + "). İnceleme çevrimiçi yapılır.");
    return;
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
