/* Ortak modal pencere: yerel <dialog> + showModal.

   Belge bulgusu (2026-09-16): modallar `div.modal` ile kurulmuştu — Tab arka
   plandaki sayfaya kaçıyor, Escape kapatmıyor, kapanınca odak kayboluyor ve ekran
   okuyucu pencere başlığını duyurmuyordu. `showModal()` arka planı `inert` yapar
   (odak içeride kalır) ve Escape'te `cancel` yayar; eksik kalan iki davranış
   burada tamamlanır: KAPANINCA ODAK açan düğmeye döner, PERDEYE dokunmak kapatır.

   Pencere başlığı `aria-labelledby` ile HTML'de bağlıdır (`<id>-baslik`). */

import { el } from "./temel.js";

const acanlar = new Map(); // diyalog id -> açan öğe (odak dönüşü için)

export function diyalogAcikMi(id) {
  const d = el(id);
  return !!(d && d.open);
}

export function diyalogAc(id) {
  const d = el(id);
  if (!d || d.open) return;
  const aktif = document.activeElement;
  if (aktif && aktif !== document.body) acanlar.set(id, aktif);
  d.showModal();
}

export function diyalogKapat(id) {
  const d = el(id);
  if (d && d.open) d.close();
}

/* Her <dialog> için bir kez: odak dönüşü + perde tıklaması. `data-perde-kapatmaz`
   taşıyan pencere (ör. yükleme sürerken) perdeyle kapanmaz. */
export function kur() {
  for (const d of document.querySelectorAll("dialog")) {
    d.addEventListener("close", () => {
      const acan = acanlar.get(d.id);
      acanlar.delete(d.id);
      // Okuma konumu kaymasın: odak geri gelirken sayfa kaydırılmaz.
      if (acan && acan.isConnected) acan.focus({ preventScroll: true });
    });
    d.addEventListener("click", (e) => {
      // Perde tıklaması hedef olarak diyaloğun KENDİSİNİ verir (içerik kartı
      // değil). Kart dışındaki boşluk da diyaloğun parçası olduğu için aynı yol.
      if (e.target === d && !d.hasAttribute("data-perde-kapatmaz")) d.close();
    });
  }
}
