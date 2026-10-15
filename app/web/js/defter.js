/* DEFTER ekranı (2026-10-15, Faz 4): kişiler, yaratıklar, anılar, nitelikler, gölge/yankılar;
   karakter kartı (adlar, rün listesi, anılar, bağlar, sen/siz) ve elle düzenleme.

   Veri sunucudadır (`/api/book/{slug}/defter*`); bu ekran çevrimiçi çalışır. Spoiler süzgecini
   SUNUCU uygular: konum verilmez, sunucu kitabın okuma konumunu kullanır; "Tüm kitap" yalnız
   açıkça seçilince `spoiler=true` gider. Saf mantık `defter-yardimci.js`te (Node testli). */

import { durum } from "./durum.js";
import { diyalogAc, diyalogKapat } from "./diyalog.js";
import { showView } from "./gezinme.js";
import { fetchWithTimeout } from "./sozluk.js";
import { el } from "./temel.js";
import {
  SEKMELER, alanEtiketi, egoDugumleri, kademeMetni, formdanKayit, hitapNotu, kayitFormu, runSatirlari, sekmeSatirlari, sinirMetni,
  tr,
} from "./defter-yardimci.js";
import { fetchBooks } from "./kutuphane.js";

const ZAMAN_ASIMI_MS = 15000;
const HITAP_SINIRI = 12;
const LISTE_SINIRI = 6; // kartta anı/yankı listesinin ilk görünen sayısı (Sunny'de 41 anı)
const p = { slug: null, tum: false, sekme: "kisiler", sorgu: "", veri: null, kart: null, kartKimlik: null,
            form: null, tumHitap: false, acik: new Set() };

/* ---------- küçük DOM yardımcıları ---------- */
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
function adMetni(k, karsiliklar) {
  // Görünen ad Türkçe karşılıktır (varsa); İngilizcesi yanında küçük yazılır.
  const tr_ = k.tr || (karsiliklar && karsiliklar[k.ad]);
  return tr_ && tr_ !== k.ad ? [tr_, k.ad] : [k.ad, null];
}
const sorgu = () => (p.tum ? "?spoiler=true" : "");

async function istek(yol, secenek = {}) {
  const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(p.slug)}/defter${yol}`, {
    headers: { "Content-Type": "application/json" }, ...secenek,
  }, ZAMAN_ASIMI_MS);
  let govde = null;
  try { govde = await res.json(); } catch { /* gövdesiz yanıt */ }
  if (!res.ok) {
    const d = govde && govde.detail;
    throw new Error(typeof d === "string" ? d : (d && d.message) || `sunucu ${res.status}`);
  }
  return govde;
}

/* ---------- ekran ---------- */
export async function openDefter(slug, tum = false) {
  p.slug = slug;
  p.tum = !!tum;
  durum.currentBookSlug = slug;
  el("defterTitle").textContent = "DEFTER";
  showView("defter");
  // Başlık kitabın adıdır; kütüphane alınamazsa (çevrimdışı) yalnız "DEFTER" kalır.
  fetchBooks().then((kitaplar) => {
    const kitap = (kitaplar || []).find((b) => b.slug === slug);
    if (kitap && p.slug === slug) el("defterTitle").textContent = "DEFTER — " + kitap.title;
  }).catch(() => {});
  window.scrollTo(0, 0);
  await yukle();
}

async function yukle() {
  el("defterDurum").textContent = "Yükleniyor…";
  try {
    p.veri = await istek(sorgu());
    el("defterDurum").textContent = "";
  } catch (e) {
    p.veri = null;
    el("defterDurum").textContent = "Defter açılamadı: " + e.message;
  }
  ciz();
}

function ciz() {
  const v = p.veri;
  el("defterSinirMetin").textContent = v ? sinirMetni(v.sinir) : "…";
  el("defterSinirNot").textContent = p.tum ? "İlerideki bölümler de görünüyor" : "Okuma konumun · ilerisi gizli";
  el("defterSinirBtn").textContent = p.tum ? "Okuma konumuna dön" : "Tüm kitap";
  el("defterSinirBtn").setAttribute("aria-pressed", p.tum ? "true" : "false");
  const sekmeler = el("defterSekmeler");
  sekmeler.replaceChildren(...SEKMELER.map((s) => {
    const b = dugme(s.etiket, "chip", () => { p.sekme = s.anahtar; ciz(); });
    b.dataset.defterSekme = s.anahtar;
    b.setAttribute("aria-pressed", s.anahtar === p.sekme ? "true" : "false");
    return b;
  }));
  const sekme = SEKMELER.find((s) => s.anahtar === p.sekme);
  const satirlar = v ? sekmeSatirlari(v, p.sekme, p.sorgu) : [];
  el("defterSayi").textContent = v ? `${satirlar.length} ${sekme.tekil}` : "";
  el("defterEkleBtn").hidden = !v || !sekme.tur;
  el("defterEkleBtn").textContent = sekme.tur ? `+ ${sekme.tekil[0].toLocaleUpperCase("tr")}${sekme.tekil.slice(1)} ekle` : "";
  const liste = el("defterListe");
  liste.replaceChildren(...satirlar.slice(0, 300).map((k) => satir(k, v.karsiliklar || {})));
  if (v && !satirlar.length) liste.append(oge("li", "defter-bos", p.sorgu ? "Aramaya uyan kayıt yok." : "Bu bölümde henüz kayıt yok."));
}

function satir(k, karsiliklar) {
  const li = oge("li", "defter-satir");
  const govde = oge("button", "defter-satir-dugme");
  govde.type = "button";
  const [ad, en] = adMetni(k, karsiliklar);
  const monogram = oge("span", "defter-monogram" + (k.run ? " run" : ""), (ad || "?").trim()[0] || "?");
  monogram.setAttribute("aria-hidden", "true");
  const metin = oge("span", "defter-satir-metin");
  const baslik = oge("span", "defter-satir-ad", ad);
  const ek = [en, ...(k.takma || []).slice(0, 2)].filter(Boolean).join(" · ");
  if (ek) baslik.append(oge("small", null, ek));
  const alt = oge("span", "defter-satir-alt", altMetin(k, karsiliklar));
  metin.append(baslik, alt);
  const sag = oge("span", "defter-satir-sag");
  if (p.sekme === "kisiler" || p.sekme === "gruplar") {
    sag.append(oge("b", null, String(k.bolum_sayisi)), oge("small", null, "bölüm"));
  } else if (k.ilk_bolum != null) {
    sag.append(oge("b", null, String(k.ilk_bolum)), oge("small", null, "bölüm"));
  }
  govde.append(monogram, metin, sag);
  govde.addEventListener("click", () => satiraTikla(k));
  li.append(govde);
  return li;
}

function altMetin(k, karsiliklar) {
  const a = k.alanlar || {};
  switch (p.sekme) {
    case "kisiler":
    case "gruplar": {
      const parca = [];
      if (k.run) parca.push("Rün listesi");
      if (k.ani_sayisi) parca.push(`${k.ani_sayisi} anı`);
      parca.push(`${k.bag_sayisi} bağ`, `${k.hitap_cifti} hitap çifti`);
      if (k.karisik) parca.push(`${k.karisik} karışık`);
      if (k.sozlukte === false) parca.push("sözlükte yok");
      return parca.join(" · ");
    }
    case "yaratiklar":
      return [tr(a.rutbe, karsiliklar), tr(a.sinif, karsiliklar)].filter(Boolean).join(" ") +
        (k.oldurulme != null ? ` · ${k.sahip || "?"} öldürdü, bölüm ${k.oldurulme}` : k.kimlik ? " · sözlükte" : "");
    case "anilar":
      return [tr(a.tur, karsiliklar), tr(a.rutbe, karsiliklar), kademeMetni(a.kademe),
        k.efsun_sayisi && `${k.efsun_sayisi} efsun`, k.sahip].filter(Boolean).join(" · ");
    case "yankilar":
      return [k.tur === "golge" ? "gölge" : "yankı", tr(a.rutbe, karsiliklar), tr(a.sinif, karsiliklar), k.sahip]
        .filter(Boolean).join(" · ");
    default:
      return k.sahip || "";
  }
}

function satiraTikla(k) {
  if (p.sekme === "kisiler" || p.sekme === "gruplar") return kartAc(k.kimlik);
  if (!k.anahtar) {
    // Sözlükten gelen yaratık: defter kaydı yok; düzeltmesi sözlükte.
    el("defterDurum").textContent = `${k.ad}: sözlük kaydı — karşılığını Sözlük ekranından düzeltebilirsin.`;
    return;
  }
  kayitFormuAc(k.tur, k.sahip, k);
}

/* ---------- karakter kartı ---------- */
async function kartAc(kimlik) {
  p.kartKimlik = kimlik;
  p.tumHitap = false;
  p.acik = new Set();
  el("defterKart-baslik").textContent = "…";
  el("defterKartIcerik").replaceChildren(oge("p", "modal-hint", "Yükleniyor…"));
  diyalogAc("defterKart");
  await kartYukle();
}

async function kartYukle() {
  try {
    const ek = p.tum ? "&spoiler=true" : "";
    p.kart = await istek(`/kart?kimlik=${encodeURIComponent(p.kartKimlik)}${ek}`);
    kartCiz();
  } catch (e) {
    el("defterKartIcerik").replaceChildren(oge("p", "modal-hint", "Kart açılamadı: " + e.message));
  }
}

function bolumBasligi(metin, eylem) {
  const kap = oge("div", "defter-bolum-ust");
  kap.append(oge("p", "terim-etiket", metin));
  if (eylem) kap.append(eylem);
  return kap;
}

function kartCiz() {
  const k = p.kart;
  const kars = k.karsiliklar || {};
  el("defterKart-baslik").textContent = k.tr && k.tr !== k.ad ? k.tr : k.ad;
  const ic = [];
  const etiketler = oge("div", "defter-etiketler");
  for (const t of [k.tur === "orgut" ? "Grup" : "Kişi", `${k.bolum_sayisi} bölüm`, k.ilk_bolum != null && `İlk: bölüm ${k.ilk_bolum}`]) {
    if (t) etiketler.append(oge("span", "gloss-cip", t));
  }
  ic.push(etiketler);
  if (!k.sozlukte) {
    ic.push(oge("p", "modal-hint", "Bu kişi sözlükte yok; bağ eklemek ve karşılığını sabitlemek için önce sözlüğe ekle."),
      dugme("Sözlüğe ekle", "pill", () => sozlugeEkleFormu(k.ad, "kisi")));
  }

  // Adlar ve takma ad önerileri
  ic.push(bolumBasligi("Adları"));
  const adlar = oge("div", "defter-cipler");
  for (const a of k.adlar) adlar.append(oge("span", "defter-ad", a.tr && a.tr !== a.ad ? `${a.tr} (${a.ad})` : a.ad));
  if (!k.adlar.length) adlar.append(oge("span", "modal-hint", "Takma adı bilinmiyor."));
  ic.push(adlar);
  for (const o of k.oneriler) {
    const s = oge("div", "defter-oneri");
    s.append(oge("span", null, `“${o.ad}” takma ad önerisi · ${o.destek} bölüm`),
      dugme("Ayrı kişi", "pill", () => takmaAdKarari(o, "ayri")),
      dugme("Aynı kişi", "next-btn", () => takmaAdKarari(o, "ayni")));
    ic.push(s);
  }

  // Rün listesi + rütbe geçmişi
  if (k.run.length || k.rutbeler.length || k.sozlukte) {
    ic.push(bolumBasligi("Rün listesi", dugme("+ Alan", "pill", () => kayitFormuAc("alan", k.ad))));
    const tablo = oge("dl", "defter-run");
    for (const satir_ of runSatirlari(k.run)) {
      const dt = oge("dt", null, alanEtiketi(satir_.ad));
      const dd = oge("dd");
      if (satir_.kayitlar.length > 1) {
        // Çok değerli alan (yetenekler): her değer kendi düzenleme çipi.
        const c = oge("span", "defter-cipler");
        for (const a of satir_.kayitlar) {
          c.append(dugme(tr(a.deger, kars) + (a.origin === "elle" ? " · elle" : ""), "defter-ad",
            () => kayitFormuAc("alan", k.ad, a)));
        }
        dd.append(c);
      } else {
        const a = satir_.kayitlar[0];
        const deger = tr(a.deger, kars);
        const metin = oge("span", "defter-run-deger", deger);
        const ince = [deger !== a.deger && a.deger, a.ilk_bolum != null && `bölüm ${a.ilk_bolum}`,
          a.origin === "elle" && "elle"].filter(Boolean).join(" · ");
        if (ince) metin.append(oge("small", null, ince));
        dd.append(metin, dugme("düzenle", "defter-duzenle", () => kayitFormuAc("alan", k.ad, a)));
      }
      tablo.append(dt, dd);
    }
    if (k.rutbeler.length) {
      tablo.append(oge("dt", null, "Rütbe geçmişi"));
      const dd = oge("dd");
      const metin = oge("span", "defter-run-deger", k.rutbeler.map((r) => r.tr || r.ad).join(" → "));
      metin.append(oge("small", null, "anlatımdan · " + k.rutbeler.map((r) => `${r.tr || r.ad} ${r.ilk_bolum}`).join(", ")));
      dd.append(metin);
      tablo.append(dd);
    }
    if (!k.run.length && !k.rutbeler.length) tablo.append(oge("dd", "modal-hint", "Rün mesajında görülmedi."));
    ic.push(tablo);
  }

  // Anılar (efsunlarıyla)
  ic.push(bolumBasligi(`Anılar · ${k.anilar.length}`, dugme("+ Ekle", "pill", () => kayitFormuAc("ani", k.ad))));
  ic.push(...kisalt("anilar", k.anilar, (a) => aniSatiri(a, kars), "Tüm anılar"));
  if (!k.anilar.length) ic.push(oge("p", "defter-bos-not", "Henüz anı yok. Rün mesajında görülünce eklenir; sen de ekleyebilirsin."));
  // Gölgeler ve yankılar
  ic.push(bolumBasligi(`Gölgeler ve yankılar · ${k.yankilar.length}`,
    dugme("+ Ekle", "pill", () => kayitFormuAc("yanki", k.ad))));
  ic.push(...kisalt("yankilar", k.yankilar, (y) => aniSatiri(y, kars), "Tüm gölge ve yankılar"));
  if (!k.yankilar.length) ic.push(oge("p", "defter-bos-not", "Gölge ya da yankı kaydı yok."));
  // Nitelikler
  ic.push(bolumBasligi(`Nitelikler · ${k.nitelikler.length}`, dugme("+ Ekle", "pill", () => kayitFormuAc("nitelik", k.ad))));
  const nit = oge("div", "defter-cipler");
  for (const n of k.nitelikler) {
    const [ad] = adMetni(n, kars);
    nit.append(dugme(ad + (n.origin === "elle" ? " · elle" : ""), "defter-ad", () => kayitFormuAc("nitelik", k.ad, n)));
  }
  if (!k.nitelikler.length) nit.append(oge("span", "defter-bos-not", "Nitelik kaydı yok."));
  ic.push(nit);

  // Bağlar
  ic.push(bolumBasligi(`Bağlar · ${k.baglar.length}`, k.sozlukte ? dugme("+ Bağ ekle", "pill", bagFormu) : null));
  if (k.baglar.length) ic.push(egoCizimi(k));
  else ic.push(oge("p", "defter-bos-not", "Bağ kaydı yok."));
  const bl = oge("ul", "defter-baglar");
  const bagSinir = p.acik.has("baglar") ? k.baglar.length : LISTE_SINIRI * 2;
  for (const b of k.baglar.slice(0, bagSinir)) {
    const li = oge("li");
    const onayli = b.durum === "onaylandi" || (b.guven || 0) >= 0.8;
    li.append(oge("span", "defter-iliski", b.yon === "gelen" ? `${b.etiket} olduğu` : b.etiket));
    const h = oge("span", "defter-bag-hedef", b.diger_tr && b.diger_tr !== b.diger_ad ? b.diger_tr : b.diger_ad);
    const ince = [b.ilk_bolum != null && `bölüm ${b.ilk_bolum}’den beri`, b.origin === "manual" && "elle",
      !onayli && "doğrulanmadı"].filter(Boolean).join(" · ");
    if (ince) h.append(oge("small", null, ince));
    li.append(h);
    const sag = oge("span", "defter-destek", onayli ? `${b.destek} bölüm` : "aday");
    sag.append(dugme("kaldır", "defter-duzenle", () => bagKaldir(b)));
    li.append(sag);
    bl.append(li);
  }
  ic.push(bl);
  if (k.baglar.length > bagSinir) {
    ic.push(dugme(`Tüm bağlar (${k.baglar.length})`, "pill defter-tumu", () => { p.acik.add("baglar"); kartCiz(); }));
  }

  // Hitap
  ic.push(bolumBasligi("Hitap · çeviride sen mi, siz mi"));
  const hl = oge("ul", "defter-hitaplar");
  const hitaplar = p.tumHitap ? k.hitaplar : k.hitaplar.slice(0, HITAP_SINIRI);
  for (const h of hitaplar) {
    const li = oge("li");
    const ust = oge("div", "defter-hitap-ust");
    ust.append(oge("span", null, `${h.konusan} → ${h.muhatap}`));
    const sec = oge("span", "segmented defter-secmeli");
    sec.setAttribute("role", "group");
    sec.setAttribute("aria-label", `${h.konusan}, ${h.muhatap} için`);
    for (const b of ["sen", "siz"]) {
      const d = dugme(b, "seg", () => hitapKarari(h, b, sec));
      d.setAttribute("aria-pressed", (h.kararli || h.elle) && h.bicim === b ? "true" : "false");
      sec.append(d);
    }
    ust.append(sec);
    li.append(ust, oge("p", "defter-hitap-not" + (!h.kararli && !h.elle ? " karisik" : ""), hitapNotu(h)));
    hl.append(li);
  }
  if (!k.hitaplar.length) hl.append(oge("li", "modal-hint", "Hitap kaydı yok."));
  ic.push(hl);
  if (!p.tumHitap && k.hitaplar.length > HITAP_SINIRI) {
    ic.push(dugme(`Tüm hitaplar (${k.hitaplar.length})`, "pill", () => { p.tumHitap = true; kartCiz(); }));
  }
  ic.push(oge("p", "modal-hint defter-not",
    "Bilgiler çevrilmiş bölümlerden otomatik çıkarılır; okuma konumunun ilerisi gösterilmez. Senin seçtiğin hitap otomatik sayımdan önce gelir."));
  el("defterKartIcerik").replaceChildren(...ic);
}

function kisalt(anahtar, liste, ciz_, etiket) {
  const sinir = p.acik.has(anahtar) ? liste.length : LISTE_SINIRI;
  const out = liste.slice(0, sinir).map(ciz_);
  if (liste.length > sinir) {
    out.push(dugme(`${etiket} (${liste.length})`, "pill defter-tumu", () => { p.acik.add(anahtar); kartCiz(); }));
  }
  return out;
}

function aniSatiri(a, kars) {
  const kap = oge("button", "defter-ani");
  kap.type = "button";
  const [ad, en] = adMetni(a, kars);
  const baslik = oge("span", "defter-ani-ad", ad);
  if (en) baslik.append(oge("small", null, en));
  if (a.origin === "elle") baslik.append(oge("span", "defter-elle", "elle"));
  const al = a.alanlar || {};
  const alt = [a.tur === "golge" ? "gölge" : a.tur === "yanki" ? "yankı" : null, tr(al.tur, kars), tr(al.rutbe, kars),
    tr(al.sinif, kars), kademeMetni(al.kademe)].filter(Boolean).join(" · ");
  kap.append(baslik, oge("span", "defter-bolum-no", a.ilk_bolum != null ? `bölüm ${a.ilk_bolum}` : ""));
  if (alt) kap.append(oge("span", "defter-ani-alt", alt));
  const cipler = [...(a.efsunlar || []).map((e) => adMetni(e, kars)[0]), ...(al.nitelikler || []).map((n) => tr(n, kars))];
  if (cipler.length) {
    const c = oge("span", "defter-efsunlar");
    for (const x of cipler) c.append(oge("span", "defter-efsun", x));
    kap.append(c);
  }
  kap.addEventListener("click", () => kayitFormuAc(a.tur, a.sahip, a));
  return kap;
}

function egoCizimi(k) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 340 200");
  svg.setAttribute("class", "defter-ego");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${k.ad} ve en güçlü bağları`);
  const yap = (ad, ozellik, metin) => {
    const n = document.createElementNS(ns, ad);
    for (const [a, d] of Object.entries(ozellik)) n.setAttribute(a, d);
    if (metin) n.textContent = metin;
    svg.append(n);
    return n;
  };
  const dugumler = egoDugumleri(k.baglar, 6);
  for (const d of dugumler) yap("line", { x1: 170, y1: 100, x2: d.x, y2: d.y, class: d.aday ? "aday" : "" });
  for (const d of dugumler) {
    yap("circle", { cx: d.x, cy: d.y, r: 6 });
    yap("text", { x: d.x, y: d.y < 100 ? d.y - 11 : d.y + 19 }, d.ad);
    yap("text", { x: Math.round((170 + d.x) / 2), y: Math.round((100 + d.y) / 2) - 4, class: "iliski" }, d.etiket);
  }
  yap("circle", { cx: 170, cy: 100, r: 9, class: "merkez" });
  yap("text", { x: 170, y: 84, class: "merkez-ad" }, k.tr && k.tr !== k.ad ? k.tr : k.ad);
  return svg;
}

/* ---------- eylemler ---------- */
async function eylem(is_, yenile = true) {
  const hedefDurum = () => (el("defterForm").open ? el("defterFormDurum") : el("defterDurum"));
  hedefDurum().textContent = "Kaydediliyor…";
  try {
    await is_();
    hedefDurum().textContent = "";
    el("defterDurum").textContent = "Kaydedildi.";
    if (yenile) {
      await yukle();
      if (el("defterKart").open) await kartYukle();
    }
    return true;
  } catch (e) {
    hedefDurum().textContent = "Kaydedilemedi: " + e.message;
    return false;
  }
}

function takmaAdKarari(o, karar) {
  return eylem(() => istek("/takma-ad", {
    method: "POST", body: JSON.stringify({ asil_kimlik: o.asil_kimlik, takma_kimlik: o.takma_kimlik, karar }),
  }));
}

function hitapKarari(h, hitap, grup) {
  // İstek sürerken ikinci dokunuş ikinci kararı göndermesin.
  for (const b of grup.querySelectorAll("button")) b.disabled = true;
  return eylem(() => istek("/hitap", {
    method: "POST", body: JSON.stringify({ konusan: h.ko, muhatap: h.mu, hitap, ilk_bolum: 1 }),
  })).then((tamam) => {
    // Başarıda kart yeniden çizilir; hatada düğmeler yeniden denenebilir kalsın.
    if (!tamam) for (const b of grup.querySelectorAll("button")) b.disabled = false;
    return tamam;
  });
}

function bagKaldir(b) {
  return eylem(() => istek("/bag", {
    method: "DELETE",
    body: JSON.stringify({ kaynak: b.kaynak_kimlik, iliski: b.iliski, hedef: b.hedef_kimlik }),
  }));
}

/* ---------- formlar ---------- */
const TUR_ADI = { ani: "Anı", efsun: "Efsun", nitelik: "Nitelik", golge: "Gölge", yanki: "Yankı",
                  yaratik: "Yaratık", alan: "Rün alanı" };

function formAc({ baslik, alanlar, kaydet, kaldir = null, ek = null, not = true }) {
  p.form = { kaydet, kaldir };
  el("defterForm-baslik").textContent = baslik;
  const kap = el("defterFormAlanlar");
  kap.replaceChildren(...alanlar.map((a) => {
    const lbl = oge("label", "terim-alan");
    lbl.append(oge("span", "terim-etiket", a.etiket));
    let girdi;
    if (a.tip === "secim") {
      girdi = document.createElement("select");
      for (const s of a.secenekler) {
        const o = document.createElement("option");
        o.value = typeof s === "string" ? s : s.deger;
        o.textContent = typeof s === "string" ? alanEtiketi(s) : s.etiket;
        girdi.append(o);
      }
    } else if (a.tip === "uzun") {
      girdi = document.createElement("textarea");
      girdi.rows = 3;
    } else {
      girdi = document.createElement("input");
      girdi.type = a.tip === "sayi" ? "number" : "text";
      if (a.tip === "sayi") { girdi.min = "0"; girdi.inputMode = "numeric"; }
      girdi.autocomplete = "off";
    }
    girdi.name = a.ad;
    girdi.value = a.deger ?? "";
    lbl.append(girdi);
    return lbl;
  }));
  el("defterFormEk").replaceChildren(...(ek || []));
  el("defterFormDurum").textContent = "";
  el("defterFormKaldir").hidden = !kaldir;
  el("defterFormNot").hidden = !not;
  diyalogAc("defterForm");
  kap.querySelector("input, select, textarea")?.focus();
}

function formDegerleri() {
  const out = {};
  for (const g of el("defterFormAlanlar").querySelectorAll("[name]")) out[g.name] = g.value;
  return out;
}

function kayitFormuAc(tur, sahip, mevcut = null) {
  // Listeden eklemede sahibi seçilir (karttan eklemede kartın kişisidir).
  const sahipSec = sahip == null && !["yaratik", "efsun"].includes(tur);
  const sahipAlani = sahipSec ? [{
    ad: "sahip", etiket: "Sahibi", tip: "secim",
    secenekler: (p.veri?.kisiler || []).slice(0, 120).map((x) => ({ deger: x.ad, etiket: x.tr && x.tr !== x.ad ? `${x.tr} (${x.ad})` : x.ad })),
  }] : [];
  const alanlar = [...sahipAlani, ...kayitFormu(tur).map((a) => ({
    ...a,
    deger: !mevcut ? "" : a.ad === "ad" ? mevcut.ad : a.ad === "ilk_bolum" ? (mevcut.ilk_bolum ?? "")
      : a.ad === "deger" ? mevcut.deger : (mevcut.alanlar || {})[a.ad] ?? "",
  }))];
  const ek = [];
  if (mevcut && mevcut.tur === "ani") {
    ek.push(oge("p", "terim-etiket defter-form-bolum", "Efsunlar"));
    for (const e of mevcut.efsunlar || []) {
      const b = dugme("", "defter-efsun-satir", () => kayitFormuAc("efsun", mevcut.ad, e));
      b.append(oge("b", null, e.tr && e.tr !== e.ad ? e.tr : e.ad), oge("small", null, e.ad));
      if (e.alanlar && e.alanlar.aciklama) b.append(oge("span", null, e.alanlar.aciklama));
      ek.push(b);
    }
    ek.push(dugme("+ efsun ekle", "defter-cizgili", () => kayitFormuAc("efsun", mevcut.ad)));
  }
  if (mevcut && mevcut.kanit) {
    ek.push(oge("p", "terim-etiket defter-form-bolum", "Rün mesajı · köken"),
      oge("p", "defter-kanit", mevcut.kanit));
  }
  if (mevcut && !mevcut.kimlik && mevcut.tur !== "alan") {
    ek.push(dugme("Sözlüğe ekle (karşılığını sabitle)", "pill", () => sozlugeEkleFormu(mevcut.ad, null)));
  }
  const baslik = mevcut ? (mevcut.tr && mevcut.tr !== mevcut.ad ? mevcut.tr : mevcut.ad) : `${TUR_ADI[tur]} ekle`;
  formAc({
    baslik: tur === "efsun" && sahip ? `${baslik} · ${sahip}` : baslik,
    alanlar,
    ek,
    kaydet: async (d) => {
      const kayit = formdanKayit(tur, d, sahipSec ? d.sahip : (sahip || ""));
      await istek("/kayit", { method: "POST", body: JSON.stringify({ kayit, yerine: mevcut?.anahtar || null }) });
    },
    kaldir: mevcut && mevcut.anahtar
      ? () => istek("/kayit", { method: "DELETE", body: JSON.stringify({ anahtar: mevcut.anahtar }) })
      : null,
  });
}

function bagFormu() {
  const k = p.kart;
  const kisiler = [...(p.veri?.kisiler || []), ...(p.veri?.gruplar || [])]
    .filter((x) => !String(x.kimlik).startsWith("ad:") && x.kimlik !== k.kimlik);
  formAc({
    baslik: `${k.tr && k.tr !== k.ad ? k.tr : k.ad} · bağ ekle`,
    alanlar: [
      { ad: "iliski", etiket: "İlişki", tip: "secim",
        secenekler: Object.entries(p.veri?.iliskiler || {}).map(([deger, etiket]) => ({ deger, etiket })) },
      { ad: "yon", etiket: "Yön", tip: "secim", secenekler: [
        { deger: "giden", etiket: `${k.ad}’ın … (ör. öğretmeni X)` },
        { deger: "gelen", etiket: `X’in … ${k.ad}` }] },
      { ad: "hedef", etiket: "Kişi ya da grup", tip: "secim",
        secenekler: kisiler.map((x) => ({ deger: x.kimlik, etiket: x.tr && x.tr !== x.ad ? `${x.tr} (${x.ad})` : x.ad })) },
      { ad: "ilk_bolum", etiket: "İlk bölüm (boş = okuma konumun)", tip: "sayi" },
    ],
    kaydet: async (d) => {
      const bolum = String(d.ilk_bolum || "").trim();
      const govde = d.yon === "gelen"
        ? { kaynak: d.hedef, iliski: d.iliski, hedef: k.kimlik }
        : { kaynak: k.kimlik, iliski: d.iliski, hedef: d.hedef };
      if (bolum) govde.ilk_bolum = Number(bolum);
      await istek("/bag", { method: "POST", body: JSON.stringify(govde) });
    },
  });
}

function sozlugeEkleFormu(ad, tur) {
  formAc({
    baslik: "Sözlüğe ekle",
    alanlar: [
      { ad: "source", etiket: "Kaynak (İngilizce)", tip: "metin", deger: ad },
      { ad: "target", etiket: "Karşılık (boş = İngilizce kalsın)", tip: "metin", deger: "" },
    ],
    not: false,
    kaydet: async (d) => {
      const source = (d.source || "").trim();
      if (!source) throw new Error("Kaynak boş olamaz");
      const res = await fetchWithTimeout(`/api/book/${encodeURIComponent(p.slug)}/glossary`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, target: (d.target || "").trim() || source, ...(tur ? { tur } : {}) }),
      }, ZAMAN_ASIMI_MS);
      if (!res.ok) throw new Error(`sunucu ${res.status}`);
    },
  });
}

export function kur() {
  el("defterBackBtn").addEventListener("click", () => history.back());
  el("defterSinirBtn").addEventListener("click", () => { p.tum = !p.tum; yukle(); });
  el("defterAra").addEventListener("input", (e) => { p.sorgu = e.target.value; ciz(); });
  el("defterEkleBtn").addEventListener("click", () => {
    const sekme = SEKMELER.find((s) => s.anahtar === p.sekme);
    if (sekme && sekme.tur) kayitFormuAc(sekme.tur, sekme.tur === "yaratik" ? "" : null);
  });
  el("defterKartKapat").addEventListener("click", () => diyalogKapat("defterKart"));
  el("defterFormKapat").addEventListener("click", () => diyalogKapat("defterForm"));
  el("defterFormVazgec").addEventListener("click", () => diyalogKapat("defterForm"));
  el("defterFormIc").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!p.form) return;
    let degerler;
    try {
      degerler = formDegerleri();
    } catch (err) {
      el("defterFormDurum").textContent = err.message;
      return;
    }
    el("defterFormKaydet").disabled = true;
    const tamam = await eylem(() => p.form.kaydet(degerler));
    el("defterFormKaydet").disabled = false;
    if (tamam) diyalogKapat("defterForm");
  });
  el("defterFormKaldir").addEventListener("click", async () => {
    if (!p.form || !p.form.kaldir) return;
    if (await eylem(p.form.kaldir)) diyalogKapat("defterForm");
  });
}
