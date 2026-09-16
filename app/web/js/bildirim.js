/* Kısa süreli bildirim ("snackbar"), isteğe bağlı TEK eylemle (ör. GERİ AL).

   Tek bir alan kullanılır (`#bildirim`, aria-live): yeni bildirim eskisinin
   yerini alır. İki bildirim üst üste yığılsaydı parmak GERİ AL'a basarken alttaki
   değişip yanlış işlemi geri alabilirdi. Eylem yalnız bir kez çalışır. */

import { el } from "./temel.js";

let zamanlayici = null;
let aktifEylem = null;

export function bildirimKapat() {
  clearTimeout(zamanlayici);
  zamanlayici = null;
  aktifEylem = null;
  const kutu = el("bildirim");
  if (kutu) kutu.hidden = true;
}

/* `eylem`: { etiket, fn } — basılınca fn çağrılır ve bildirim kapanır.
   `sure`: ms; eylemli bildirim varsayılan olarak daha uzun kalır (karar zamanı). */
export function bildir(metin, { eylem = null, sure = null } = {}) {
  const kutu = el("bildirim");
  if (!kutu) return;
  clearTimeout(zamanlayici);
  kutu.replaceChildren();
  const yazi = document.createElement("span");
  yazi.className = "bildirim-metin";
  yazi.textContent = metin;
  kutu.appendChild(yazi);
  aktifEylem = eylem;
  if (eylem) {
    const dugme = document.createElement("button");
    dugme.type = "button";
    dugme.className = "bildirim-eylem";
    dugme.textContent = eylem.etiket;
    dugme.addEventListener("click", () => {
      const fn = aktifEylem && aktifEylem.fn;
      bildirimKapat();
      if (fn) fn();
    });
    kutu.appendChild(dugme);
  }
  kutu.hidden = false;
  zamanlayici = setTimeout(bildirimKapat, sure ?? (eylem ? 8000 : 3500));
}
