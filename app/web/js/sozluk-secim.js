/* Okurken seçimden sözlüğe ekleme kısayolu. */

import { diyalogAc, diyalogAcikMi, diyalogKapat } from "./diyalog.js";
import { durum, views } from "./durum.js";
import { fetchGlossary, fetchWithTimeout, kuyruk, kuyrukDinle, saveTerm } from "./sozluk.js";
import { el } from "./temel.js";

/* ---------- seçimden sözlüğe ekleme ----------
   Okurken bir özel adı seçip doğrudan sözlüğe atmak için. Android'in KENDİ seçim
   menüsüne (Çevir/Kopyala/Paylaş) kendi eylemimizi EKLEYEMEYİZ — o tarayıcının
   menüsü, sayfaya kapalı. Bunun yerine seçim yapılınca kendi kayan düğmemizi
   gösteririz; native menü seçimin üstünde durduğu için düğme ALTA konumlanır. */

// Cümle seçilince düğme çıkmasın: sözlük TERİM eşlemesidir, cümle çevirisi değil.
export const SEL_GLOSS_MAX_WORDS = 8;
export let selGlossData = null; // aktif seçim (düğme görünürken)
// Düğmeye basılınca kullanılacak SON geçerli seçim. Ayrı tutulur: dokunma anında
// tarayıcı seçimi temizleyip `selectionchange` yayabiliyor, tek değişken olsaydı
// tıklama işlenmeden önce null'lanıp düğme sessizce hiçbir şey yapmazdı.
export let selGlossLast = null;
export let selGlossTimer = null;

/* `glossary.normalize_source`'un hafif JS eşi: çevresel noktalama kırpılır, İngilizce
   iyelik eki KORUNUR (kullanıcı ne eklediğini görsün, sunucu zaten köke indiriyor).
   Sunucudaki `set_term` normalize ETMEZ — kırpma burada olmazsa sözlükte
   "Silverwing Town." gibi noktalı anahtarlar birikir. */
export function trimSecim(text) {
  return (text || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[^\p{L}\p{N}]+/u, "")
    .replace(/[^\p{L}\p{N}'’]+$/u, "");
}

export function hideSelGloss() {
  selGlossData = null;
  const btn = el("selGlossBtn");
  if (btn) btn.hidden = true;
}

export function updateSelGloss() {
  const btn = el("selGlossBtn");
  if (!btn || views.reader.hidden) return hideSelGloss();
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return hideSelGloss();
  const range = sel.getRangeAt(0);
  const node = range.commonAncestorContainer;
  const host = node.nodeType === 1 ? node : node.parentElement;
  if (!host || !host.closest("#readerBody")) return hideSelGloss();

  const terim = trimSecim(sel.toString());
  if (!terim || terim.split(" ").length > SEL_GLOSS_MAX_WORDS) return hideSelGloss();

  // Sözlük eşlemesi kaynak(İngilizce) → karşılık(Türkçe). Seçimin İngilizce orijinal
  // bloğundan (`.source-line`) mı yoksa Türkçe paragraftan mı geldiği, modalda hangi
  // alanın dolacağını belirler.
  // Bağlam cümlesi öneriye gider: aynı sözcük bir kitapta kişi adı, başkasında yer
  // adı olabilir ("Rain"), sınıfı ancak cümle belli eder.
  selGlossData = {
    terim,
    kaynaktan: !!host.closest(".source-line"),
    baglam: (host.closest(".source-line, p") || host).textContent.slice(0, 600),
  };
  selGlossLast = selGlossData;

  btn.hidden = false; // ölçüden ÖNCE görünür olmalı, yoksa offset* 0 döner
  const yariGenislik = btn.offsetWidth / 2 || 60;
  const r = range.getBoundingClientRect();
  const x = Math.min(
    Math.max(r.left + r.width / 2, yariGenislik + 8),
    window.innerWidth - yariGenislik - 8
  );
  const altta = r.bottom + 8;
  const y =
    altta + btn.offsetHeight + 8 < window.innerHeight
      ? altta
      : r.top - btn.offsetHeight - 8; // ekranın dibinde seçim: üste al
  btn.style.left = x + "px";
  btn.style.top = Math.max(8, y) + "px";
}

export function openGlossQuick() {
  const secim = selGlossLast;
  if (!secim) return;
  hizliKaydiBirak();
  const { terim, kaynaktan } = secim;
  el("glossQuickSource").value = kaynaktan ? terim : "";
  el("glossQuickTarget").value = kaynaktan ? "" : terim;
  el("glossQuickHint").textContent = kaynaktan
    ? "Karakter adıysa İngilizce kalır, değilse Türkçe karşılığı yazılır. Sözlük YALNIZ bundan sonra çevrilecek bölümlerde geçerlidir."
    : "Türkçe metinden seçtin: bunu KARŞILIK alanına koydum, kaynak İngilizce terimi sen yaz. Sözlük yalnız bundan sonra çevrilecek bölümlerde geçerlidir.";
  el("glossQuickState").textContent = "";
  diyalogAc("glossQuickModal");
  hideSelGloss();
  window.getSelection()?.removeAllRanges();
  (kaynaktan ? el("glossQuickTarget") : el("glossQuickSource")).focus();
  if (kaynaktan) doldurOneri(secim);
}

/* Karşılığı kullanıcı yerine SİSTEM belirler: karakter adı İngilizce kalır, başka
   her özel ad Türkçe karşılığıyla girer — `pipeline._sozluge_isle`'ın otomatik
   davranışıyla aynı kural. Öneri yine de ONAYA sunulur: sözlük prompt'ta KURALdır,
   yanlış bir karşılık kitap boyunca birebir uygulanırdı. */
export async function doldurOneri(secim) {
  const { terim, baglam } = secim;
  if (!durum.currentBookSlug) return;
  // Zaten kayıtlıysa öneri istemeye gerek yok (kayıt INSERT OR REPLACE: kullanıcı
  // üzerine yazdığını bilerek yazsın). Çevrimdışıysa boş döner, akış sürer.
  const terms = await fetchGlossary(durum.currentBookSlug);
  if (!diyalogAcikMi("glossQuickModal")) return; // kullanıcı bu arada kapattı
  if (terms[terim] !== undefined) {
    if (!el("glossQuickTarget").value.trim()) el("glossQuickTarget").value = terms[terim];
    el("glossQuickState").textContent =
      `Zaten kayıtlı: ${terim} → ${terms[terim]} · kaydedersen değişir`;
    return;
  }
  el("glossQuickState").textContent = "Karşılık öneriliyor…";
  try {
    const res = await fetchWithTimeout(
      `/api/book/${encodeURIComponent(durum.currentBookSlug)}/glossary/suggest`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: terim, context: baglam || "" }),
      },
      25000 // model çağrısı: sözlük yazımından uzun sürebilir
    );
    if (!res.ok) throw new Error("öneri alınamadı");
    const data = await res.json();
    if (!diyalogAcikMi("glossQuickModal")) return;
    if (!el("glossQuickTarget").value.trim()) el("glossQuickTarget").value = data.target || terim;
    el("glossQuickState").textContent = data.is_character
      ? "Karakter adı → İngilizce kalacak. Yanlışsa karşılığı sen yaz."
      : "Önerilen karşılık dolduruldu; istersen değiştir.";
  } catch {
    if (!diyalogAcikMi("glossQuickModal")) return;
    el("glossQuickState").textContent =
      "Öneri alınamadı (sunucu kapalı ya da kota dolu olabilir) — karşılığı elle yaz.";
  }
}

export function saveGlossQuick() {
  const source = trimSecim(el("glossQuickSource").value);
  if (!source) {
    el("glossQuickState").textContent = "Kaynak terim gerekli.";
    el("glossQuickSource").focus();
    return;
  }
  if (!durum.currentBookSlug) {
    el("glossQuickState").textContent = "Kitap bilinmiyor — sözlük ekranından ekle.";
    return;
  }
  const target = el("glossQuickTarget").value.trim() || source;
  const { id, kalici } = saveTerm(durum.currentBookSlug, source, target);
  selGlossLast = null;
  hizliKaydiIzle(id, source, target, kalici);
}

/* Kayıt durumu DÜRÜST söylenir. Eskiden kuyruğa yazar yazmaz "Eklendi" deyip
   pencereyi kapatıyordu; gönderim reddedilse ya da depolama yazılamasa bile
   kullanıcı kaydın sunucuya ulaştığını sanıyordu. Artık işlemin kimliği izlenir:
   "cihazda bekliyor" -> "sunucuya kaydedildi" ya da "gönderilemedi". */
let hizliKayitDinleyici = null;

function hizliKaydiBirak() {
  if (hizliKayitDinleyici) hizliKayitDinleyici();
  hizliKayitDinleyici = null;
}

function hizliKaydiIzle(id, source, target, kalici) {
  hizliKaydiBirak();
  const yaz = (metin) => (el("glossQuickState").textContent = metin);
  yaz(
    kalici
      ? `Cihazda bekliyor: ${source} → ${target} — sunucuya gönderiliyor…`
      : `Cihaza yazılamadı (depolama dolu ya da kapalı): ${source} → ${target} yalnız bu oturumda bekliyor, gönderiliyor…`
  );
  hizliKayitDinleyici = kuyrukDinle((ad, veri) => {
    if (!veri || !veri.islem || veri.islem.id !== id) return;
    if (ad === "gonderildi") {
      hizliKaydiBirak();
      yaz(`Sunucuya kaydedildi: ${source} → ${target}`);
      setTimeout(() => diyalogKapat("glossQuickModal"), 900);
    } else if (ad === "hata") {
      hizliKaydiBirak();
      yaz(
        `Gönderilemedi (${veri.kod}${veri.mesaj ? " — " + veri.mesaj : ""}). ` +
          "Kayıt silinmedi: sözlük ekranından tekrar deneyebilir ya da vazgeçebilirsin."
      );
    } else if (ad === "bekliyor") {
      hizliKaydiBirak();
      if (kuyruk.kalici()) {
        yaz(`Cihazda bekliyor: ${source} → ${target} — sunucuya ulaşınca kendiliğinden kaydedilecek.`);
        setTimeout(() => diyalogKapat("glossQuickModal"), 1800);
      } else {
        yaz(
          `Sunucuya ulaşılamadı ve cihaza da yazılamadı: uygulamayı kapatırsan ${source} kaybolur. ` +
            "Bağlantı gelince yeniden denenecek."
        );
      }
    }
  });
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {

  document.addEventListener("selectionchange", () => {
    clearTimeout(selGlossTimer);
    // Seçim tutamacı sürüklenirken her karede yeniden konumlandırma.
    selGlossTimer = setTimeout(updateSelGloss, 180);
  });
  // Seçim ekranda kayınca düğme onunla birlikte gitsin (gizlemek yerine yeniden konumla:
  // kaydırıp sonra eklemek isteyen kullanıcı düğmeyi kaybetmemeli).
  window.addEventListener("scroll", () => selGlossData && updateSelGloss(), { passive: true });

  el("selGlossBtn")?.addEventListener("click", openGlossQuick);
  el("glossQuickSave")?.addEventListener("click", saveGlossQuick);
  el("glossQuickCancel")?.addEventListener("click", () => {
    hizliKaydiBirak();
    diyalogKapat("glossQuickModal");
  });
  el("glossQuickModal")?.addEventListener("click", (e) => {
    if (e.target === el("glossQuickModal")) diyalogKapat("glossQuickModal");
  });
  for (const id of ["glossQuickSource", "glossQuickTarget"]) {
    el(id)?.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      saveGlossQuick();
    });
  }
}
