/* Terim paneli: sözlük ayrıntısı + okurken terim düzenleme + etkilenen bölümler.

   Belge kararı (2026-09-16): üç ayrı yüzey TEK bileşendir. Sözlük listesinde bir
   satıra dokunmak da, okurken metin seçip "+ SÖZLÜĞE EKLE"ye basmak da aynı paneli
   açar; eski hızlı ekleme penceresi yalnız kaynak + karşılık taşıyordu — koşul,
   köken ve "bu düzeltme hangi bölümleri etkiler" sorusu okuma akışının DIŞINDA
   kalıyordu ve pratikte hiç sorulmuyordu.

   Üç kural load-bearing:
     * Türkçe metinden yapılan seçim İngilizce kaynağı OTOMATİK DOLDURMAZ. Hizalı
       paragraf bir paragraf eşlemesidir, kelime hizalaması değil; adaylar gösterilir,
       kullanıcı seçer.
     * Kayıt durumu dürüsttür: kuyruğa yazılan değer "Cihazda bekliyor" der, sunucu
       onaylayınca "Sunucuya kaydedildi" olur.
     * Yeniden çevrilen bölüm telefonun Service Worker önbelleğinde de tazelenir;
       yoksa kullanıcı düzeltilmiş bölümün ESKİ kopyasını okumaya devam ederdi. */

import { bildir } from "./bildirim.js";
import { purgeChapterFromSwCache, warmOffline } from "./cevrimdisi.js";
import { diyalogAc, diyalogAcikMi, diyalogKapat } from "./diyalog.js";
import { durum, views } from "./durum.js";
import {
  entryFor,
  fetchChapterData,
  renderHtmlContent,
  renderParagraphs,
} from "./okuyucu.js";
import {
  fetchGlossary,
  fetchWithTimeout,
  glossKosullarSonHal,
  glossRows,
  glossTermsSonHal,
  kokeneGit,
  kuyrukDinle,
  overlayGloss,
  saveTerm,
  terimDurumu,
  terimiSilGeriAlinabilir,
  yenidenSuz,
} from "./sozluk.js";
import { anahtarla } from "./sozluk-kuyruk.js";
import { adayTerimler, cumleBul, sonucEtiketi, trimSecim } from "./terim-yardimci.js";
import { el } from "./temel.js";

const PANEL = "terimPaneli";
const IS_YOKLAMA_MS = 3000;

/* Açık panelin bağlamı. `secim` yalnız okuyucudan açılınca dolar:
   { terim, kaynaktan, enParagraf, url, no }. */
let panel = null;
let durumDinleyici = null;

function yaz(id, metin) {
  const d = el(id);
  if (d) d.textContent = metin || "";
}

function kayitliAnahtar(terms, source) {
  const k = anahtarla(source);
  return Object.keys(terms).find((s) => anahtarla(s) === k);
}

function gorunenSozluk(slug) {
  return overlayGloss(slug, glossTermsSonHal, glossKosullarSonHal);
}

/* ---------- açma ---------- */

export async function terimPaneliAc({ slug, source = "", secim = null }) {
  if (!slug) return;
  panel = { slug, secim, kayitli: null, eskiKosul: "", ornek: null };
  formuSifirla();
  diyalogAc(PANEL);
  baglamiCiz();
  // Sözlük o kitap için hiç çekilmediyse (okuyucudan açılış) önce çekilir; çevrimdışı
  // ve önbelleksizse boş döner, panel yine çalışır (yazım kuyruğa gider).
  // Sözlük ekranı AYNI kitapla açıkken yeniden çekilmez: çevrimdışıyken boş yanıt
  // ekrandaki listenin tabanını silerdi.
  const listeHazir = !views.glossary.hidden && durum.currentBookSlug === slug;
  if (!listeHazir) await fetchGlossary(slug);
  if (secim && !secim.kaynaktan && !secim.enParagraf && secim.url && secim.idx != null) {
    await kaynagiYukle(secim);
  }
  if (!panel || panel.slug !== slug || !diyalogAcikMi(PANEL)) return;
  baglamiCiz();
  adaylariCiz();
  const baslangic = source || (secim && secim.kaynaktan ? secim.terim : "");
  if (baslangic) kaynagiSec(baslangic, { oner: !!secim });
  else el("terimKaynak").focus();
}

function formuSifirla() {
  for (const id of ["terimKaynak", "terimKarsilik", "terimKosul"]) el(id).value = "";
  el("terimAynen").checked = false;
  el("terimKarsilik").disabled = false;
  el("terimSil").hidden = true;
  el("terimSonrasi").hidden = true;
  el("terimBuBolum").hidden = true;
  el("terimEtki").hidden = true;
  el("terimEtki").replaceChildren();
  el("terimKoken").hidden = true;
  el("terimKoken").replaceChildren();
  yaz("terimDurum", "");
  yaz("terimPaneli-baslik", "TERİM");
  durumuBirak();
}

function baglamiCiz() {
  const s = panel.secim;
  el("terimBaglam").hidden = !s;
  if (!s) return;
  yaz("terimSecilen", s.terim);
  el("terimSecilenSatir").hidden = !!s.kaynaktan;
  yaz(
    "terimEnParagraf",
    s.enParagraf || "Bu paragrafın İngilizce kaynağı yok — kaynak terimi elle yaz."
  );
  el("terimAdayBaslik").hidden = !!s.kaynaktan;
}

/* Okuyucu hizalı kaynağı bölüm yüklenirken getirmemiş olabilir (eski önbellek
   girdisi); çift dokunmadaki `loadSourceForChapter` ile aynı uç. */
async function kaynagiYukle(secim) {
  yaz("terimEnParagraf", "İngilizce getiriliyor…");
  try {
    const res = await fetch(`/api/chapter?url=${encodeURIComponent(secim.url)}&source=1&track=0`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    const kaynak = data.source ? data.source.split(/\n\n+/).map((s) => s.trim()) : [];
    const entry = entryFor(secim.url);
    if (entry && kaynak.length) entry.source = kaynak;
    secim.enParagraf = kaynak[secim.idx] || "";
  } catch {
    secim.enParagraf = "";
  }
}

function adaylariCiz() {
  const kutu = el("terimAdaylar");
  kutu.replaceChildren();
  const s = panel.secim;
  if (!s || s.kaynaktan || !s.enParagraf) return;
  const { terms } = gorunenSozluk(panel.slug);
  for (const aday of adayTerimler(s.enParagraf, terms)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip terim-aday" + (aday.kayitli ? " terim-aday-kayitli" : "");
    b.textContent = aday.kayitli ? `${aday.source} → ${aday.target}` : aday.source;
    b.addEventListener("click", () => kaynagiSec(aday.source, { oner: !aday.kayitli }));
    kutu.appendChild(b);
  }
}

/* Kaynak terim belirlendi: kayıtlıysa kaydı yükle, değilse (isteğe bağlı) öner. */
function kaynagiSec(kaynak, { oner = false } = {}) {
  kaynak = trimSecim(kaynak);
  el("terimKaynak").value = kaynak;
  if (!kaynak) return;
  const { terms, kosullar } = gorunenSozluk(panel.slug);
  const kayitli = kayitliAnahtar(terms, kaynak);
  panel.kayitli = kayitli || null;
  const s = panel.secim;
  panel.ornek =
    s && s.enParagraf ? { kaynak_cumle: cumleBul(s.enParagraf, kaynak), bolum: s.no } : null;
  if (kayitli) {
    el("terimKaynak").value = kayitli;
    const hedef = terms[kayitli];
    el("terimAynen").checked = anahtarla(hedef) === anahtarla(kayitli);
    el("terimKarsilik").value = hedef;
    el("terimKarsilik").disabled = el("terimAynen").checked;
    panel.eskiKosul = kosullar[kayitli] || "";
    el("terimKosul").value = panel.eskiKosul;
    el("terimSil").hidden = false;
    el("terimSonrasi").hidden = false;
    yaz("terimPaneli-baslik", kayitli);
    kokeniCiz(kayitli);
    durumuIzle(kayitli);
  } else {
    panel.eskiKosul = "";
    el("terimSil").hidden = true;
    el("terimSonrasi").hidden = true;
    yaz("terimPaneli-baslik", "YENİ TERİM");
    kokeniCiz(null);
    yaz("terimDurum", "Sözlükte yok — kaydedince eklenir.");
    if (oner) oneriIste();
  }
  bolumDugmesiniAyarla();
}

function kokeniCiz(kaynak) {
  const kutu = el("terimKoken");
  kutu.replaceChildren();
  const kok = (kaynak && glossRows[kaynak]) || {};
  const cumle = kok.kaynak_cumle || (panel.ornek && panel.ornek.kaynak_cumle);
  const no = kok.first_chapter || (panel.ornek && panel.ornek.bolum);
  kutu.hidden = !(cumle || no || kok.origin);
  if (kutu.hidden) return;
  const ust = document.createElement("p");
  ust.className = "terim-etiket";
  const kim = { auto: "otomatik eklendi", manual: "elle eklendi", import: "yedekten geldi" }[kok.origin];
  ust.textContent = ["ÖRNEK / KÖKEN", kim].filter(Boolean).join(" · ");
  kutu.appendChild(ust);
  if (cumle) {
    const c = document.createElement("p");
    c.className = "terim-ornek-cumle";
    c.lang = "en";
    c.textContent = "“" + cumle + "”";
    kutu.appendChild(c);
  }
  if (no && kok.first_chapter && !panel.secim) {
    const git = document.createElement("button");
    git.type = "button";
    git.className = "pill";
    git.textContent = "BÖLÜM " + no + " — cümleye git";
    git.addEventListener("click", () => {
      diyalogKapat(PANEL);
      kokeneGit(no, kok.kaynak_cumle, kaynak, (glossRows[kaynak] || {}).target);
    });
    kutu.appendChild(git);
  }
}

/* ---------- öneri ---------- */

async function oneriIste() {
  const kaynak = el("terimKaynak").value.trim();
  if (!kaynak || !panel) return;
  const istek = panel;
  yaz("terimDurum", "Karşılık öneriliyor…");
  try {
    const res = await fetchWithTimeout(
      `/api/book/${encodeURIComponent(istek.slug)}/glossary/suggest`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: kaynak,
          context: (istek.secim && istek.secim.enParagraf) || "",
        }),
      },
      25000 // model çağrısı: sözlük yazımından uzun sürebilir
    );
    if (!res.ok) throw new Error("öneri alınamadı");
    const data = await res.json();
    if (panel !== istek || !diyalogAcikMi(PANEL) || el("terimKaynak").value.trim() !== kaynak) return;
    if (!el("terimKarsilik").value.trim()) {
      el("terimKarsilik").value = data.target || kaynak;
      if (data.is_character) {
        el("terimAynen").checked = true;
        el("terimKarsilik").disabled = true;
      }
    }
    yaz(
      "terimDurum",
      data.is_character
        ? "Öneri: karakter adı → İngilizce kalsın. Yanlışsa işareti kaldırıp karşılık yaz."
        : "Önerilen karşılık dolduruldu; kaydetmeden önce kontrol et."
    );
  } catch {
    if (panel !== istek || !diyalogAcikMi(PANEL)) return;
    yaz("terimDurum", "Öneri alınamadı (sunucu kapalı ya da modeller meşgul) — karşılığı elle yaz.");
  }
}

/* ---------- kaydetme / silme ---------- */

function kaydet() {
  if (!panel) return;
  const kaynak = trimSecim(el("terimKaynak").value);
  if (!kaynak) {
    yaz("terimDurum", "Kaynak terim gerekli.");
    el("terimKaynak").focus();
    return;
  }
  const { terms, kosullar } = gorunenSozluk(panel.slug);
  const kayitli = kayitliAnahtar(terms, kaynak);
  const ad = kayitli || kaynak;
  const hedef = el("terimAynen").checked ? ad : el("terimKarsilik").value.trim() || ad;
  const yeniKosul = el("terimKosul").value.trim();
  // Koşul YALNIZ değiştiyse gönderilir: undefined = sunucu mevcut koşulu korur.
  const eskiKosul = kayitli ? kosullar[kayitli] || "" : "";
  const kosul = yeniKosul !== eskiKosul ? yeniKosul : undefined;
  const ornek =
    !kayitli && panel.ornek && panel.ornek.kaynak_cumle ? panel.ornek : undefined;
  const { kalici } = saveTerm(panel.slug, ad, hedef, kosul, ornek);
  panel.kayitli = ad;
  panel.eskiKosul = yeniKosul;
  el("terimSil").hidden = false;
  el("terimSonrasi").hidden = false;
  yaz("terimPaneli-baslik", ad);
  bolumDugmesiniAyarla();
  if (!kalici) {
    yaz(
      "terimDurum",
      "Cihaza YAZILAMADI (depolama dolu ya da kapalı): kayıt yalnız bu oturumda bekliyor, gönderiliyor…"
    );
  }
  durumuIzle(ad);
}

function sil() {
  if (!panel || !panel.kayitli) return;
  const { slug, kayitli } = panel;
  diyalogKapat(PANEL);
  terimiSilGeriAlinabilir(slug, kayitli, { geriAlindi: yenidenSuz });
  yenidenSuz();
}

/* Kayıt durumu satırı: kuyruk olaylarıyla canlı. */
function durumuIzle(kaynak) {
  durumuBirak();
  const guncelle = () => {
    if (!panel) return;
    const d = terimDurumu(panel.slug, kaynak);
    if (!d) {
      yaz("terimDurum", "Sunucuya kaydedildi.");
      return;
    }
    const metin = {
      bekliyor: "Cihazda bekliyor — sunucuya ulaşınca kendiliğinden kaydedilecek.",
      bellekte: "KAYDEDİLMEDİ: cihaza yazılamadı; uygulamayı kapatırsan kaybolur.",
      hata: "Gönderilemedi — sözlük ekranındaki uyarıdan tekrar deneyebilirsin.",
      kaydedildi: "Sunucuya kaydedildi.",
    }[d.sinif];
    yaz("terimDurum", metin || d.etiket);
  };
  guncelle();
  durumDinleyici = kuyrukDinle(() => queueMicrotask(guncelle));
}

function durumuBirak() {
  if (durumDinleyici) durumDinleyici();
  durumDinleyici = null;
}

/* ---------- eski bölümlere uygulama ---------- */

function bolumDugmesiniAyarla() {
  const s = panel && panel.secim;
  const entry = s && s.url ? entryFor(s.url) : null;
  // Yalnız ÇEVRİLMİŞ metin bölümü: görsel sayfa ve çevrilmemiş bölüm yeniden
  // çevrilemez (uç da reddeder).
  el("terimBuBolum").hidden = !(panel && panel.kayitli && entry && entry.paras && entry.paras.length);
}

function buBolumdeUygula() {
  const s = panel && panel.secim;
  if (!s || !s.url) return;
  yenidenCevir(panel.slug, [s.url], el("terimEtki"));
}

async function etkiyiGoster() {
  if (!panel || !panel.kayitli) return;
  const { slug, kayitli } = panel;
  const kutu = el("terimEtki");
  kutu.hidden = false;
  kutu.replaceChildren();
  const bekle = document.createElement("p");
  bekle.className = "modal-hint";
  bekle.textContent = "Etkilenen bölümler aranıyor…";
  kutu.appendChild(bekle);
  let veri;
  try {
    const res = await fetch(
      `/api/book/${encodeURIComponent(slug)}/glossary/impact?source=${encodeURIComponent(kayitli)}`
    );
    if (!res.ok) throw new Error("sunucu " + res.status);
    veri = await res.json();
  } catch (err) {
    bekle.textContent = "Etkilenen bölümler alınamadı (" + err.message + ").";
    return;
  }
  if (panel === null || panel.slug !== slug || panel.kayitli !== kayitli) return;
  etkiListesiCiz(kutu, slug, veri);
}

function etkiListesiCiz(kutu, slug, veri) {
  kutu.replaceChildren();
  const [kapsanan, toplam] = veri.kapsama || [0, 0];
  const ozet = document.createElement("p");
  ozet.className = "modal-hint";
  ozet.textContent = veri.count
    ? `Terim çevrilmiş ${veri.count} bölümde geçiyor. Kayıt yeni çevrilecek bölümlerde zaten ` +
      "geçerli; eskilerde görünmesi için seçtiklerini yeniden çevir. Her bölüm bir çeviri isteği harcar."
    : kapsanan < toplam
      ? `Çevrilmiş bölümlerde bulunamadı (yalnız ${kapsanan}/${toplam} bölümün kaynak metni saklı — kesin değil).`
      : "Çevrilmiş hiçbir bölümde geçmiyor; yalnız yeni bölümleri etkiler.";
  kutu.appendChild(ozet);
  if (!veri.count) return;

  const liste = document.createElement("ul");
  liste.className = "terim-etki-liste";
  for (const b of veri.chapters) {
    const li = document.createElement("li");
    li.className = "terim-etki-satir";
    li.dataset.url = b.url;
    const etiket = document.createElement("label");
    etiket.className = "terim-etki-baslik";
    const kutucuk = document.createElement("input");
    kutucuk.type = "checkbox";
    kutucuk.checked = true;
    kutucuk.value = b.url;
    const ad = document.createElement("span");
    ad.textContent =
      (b.chapter_no != null ? `Bölüm ${b.chapter_no}` : "Bölüm") + (b.title ? " — " + b.title : "");
    etiket.append(kutucuk, ad);
    li.appendChild(etiket);
    if (b.ceviri_zamani) {
      const z = document.createElement("span");
      z.className = "terim-etki-zaman";
      z.textContent = "çeviri: " + new Date(b.ceviri_zamani * 1000).toLocaleDateString("tr-TR");
      li.appendChild(z);
    }
    for (const [alan, dil] of [["ornek_en", "en"], ["ornek_tr", "tr"]]) {
      if (!b[alan]) continue;
      const p = document.createElement("p");
      p.className = "terim-etki-ornek";
      p.lang = dil;
      p.textContent = b[alan];
      li.appendChild(p);
    }
    const sonuc = document.createElement("p");
    sonuc.className = "terim-etki-sonuc";
    sonuc.setAttribute("aria-live", "polite");
    li.appendChild(sonuc);
    liste.appendChild(li);
  }
  kutu.appendChild(liste);

  const eylem = document.createElement("div");
  eylem.className = "modal-actions terim-etki-eylem";
  const hepsi = document.createElement("button");
  hepsi.type = "button";
  hepsi.className = "pill";
  hepsi.textContent = "Seçimi tersine çevir";
  hepsi.addEventListener("click", () => {
    for (const k of liste.querySelectorAll("input[type=checkbox]")) k.checked = !k.checked;
  });
  const basla = document.createElement("button");
  basla.type = "button";
  basla.className = "next-btn";
  basla.textContent = "Seçilenleri yeniden çevir";
  basla.addEventListener("click", () => {
    const urls = [...liste.querySelectorAll("input[type=checkbox]:checked")].map((k) => k.value);
    if (!urls.length) return bildir("Bölüm seçilmedi.");
    basla.disabled = true;
    yenidenCevir(slug, urls, kutu).finally(() => (basla.disabled = false));
  });
  eylem.append(hepsi, basla);
  kutu.appendChild(eylem);
}

/* Yeniden çeviri işi: sunucuda arka planda koşar (panel kapansa da sürer). Her
   biten bölüm TELEFONDA da tazelenir: SW kopyası silinip yeniden çekilir, okuyucuda
   açıksa yerinde yeniden çizilir. */
export async function yenidenCevir(slug, urls, kutu) {
  let isId;
  try {
    const res = await fetch(`/api/book/${encodeURIComponent(slug)}/retranslate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
    });
    const veri = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(veri.detail || "sunucu " + res.status);
    isId = veri.job_id;
  } catch (err) {
    bildir("Yeniden çeviri başlatılamadı: " + err.message);
    return;
  }
  let ilerleme = kutu && kutu.querySelector(".terim-is-durum");
  if (kutu && !ilerleme) {
    ilerleme = document.createElement("p");
    ilerleme.className = "terim-is-durum";
    ilerleme.setAttribute("role", "status");
    kutu.hidden = false;
    kutu.appendChild(ilerleme);
  }
  const islenen = new Set();
  for (;;) {
    let is;
    try {
      const r = await fetch(`/api/bulk/${encodeURIComponent(isId)}`);
      if (!r.ok) throw new Error();
      is = await r.json();
    } catch {
      await new Promise((c) => setTimeout(c, IS_YOKLAMA_MS * 2));
      continue; // bağlantı koptu: iş sunucuda sürüyor, yoklamaya devam
    }
    if (ilerleme && ilerleme.isConnected) ilerleme.textContent = is.message || "";
    const sonuclar = (is.params && is.params.sonuclar) || {};
    for (const [url, sonuc] of Object.entries(sonuclar)) {
      if (islenen.has(url)) continue;
      islenen.add(url);
      const satir = kutu && kutu.querySelector(`li[data-url="${CSS.escape(url)}"] .terim-etki-sonuc`);
      if (satir) satir.textContent = sonucEtiketi(sonuc);
      if (sonuc.durum === "tamam") await bolumuTazele(url);
    }
    if (is.state !== "running" && is.state !== "queued") {
      bildir(is.message || "Yeniden çeviri bitti.");
      return is;
    }
    await new Promise((c) => setTimeout(c, IS_YOKLAMA_MS));
  }
}

/* Sunucuda yeniden çevrilmiş bölümü telefona indir. `refresh=1` KULLANILMAZ: o
   sunucuda İKİNCİ bir çeviri tetiklerdi. Önce SW kopyası silinir, sonra düz GET
   önbellek ıskası olarak ağa gider ve SW yenisini yazar. */
export async function bolumuTazele(url) {
  await purgeChapterFromSwCache(url);
  const entry = entryFor(url);
  if (!entry || !entry.el || views.reader.hidden) {
    await warmOffline(url);
    return;
  }
  try {
    const data = await fetchChapterData(url, false, false);
    const y = window.scrollY;
    if (data.content_type === "html") {
      entry.html = data.translation || "";
      renderHtmlContent(entry);
    } else {
      entry.paras = (data.translation || "").split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
      entry.source = data.source ? data.source.split(/\n\n+/).map((p) => p.trim()) : [];
      entry.glossaryLeaks = data.glossary_leaks || null;
      entry.ingilizceKalinti = data.ingilizce_kalinti || null;
      entry.model = data.model || entry.model;
      renderParagraphs(entry, "");
    }
    window.scrollTo(0, y); // okuma konumu korunur
  } catch {
    await warmOffline(url);
  }
}

/* ---------- olaylar ---------- */

export function kur() {
  el("terimKaydet").addEventListener("click", kaydet);
  el("terimSil").addEventListener("click", sil);
  el("terimOner").addEventListener("click", oneriIste);
  el("terimKapat").addEventListener("click", () => diyalogKapat(PANEL));
  el("terimBuBolum").addEventListener("click", buBolumdeUygula);
  el("terimEtkiBtn").addEventListener("click", etkiyiGoster);
  el("terimAynen").addEventListener("change", () => {
    const aynen = el("terimAynen").checked;
    el("terimKarsilik").disabled = aynen;
    if (aynen) el("terimKarsilik").value = el("terimKaynak").value.trim();
  });
  // Kaynak elle değiştirilince kayıt yeniden aranır (yazım varyantı dahil).
  el("terimKaynak").addEventListener("change", () => {
    if (panel) kaynagiSec(el("terimKaynak").value);
  });
  for (const id of ["terimKaynak", "terimKarsilik"]) {
    el(id).addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (id === "terimKaynak") kaynagiSec(el("terimKaynak").value);
      else kaydet();
    });
  }
  el(PANEL).addEventListener("close", () => {
    durumuBirak();
    panel = null;
    yenidenSuz(); // sözlük ekranı açıksa değişiklik listeye yansısın
  });
}
