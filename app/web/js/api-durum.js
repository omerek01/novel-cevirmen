/* API durum paneli: beş Gemini anahtarının son gözlemi, bugünkü istekler ve
   zincirin NEDEN aşağı indiği. Ayrıca okuyucu künyesindeki "neden bu model?"
   satırı.

   Panel yalnız sunucunun KAYDINI okur (`/api/settings/api-*`): Google'a istek
   atmaz, kota harcamaz. "Anahtarları canlı dene" düğmesi BİLEREK yok. Durumu
   normal çeviriler günceller; kota tüketen bir düğme eklenirse otomatik
   yenilemeden tamamen ayrı tutulmalı ve tüketimi açıkça yazmalı.

   Yenileme kuralları (plan):
     * yalnız panel GÖRÜNÜRKEN 15 sn'de bir; sekme ya da görünüm gizlenince durur;
     * istekler üst üste binmez (uçuşta olan varken yenisi atılmaz);
     * bağlantı koparsa eski veri zamanıyla kalır ve BAYAT diye işaretlenir.

   Panel bir GÖRÜNÜMDÜR, modal değil: ayarlar sheet'i kapanır, panel açılır, geri
   düğmesi ayarlara döner — iç içe modal açılmaz. */

import { diyalogKapat } from "./diyalog.js";
import { views } from "./durum.js";
import { navigate, showView } from "./gezinme.js";
import { fetchWithTimeout } from "./sozluk.js";
import { el } from "./temel.js";
import {
  YENILEME_MS,
  baglantiDurumu,
  bolumEtiketi,
  gecisNedeni,
  isaret,
  kalanSure,
  kisaModel,
  sayfalariBirlestir,
  tarihSaat,
} from "./api-durum-yardimci.js";

const ZAMAN_ASIMI_MS = 8000;
const SAYFA = 20;

const p = {
  zamanlayici: null,
  ucusta: false,
  veri: null,
  gecisler: [],
  sonraki: null,
  eskiYuklendi: false,
  sonBasari: 0, // Date.now() — son BAŞARILI yenileme
  sonHata: 0,
};

async function jsonAl(yol) {
  const res = await fetchWithTimeout(yol, { cache: "no-store" }, ZAMAN_ASIMI_MS);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function panelGorunurMu() {
  return !!views.apidurum && !views.apidurum.hidden && document.visibilityState === "visible";
}

function durdur() {
  clearTimeout(p.zamanlayici);
  p.zamanlayici = null;
}

function zamanla() {
  durdur();
  if (panelGorunurMu()) p.zamanlayici = setTimeout(yenile, YENILEME_MS);
}

/** Ayarlar panelinden: sheet'i kapat, paneli yeni bir geçmiş kaydıyla aç. */
export function apiDurumunuAc() {
  diyalogKapat("settingsPanel");
  navigate({ view: "apidurum" });
}

/** `applyNavState` çağırır (geri/ileri dahil). */
export function apiDurumGoster() {
  showView("apidurum");
  ciz();
  yenile();
}

/** Kaydı oku. "Yenile" düğmesi de bunu çağırır — yalnız OKUR. */
export async function yenile() {
  if (!panelGorunurMu()) {
    durdur(); // gizli panel için istek ATILMAZ
    return;
  }
  if (p.ucusta) return; // üst üste binme yok
  p.ucusta = true;
  durdur();
  ciz();
  try {
    const [veri, olay] = await Promise.all([
      jsonAl("/api/settings/api-status"),
      jsonAl(`/api/settings/api-events?limit=${SAYFA}`),
    ]);
    p.veri = veri;
    p.gecisler = p.eskiYuklendi
      ? sayfalariBirlestir(olay.olaylar || [], p.gecisler)
      : olay.olaylar || [];
    if (!p.eskiYuklendi) p.sonraki = olay.sonraki;
    p.sonBasari = Date.now();
  } catch {
    p.sonHata = Date.now(); // eski veri SİLİNMEZ; bağlantı satırı bayat der
  } finally {
    p.ucusta = false;
    ciz();
    zamanla();
  }
}

async function dahaEski() {
  if (!p.sonraki) return;
  const btn = el("apiDahaEski");
  btn.disabled = true;
  try {
    const olay = await jsonAl(
      `/api/settings/api-events?limit=${SAYFA}&cursor=${encodeURIComponent(p.sonraki)}`
    );
    p.gecisler = p.gecisler.concat(olay.olaylar || []);
    p.sonraki = olay.sonraki;
    p.eskiYuklendi = true;
  } catch {
    p.sonHata = Date.now();
  } finally {
    btn.disabled = false;
    ciz();
  }
}

/* ---------- çizim (yalnız textContent: kayıttaki metin HTML sayılmaz) ---------- */

function yap(etiket, sinif, metin) {
  const d = document.createElement(etiket);
  if (sinif) d.className = sinif;
  if (metin != null) d.textContent = metin;
  return d;
}

function ciz() {
  const baglanti = el("apiBaglanti");
  if (!baglanti) return;
  const b = baglantiDurumu({ sonBasari: p.sonBasari, sonHata: p.sonHata, simdiMs: Date.now() });
  baglanti.textContent = p.ucusta && !p.veri ? "Yükleniyor…" : b.metin;
  baglanti.classList.toggle("api-bayat", b.bayat);
  el("apiYenile").disabled = p.ucusta;
  ozetCiz();
  kartlariCiz();
  gecisleriCiz();
}

function ozetCiz() {
  const kutu = el("apiOzet");
  kutu.replaceChildren();
  const v = p.veri;
  if (!v) return;
  const simdi = Date.now() / 1000;
  const satir = (ad, deger) => {
    const dt = yap("dt", null, ad);
    const dd = yap("dd", null, deger);
    kutu.append(dt, dd);
  };
  satir("Tercih edilen model", kisaModel(v.tercih));
  satir("Yedek sırası", v.zincir.map(kisaModel).join(" → "));
  satir("Rotasyon", v.rotasyon);
  satir(
    `${kisaModel(v.tercih)} soğumada`,
    `${v.sogumada} / ${v.anahtar_sayisi} anahtar` +
      (v.sogumada < v.anahtar_sayisi ? " (kalanların çalışacağı garanti değil)" : "")
  );
  const t = v.bugun_toplam || {};
  satir(
    "Bugün (kota günü)",
    `${t.deneme || 0} istek · ${t.basari || 0} başarı · ${t.hata || 0} hata`
  );
  satir(
    "Günlük kota sıfırlanır",
    `${tarihSaat(v.sifirlama)} TSİ (Pasifik gece yarısı, ${kalanSure(v.sifirlama, simdi)} sonra)`
  );
  satir("Kayıt başlangıcı", `${tarihSaat(v.kayit_baslangici)} (öncesi bilinmiyor)`);
  const not = el("apiNot");
  not.textContent = v.claude_secili
    ? "Claude seçili: aşağıdaki Gemini havuzu şu an çeviride KULLANILMIYOR."
    : "";
  not.hidden = !v.claude_secili;
}

function modelSatiri(m, simdi, ayrintili) {
  const kutu = yap("div", `api-model api-ton-${m.ton}`);
  const baslik = yap("div", "api-model-baslik");
  baslik.append(
    yap("span", "api-model-ad", kisaModel(m.model)),
    yap("span", "api-rozet", `${isaret(m.ton)} ${m.etiket}`)
  );
  kutu.appendChild(baslik);
  const bilgi = [];
  if (m.son_deneme) bilgi.push(`Son gözlem ${tarihSaat(m.son_deneme)}`);
  if (m.son_basari) bilgi.push(`son başarı ${tarihSaat(m.son_basari)}`);
  const g = m.bugun || {};
  if (ayrintili || g.deneme) {
    bilgi.push(`bugün ${g.deneme} istek · ${g.basari} başarı · ${g.hata} hata`);
  }
  if (bilgi.length) kutu.appendChild(yap("p", "api-model-bilgi", bilgi.join(" · ")));
  if (m.hata_etiketi && m.durum !== "basarili" && m.durum !== "gozlenmedi") {
    let metin = `Son hata ${tarihSaat(m.son_hata)}: ${m.hata_etiketi}`;
    if (m.http_kodu) metin += ` (HTTP ${m.http_kodu})`;
    if (m.kota_sinir) metin += `, bildirilen sınır ${m.kota_sinir}`;
    kutu.appendChild(yap("p", "api-model-bilgi", metin));
  }
  if (m.soguma_bitis) {
    kutu.appendChild(yap(
      "p",
      "api-model-bilgi api-soguma",
      `Soğumada: ${tarihSaat(m.soguma_bitis)} TSİ'ye kadar (${kalanSure(m.soguma_bitis, simdi)})`
    ));
  }
  return kutu;
}

function kartlariCiz() {
  const kutu = el("apiKartlar");
  kutu.replaceChildren();
  const v = p.veri;
  if (!v) return;
  if (!v.anahtarlar.length) {
    kutu.appendChild(yap("p", "gloss-hint", "Sunucuda Gemini anahtarı tanımlı değil."));
    return;
  }
  const simdi = Date.now() / 1000;
  for (const a of v.anahtarlar) {
    const kart = yap("article", "api-kart");
    kart.appendChild(yap("h3", "api-kart-baslik", a.etiket));
    const [ilk, ...yedekler] = a.modeller;
    if (ilk) kart.appendChild(modelSatiri(ilk, simdi, true));
    if (yedekler.length) {
      const ayrinti = yap("details", "api-yedekler");
      ayrinti.appendChild(yap("summary", "api-yedek-ozet", "Yedek modeller"));
      for (const m of yedekler) ayrinti.appendChild(modelSatiri(m, simdi, false));
      kart.appendChild(ayrinti);
    }
    kutu.appendChild(kart);
  }
}

function gecisleriCiz() {
  const liste = el("apiGecisler");
  liste.replaceChildren();
  el("apiDahaEski").hidden = !p.sonraki;
  if (!p.veri) return;
  if (!p.gecisler.length) {
    liste.appendChild(yap(
      "li", "gloss-hint api-bos",
      "Kayıt başladıktan sonra tercih edilen modelden hiç inilmedi."
    ));
    return;
  }
  for (const o of p.gecisler) {
    const li = yap("li", "api-gecis");
    const ust = [tarihSaat(o.zaman), o.amac_etiketi, bolumEtiketi(o)].filter(Boolean);
    li.appendChild(yap("div", "api-gecis-ust", ust.join(" · ")));
    const hedef = o.tur === "tukendi" ? "çeviri yapılamadı" : kisaModel(o.hedef);
    li.appendChild(yap(
      "div", "api-gecis-yon" + (o.tur === "tukendi" ? " api-ton-hata" : ""),
      `${kisaModel(o.model)} → ${hedef}`
    ));
    const neden = gecisNedeni(o);
    if (neden) li.appendChild(yap("p", "api-model-bilgi", `Neden: ${neden}`));
    if (o.denenen && o.denenen.length) {
      li.appendChild(yap(
        "p", "api-model-bilgi",
        `Denenen anahtarlar (o anki sırayla): ${o.denenen.join(", ")}`
      ));
    }
    liste.appendChild(li);
  }
}

/* ---------- künye: "neden bu model?" ----------
   Rozet açılınca BİR kez sorulur (her bölüm için değil — okurken rozetlerin çoğu
   hiç açılmaz). Tercih edilen modelle çevrilmiş bölümde satır hiç görünmez. */
export function modelNedeniniBagla(kutu, govde, url) {
  if (!url || !/^https?:\/\//.test(url)) return;
  const satir = yap("div", "gloss-hint kunye-satir kunye-neden");
  satir.hidden = true;
  govde.appendChild(satir);
  let soruldu = false;
  kutu.addEventListener("toggle", async () => {
    if (!kutu.open || soruldu) return;
    soruldu = true;
    try {
      const v = await jsonAl(`/api/settings/api-neden?url=${encodeURIComponent(url)}`);
      if (v.durum === "tercih" || v.durum === "yok") return;
      satir.appendChild(yap("span", "kunye-neden-baslik", "Neden bu model? "));
      satir.appendChild(yap("span", null, v.aciklama));
      if (v.nedenler && v.nedenler.length) {
        const liste = yap("ul", "kunye-liste");
        for (const n of v.nedenler) liste.appendChild(yap("li", "kunye-ihlal-terim", n));
        satir.appendChild(liste);
      }
      satir.hidden = false;
    } catch {
      soruldu = false; // çevrimdışı: bir sonraki açılışta yeniden dene
    }
  });
}

/* Olay kayıtları: modül yüklenirken DEĞİL, `app.js` sırayla çağırınca. */
export function kur() {
  el("apiDurumAc").addEventListener("click", apiDurumunuAc);
  el("apiDurumGeri").addEventListener("click", () => history.back());
  el("apiYenile").addEventListener("click", () => yenile());
  el("apiDahaEski").addEventListener("click", dahaEski);

  // Panelden GERİ ile çıkış (panelin geri düğmesi ya da telefonun geri tuşu)
  // ayarlara döner. Bu dinleyici `gezinme`ninkinden ÖNCE kurulmalı (`app.js`
  // sırası): görünüm henüz değişmemişken panelin AÇIK olup olmadığını not eder.
  // Ölçüldü: Chromium pencere üzerindeki popstate dinleyicilerini capture/bubble
  // ayrımına bakmadan KAYIT SIRASIYLA çağırıyor, yani `{capture: true}` önce
  // koşmayı sağlamıyordu. Ayarlar olay dağıtımı BİTTİKTEN sonra açılır ve ölçüt
  // yeni geçmiş kaydıdır, DOM değil: okuyucuya dönüşte görünüm eşzamansız değişir.
  // Yalnız "şu an hangi görünüm" bakmak yetmezdi: panelden alt gezinmeyle çıkılıp
  // başka bir yerde geri basılınca ayarlar sebepsiz açılırdı.
  window.addEventListener("popstate", (e) => {
    const acikti = !!views.apidurum && !views.apidurum.hidden;
    if (!acikti) return;
    durdur();
    setTimeout(() => {
      const hedef = (e.state && e.state.view) || "library";
      if (hedef !== "apidurum") el("settingsBtn").click(); // TEK kaynak: ayarların açma yolu
    }, 0);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") durdur();
    else if (panelGorunurMu()) yenile();
  });
}
