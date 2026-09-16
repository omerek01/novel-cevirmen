/* Okurken seçimden sözlüğe: kayan "+ SÖZLÜĞE EKLE" düğmesi → terim paneli. */

import { durum, views } from "./durum.js";
import { entryFor } from "./okuyucu.js";
import { terimPaneliAc } from "./terim-paneli.js";
import { trimSecim } from "./terim-yardimci.js";
import { el } from "./temel.js";

export { trimSecim };

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

export function hideSelGloss() {
  selGlossData = null;
  const btn = el("selGlossBtn");
  if (btn) btn.hidden = true;
}

/* Seçimin bulunduğu paragrafın bölüm url'si, indeksi ve HİZALI İngilizcesi.
   `.source-line` Türkçe paragrafın hemen ardına eklenir; indeks ondan önceki
   `p[data-idx]`dan okunur. */
function paragrafBaglami(host) {
  const art = host.closest("article.chapter");
  const url = art ? art.dataset.url : null;
  const kaynaktan = !!host.closest(".source-line");
  let p = host.closest("p[data-idx]");
  if (kaynaktan) {
    const satir = host.closest(".source-line");
    p = satir.previousElementSibling;
    while (p && !p.matches("p[data-idx]")) p = p.previousElementSibling;
  }
  const idx = p ? Number(p.dataset.idx) : null;
  const entry = url ? entryFor(url) : null;
  const enParagraf = kaynaktan
    ? host.closest(".source-line").textContent
    : entry && idx != null && entry.source
      ? entry.source[idx] || ""
      : "";
  return { url, idx, kaynaktan, enParagraf, no: entry ? entry.no : null };
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

  selGlossData = { terim, ...paragrafBaglami(host) };
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
  const entry = secim.url ? entryFor(secim.url) : null;
  const slug = (entry && entry.bookSlug) || durum.currentBookSlug;
  hideSelGloss();
  window.getSelection()?.removeAllRanges();
  selGlossLast = null;
  terimPaneliAc({ slug, secim });
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
}
