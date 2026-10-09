/* Sözlük TÜRLERİ: kitaba özel tür listesi (2026-10-09, kullanıcı kararı).

   Liste sunucudan gelir (`GET /glossary` yanıtındaki `turler`): hazır türler +
   bu kitaba eklenen türler. Hazır türler de bu kitapta yeniden adlandırılabilir ya da
   silinebilir; KOD değişmez, kayıtlar koda bağlıdır. Tür silinince o türdeki kayıtlar
   silinmez, yalnız türleri boşalır. Tür çeviriyi etkilemez (prompt'a girmez).

   Bu modül `sozluk.js`i İÇE AKTARMAZ (döngü olmasın): yazma uçlarını kendisi çağırır. */

import { bildir } from "./bildirim.js";
import { durum } from "./durum.js";
import { el } from "./temel.js";

const VARSAYILAN = [
  ["kisi", "Kişi"], ["yer", "Yer"], ["orgut", "Örgüt"], ["rutbe", "Rütbe"],
  ["yetenek", "Yetenek"], ["nesne", "Nesne"], ["diger", "Diğer"],
].map(([kod, ad]) => ({ kod, ad, ozel: false }));

export let glossTurler = VARSAYILAN;

export function turAdi(kod) {
  const t = glossTurler.find((x) => x.kod === kod);
  return t ? t.ad : kod;
}

/* Sunucu yanıtındaki listeyi al ve iki seçim kutusunu (süzgeç + panel) yeniden çiz.
   Seçili değer korunur; listede olmayan (silinmiş) değer "Belirtilmedi"ye düşer. */
export function turleriAyarla(liste) {
  if (Array.isArray(liste)) glossTurler = liste;
  secimiCiz(el("glossTurSuz"), "Hepsi");
  secimiCiz(el("terimTur"), "Belirtilmedi");
  yoneticiyiCiz();
}

function secimiCiz(sec, bosEtiket) {
  if (!sec) return;
  const secili = sec.value;
  sec.replaceChildren(new Option(bosEtiket, ""));
  for (const t of glossTurler) sec.appendChild(new Option(t.ad, t.kod));
  sec.value = glossTurler.some((t) => t.kod === secili) ? secili : "";
}

async function istek(yontem, govde, sorgu = "") {
  const slug = durum.currentBookSlug;
  const ctrl = new AbortController();
  const zaman = setTimeout(() => ctrl.abort(), 15000);
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/glossary/turler${sorgu}`, {
      method: yontem,
      headers: govde ? { "Content-Type": "application/json" } : {},
      body: govde ? JSON.stringify(govde) : undefined,
      signal: ctrl.signal,
    });
    const veri = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof veri.detail === "string" ? veri.detail : "sunucu " + res.status);
    return veri;
  } finally {
    clearTimeout(zaman);
  }
}

function durumYaz(metin) {
  const p = el("terimTurDurum");
  if (p) p.textContent = metin;
}

export async function turEkle(ad) {
  try {
    const veri = await istek("POST", { ad });
    turleriAyarla(veri.turler);
    el("terimTur").value = veri.kod; // yeni tür panelde hemen seçili olur
    el("terimTur").dispatchEvent(new Event("change"));
    durumYaz(`"${turAdi(veri.kod)}" türü eklendi. Kaydet'e basınca bu kayda atanır.`);
    return veri.kod;
  } catch (err) {
    durumYaz("Tür eklenemedi: " + err.message);
    return null;
  }
}

async function turAdlandir(kod, ad) {
  try {
    turleriAyarla((await istek("PUT", { kod, ad })).turler);
    durumYaz(`Tür adı "${ad}" oldu.`);
  } catch (err) {
    durumYaz("Ad değiştirilemedi: " + err.message);
  }
}

async function turSil(kod) {
  const ad = turAdi(kod);
  if (!confirm(`"${ad}" türü bu kitaptan silinsin mi? Bu türdeki kayıtlar silinmez, yalnız türleri boşalır.`)) return;
  try {
    const veri = await istek("DELETE", null, `?kod=${encodeURIComponent(kod)}`);
    turleriAyarla(veri.turler);
    durumYaz(`"${ad}" silindi; ${veri.bosalan} kaydın türü boşaldı.`);
    bildir(`"${ad}" türü silindi.`);
    document.dispatchEvent(new CustomEvent("sozluk-turler-degisti"));
  } catch (err) {
    durumYaz("Silinemedi: " + err.message);
  }
}

// TÜRLERİ YÖNET: her tür için ad kutusu + Kaydet + Sil.
function yoneticiyiCiz() {
  const kutu = el("terimTurListe");
  if (!kutu) return;
  kutu.replaceChildren();
  for (const t of glossTurler) {
    const satir = document.createElement("div");
    satir.className = "terim-tur-satir";
    const ad = document.createElement("input");
    ad.type = "text";
    ad.value = t.ad;
    ad.maxLength = 30;
    ad.setAttribute("aria-label", `${t.ad} türünün adı`);
    const kaydet = document.createElement("button");
    kaydet.type = "button";
    kaydet.className = "pill";
    kaydet.textContent = "Adı kaydet";
    kaydet.addEventListener("click", () => {
      const yeni = ad.value.trim();
      if (yeni && yeni !== t.ad) turAdlandir(t.kod, yeni);
    });
    const sil = document.createElement("button");
    sil.type = "button";
    sil.className = "pill terim-sil";
    sil.textContent = "Sil";
    sil.setAttribute("aria-label", `${t.ad} türünü sil`);
    sil.addEventListener("click", () => turSil(t.kod));
    satir.append(ad, kaydet, sil);
    kutu.appendChild(satir);
  }
}

export function turYoneticisiniBagla() {
  el("terimTurEkle")?.addEventListener("click", async () => {
    const alan = el("terimTurYeni");
    const ad = alan.value.trim();
    if (!ad) {
      durumYaz("Önce yeni türün adını yaz.");
      alan.focus();
      return;
    }
    if (await turEkle(ad)) alan.value = "";
  });
  el("terimTurYeni")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    el("terimTurEkle").click();
  });
}
