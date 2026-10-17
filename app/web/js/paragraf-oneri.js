// Okuyucuda tek paragraf önerisi: üret → göster → "Kabul et" ya da "Atla" (Ö2/Ö4).
// Öneri kaydedilmez; kabul edilirse sunucu okurun gördüğü metinle karşılaştırıp yazar.
import { bildir } from "./bildirim.js";
import { bolumuTazele } from "./terim-paneli.js";
import {
  MODLAR, hataMetni, kaydetGovdesi, oneriDurumu, oneriGovdesi,
} from "./paragraf-oneri-yardimci.js";

async function postJson(yol, govde) {
  let res;
  try {
    res = await fetch(yol, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
    });
  } catch {
    return { ok: false, durum: 0 };
  }
  let veri = null;
  try { veri = await res.json(); } catch { /* gövdesiz hata */ }
  return { ok: res.ok, durum: res.status, veri };
}

/* Öneri düğmesi + panel. `mevcutGoster`: künyeden açılırken okur paragrafı görmüyor,
   karşılaştırma için şu anki metin de gösterilir. */
export function oneriDugmesi(url, sira, mod, { mevcutGoster = false } = {}) {
  const kap = document.createElement("div");
  kap.className = "paragraf-oneri";
  const dugme = document.createElement("button");
  dugme.type = "button";
  dugme.className = "pill paragraf-oneri-dugme";
  dugme.textContent = MODLAR[mod].dugme;
  const durum = document.createElement("p");
  durum.className = "gloss-hint paragraf-oneri-durum";
  durum.setAttribute("aria-live", "polite");
  kap.append(dugme, durum);

  dugme.addEventListener("click", async (e) => {
    e.stopPropagation(); // paragraf çift dokunuşu tetiklenmesin
    dugme.disabled = true;
    durum.textContent = MODLAR[mod].bekleme;
    kap.querySelector(".paragraf-oneri-panel")?.remove();
    const r = await postJson("/api/chapter/paragraf/oneri", oneriGovdesi(url, sira, mod));
    dugme.disabled = false;
    if (!r.ok) {
      durum.textContent = hataMetni(r.durum, r.veri?.detail);
      return;
    }
    const d = oneriDurumu(r.veri);
    if (d.tur === "yok") {
      durum.textContent = d.metin;
      return;
    }
    durum.textContent = d.not;
    kap.appendChild(oneriPaneli(url, sira, r.veri, mevcutGoster, () => {
      durum.textContent = "";
    }));
  });
  return kap;
}

function metinBlogu(etiket, metin, sinif) {
  const blok = document.createElement("div");
  blok.className = "paragraf-oneri-blok " + sinif;
  const e = document.createElement("span");
  e.className = "paragraf-oneri-etiket";
  e.textContent = etiket;
  const p = document.createElement("p");
  p.textContent = metin;
  blok.append(e, p);
  return blok;
}

function oneriPaneli(url, sira, oneri, mevcutGoster, kapandi) {
  const panel = document.createElement("div");
  panel.className = "paragraf-oneri-panel";
  if (mevcutGoster) panel.appendChild(metinBlogu("Şu an", oneri.mevcut, "mevcut"));
  panel.appendChild(metinBlogu("Öneri", oneri.aday, "aday"));
  const satir = document.createElement("div");
  satir.className = "paragraf-oneri-eylem";
  const kabul = document.createElement("button");
  kabul.type = "button";
  kabul.className = "pill paragraf-oneri-kabul";
  kabul.textContent = "Kabul et";
  const atla = document.createElement("button");
  atla.type = "button";
  atla.className = "pill";
  atla.textContent = "Atla";
  satir.append(kabul, atla);
  panel.appendChild(satir);
  atla.addEventListener("click", (e) => {
    e.stopPropagation();
    panel.remove();
    kapandi();
  });
  kabul.addEventListener("click", async (e) => {
    e.stopPropagation();
    kabul.disabled = atla.disabled = true;
    kabul.textContent = "Kaydediliyor…";
    const r = await postJson("/api/chapter/paragraf/kaydet", kaydetGovdesi(url, sira, oneri));
    if (!r.ok) {
      kabul.disabled = atla.disabled = false;
      kabul.textContent = "Kabul et";
      bildir(hataMetni(r.durum, r.veri?.detail));
      return;
    }
    bildir("Paragraf güncellendi (eski hâli arşivde).");
    await bolumuTazele(url);
  });
  return panel;
}
