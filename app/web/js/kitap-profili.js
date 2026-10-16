/* KİTAP PROFİLİ kartı (2026-10-16, plan Faz 3): yeni kitabın ilk bölümlerinden önerilen profil
   alanları, kanıt alıntılarıyla; her alan Onayla / Reddet / Düzelt.

   Onaylanmamış öneri hiçbir istem ya da denetime girmez (sunucu kuralı). Onaylı profil o kitapta
   karakter defterini de açar — kart bunu açıkça söyler. Veri sunucudadır (`/api/book/{slug}/profil`);
   saf mantık `kitap-profili-yardimci.js`te (Node testli). */

import { diyalogAc, diyalogKapat } from "./diyalog.js";
import { durum } from "./durum.js";
import { fetchWithTimeout } from "./sozluk.js";
import { el } from "./temel.js";
import {
  ALANLAR, TURLER, alanDurumu, bekleyenSayisi, cikarimMetni, degerMetni, duzeltmeMetni, gosterilenDeger, kanitlar,
  metindenDeger, siraliAlanlar,
} from "./kitap-profili-yardimci.js";

const ZAMAN_ASIMI_MS = 15000;
const YOKLAMA_MS = 3000;
const p = { slug: null, veri: null, duzenlenen: null, mesgul: false, yoklama: null };

function oge(etiket, sinif, metin) {
  const n = document.createElement(etiket);
  if (sinif) n.className = sinif;
  if (metin !== undefined && metin !== null) n.textContent = metin;
  return n;
}
function dugme(metin, sinif, tik) {
  const b = oge("button", sinif, metin);
  b.type = "button";
  b.addEventListener("click", tik);
  return b;
}

async function istek(yol, govde) {
  const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(p.slug)}/profil${yol}`, govde
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) }
    : {}, ZAMAN_ASIMI_MS);
  let veri = null;
  try { veri = await res.json(); } catch { /* gövdesiz yanıt */ }
  if (!res.ok) {
    const d = veri && veri.detail;
    throw new Error(typeof d === "string" ? d : (d && d.message) || `sunucu ${res.status}`);
  }
  return veri;
}

export async function openKitapProfili(slug) {
  p.slug = slug;
  p.duzenlenen = null;
  el("kitapProfiliIcerik").replaceChildren(oge("p", "modal-hint", "Yükleniyor…"));
  el("kitapProfiliDurum").textContent = "";
  diyalogAc("kitapProfili");
  await yukle();
}

async function yukle() {
  try {
    p.veri = await istek("");
  } catch (e) {
    p.veri = null;
    el("kitapProfiliIcerik").replaceChildren(oge("p", "modal-hint", "Profil açılamadı: " + e.message));
    return;
  }
  ciz();
  yoklamayiAyarla();
}

function yoklamayiAyarla() {
  clearTimeout(p.yoklama);
  if (p.veri && p.veri.cikarim.calisiyor && el("kitapProfili").open) {
    p.yoklama = setTimeout(yukle, YOKLAMA_MS);
  }
}

function ciz() {
  const v = p.veri;
  const ic = [];
  const ozet = oge("div", "profil-ozet");
  const bekleyen = bekleyenSayisi(v);
  ozet.append(oge("p", "profil-ozet-baslik", v.kod_profili ? "Bu kitabın profili kodda tanımlı"
    : bekleyen ? `${bekleyen} alan onayını bekliyor` : v.profil_var ? "Profil etkin" : "Profil yok"));
  ozet.append(oge("p", "modal-hint", v.defter_acik
    ? "Karakter defteri bu kitapta çalışıyor: her yeni bölümde bir model çağrısı yapar."
    : "Onayladığın ilk alanla birlikte bu kitapta karakter defteri de çalışmaya başlar (her yeni bölümde bir model çağrısı)."));
  ic.push(ozet);

  for (const a of siraliAlanlar(v)) ic.push(alanKarti(a));

  // Yeniden öner: ilk bölümler değiştiyse (yeni bölüm geldi) ya da önceki deneme boş döndüyse.
  const alt = oge("div", "profil-oner");
  alt.append(oge("p", "profil-cikarim", cikarimMetni(v.cikarim)));
  if (!v.kod_profili) {
    const lbl = oge("label", "profil-secim");
    const kutu = document.createElement("input");
    kutu.type = "checkbox";
    kutu.id = "profilOnTarama";
    kutu.checked = !!v.cikarim.on_tarama_varsayilan;
    lbl.append(kutu, oge("span", null, "Sözlük ön taraması da yapılsın — adaylar doğrulanana kadar çeviriye girmez (deneysel)"));
    const b = dugme(v.cikarim.son ? "Yeniden öner" : "İlk bölümlerden öner", "pill", () => oner(kutu.checked, b));
    b.disabled = v.cikarim.calisiyor || p.mesgul;
    alt.append(lbl, b);
  }
  ic.push(alt);
  el("kitapProfiliIcerik").replaceChildren(...ic);
}

function alanKarti(a) {
  const tanim = ALANLAR[a.alan];
  const d = alanDurumu(a);
  const kart = oge("section", `profil-alan durum-${d.anahtar}`);
  kart.setAttribute("aria-labelledby", `profilAlan-${a.alan}`);
  const ust = oge("div", "profil-alan-ust");
  ust.append(oge("h4", "profil-alan-ad", tanim.etiket), oge("span", `profil-durum durum-${d.anahtar}`, d.etiket));
  ust.firstChild.id = `profilAlan-${a.alan}`;
  kart.append(ust);

  if (p.duzenlenen === a.alan) {
    kart.append(duzeltmeFormu(a));
    return kart;
  }
  const deger = gosterilenDeger(a);
  if (deger == null) {
    kart.append(oge("p", "profil-bos", d.anahtar === "kod" ? "Kodda tanımlı." : "İlk bölümlerde kanıtı bulunamadı."));
  } else {
    kart.append(oge("p", "profil-deger" + (a.alan === "diziler" ? " cok-satir" : ""), degerMetni(a.alan, deger)));
  }
  kart.append(oge("p", "profil-not", tanim.not));
  if (d.anahtar === "aday" || d.anahtar === "reddedildi") {
    for (const k of kanitlar(a)) {
      const fis = oge("figure", "profil-fis");
      const kenar = oge("span", "profil-fis-bolum", k.bolum != null ? String(k.bolum) : "–");
      kenar.setAttribute("aria-label", `bölüm ${k.bolum}`);
      const govde = oge("blockquote", null, k.alinti);
      govde.lang = "en";
      fis.append(kenar, govde);
      if (k.ek) fis.append(oge("figcaption", null, k.ek));
      kart.append(fis);
    }
  }
  if (d.anahtar !== "kod") {
    const eylem = oge("div", "profil-eylem");
    if (d.anahtar === "aday") {
      eylem.append(dugme("Reddet", "pill", (e) => karar(a.alan, "reddet", null, e.currentTarget)),
        dugme("Onayla", "next-btn", (e) => karar(a.alan, "onayla", null, e.currentTarget)));
    } else if (d.anahtar === "reddedildi") {
      eylem.append(dugme("Yine de onayla", "pill", (e) => karar(a.alan, "onayla", null, e.currentTarget)));
    }
    eylem.prepend(dugme(deger == null ? "Elle yaz" : "Düzelt", "pill profil-duzelt", () => {
      p.duzenlenen = a.alan;
      ciz();
      el("kitapProfiliIcerik").querySelector(".profil-duzelt-girdi")?.focus();
    }));
    kart.append(eylem);
  }
  return kart;
}

function duzeltmeFormu(a) {
  const tanim = ALANLAR[a.alan];
  const form = oge("form", "profil-duzelt-form");
  let girdi;
  if (tanim.tip === "secim") {
    girdi = document.createElement("select");
    for (const [deger, etiket] of Object.entries(TURLER)) {
      const o = document.createElement("option");
      o.value = deger;
      o.textContent = etiket;
      girdi.append(o);
    }
    girdi.value = gosterilenDeger(a) || "sistem";
  } else {
    girdi = document.createElement(tanim.tip === "dizi" ? "textarea" : "input");
    if (tanim.tip === "dizi") girdi.rows = 4;
    else girdi.type = "text";
    girdi.autocomplete = "off";
    girdi.spellcheck = false;
    girdi.lang = "en";
    girdi.value = duzeltmeMetni(a.alan, gosterilenDeger(a));
  }
  girdi.className = "profil-duzelt-girdi";
  girdi.setAttribute("aria-label", tanim.etiket);
  const ipucu = { liste: "Virgülle ayır: System, Quest", metin: "Metindeki yazımıyla", secim: "",
                  dizi: "Her satıra bir dizi: rutbe: Bronze, Silver, Gold" }[tanim.tip];
  const hata = oge("p", "profil-hata");
  hata.setAttribute("role", "alert");
  const eylem = oge("div", "profil-eylem");
  const kaydet = oge("button", "next-btn", "Kaydet");
  kaydet.type = "submit";
  eylem.append(dugme("Vazgeç", "pill", () => { p.duzenlenen = null; ciz(); }), kaydet);
  form.append(girdi);
  if (ipucu) form.append(oge("p", "profil-not", ipucu));
  form.append(hata, eylem);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    let deger;
    try {
      deger = metindenDeger(a.alan, girdi.value);
    } catch (err) {
      hata.textContent = err.message;
      girdi.focus();
      return;
    }
    karar(a.alan, "duzelt", deger, kaydet, hata);
  });
  return form;
}

async function karar(alan, karar_, deger, dugme_, hataYeri = null) {
  if (p.mesgul) return;
  p.mesgul = true;
  if (dugme_) dugme_.disabled = true;
  const satir = el("kitapProfiliDurum");
  satir.textContent = "Kaydediliyor…";
  try {
    p.veri = await istek("/karar", { alan, karar: karar_, deger });
    p.duzenlenen = null;
    satir.textContent = { onayla: "Onaylandı.", reddet: "Reddedildi.", duzelt: "Kaydedildi." }[karar_];
    ciz();
  } catch (e) {
    satir.textContent = "";
    (hataYeri || satir).textContent = "Kaydedilemedi: " + e.message;
    if (dugme_) dugme_.disabled = false;
  } finally {
    p.mesgul = false;
  }
}

async function oner(onTarama, dugme_) {
  if (p.mesgul) return;
  p.mesgul = true;
  dugme_.disabled = true;
  try {
    const v = await istek("/oner", { on_tarama: onTarama });
    p.veri = v;
    el("kitapProfiliDurum").textContent = v.basladi ? "Öneri başladı." : "Şu an başlatılamadı (çalışıyor ya da anahtar yok).";
  } catch (e) {
    el("kitapProfiliDurum").textContent = "Başlatılamadı: " + e.message;
  } finally {
    p.mesgul = false;
  }
  ciz();
  yoklamayiAyarla();
}

/* Kitap sayfasındaki düğmenin alt yazısı: bekleyen öneri varsa "3 öneri". Hata sessiz (çevrimdışı). */
export async function profilRozeti(slug) {
  const alt = el("openProfilAlt");
  alt.textContent = "kitap bilgisi";
  try {
    const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(slug)}/profil`, {}, ZAMAN_ASIMI_MS);
    if (!res.ok) return;
    const n = bekleyenSayisi(await res.json());
    if (n && durum.currentBookSlug === slug) alt.textContent = `${n} öneri`;
  } catch { /* çevrimdışı: varsayılan yazı kalır */ }
}

export function kur() {
  el("kitapProfiliKapat").addEventListener("click", () => diyalogKapat("kitapProfili"));
  el("kitapProfili").addEventListener("close", () => {
    clearTimeout(p.yoklama);
    if (p.slug) profilRozeti(p.slug); // onaylar sayıyı değiştirdi
  });
}
