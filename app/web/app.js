/* NovelLink okuyucu — GİRİŞ NOKTASI.

   Kod `js/` altındaki ES modüllerindedir; bu dosya yalnız olay kayıtlarını
   sırayla kurar ve uygulamayı başlatır. Build adımı YOK: tarayıcı modülleri
   doğrudan yükler. Yeni bir modül eklenirse `sw.js` SHELL listesine de
   eklenmeli — yoksa çevrimdışı açılışta o modül indirilemez ve uygulama
   hiç başlamaz (tests/test_modul_kabugu.py bunu tutar). */

import { kur as diyalogKur } from "./js/diyalog.js";
import { showView, kur as gezinmeKur } from "./js/gezinme.js";
import { renderLibrary, kur as kutuphaneKur } from "./js/kutuphane.js";
import { kur as kitapKur } from "./js/kitap.js";
import { applySettings, updateSettingsUI, kur as ayarlarKur } from "./js/ayarlar.js";
import { flushGlossQueue, kur as sozlukKur } from "./js/sozluk.js";
import { kur as okuyucuKur } from "./js/okuyucu.js";
import { kur as cevrimdisiKur } from "./js/cevrimdisi.js";
import { kur as ekleKur } from "./js/ekle.js";
import { kur as sozluk_secimKur } from "./js/sozluk-secim.js";
import { kur as terimPaneliKur } from "./js/terim-paneli.js";
import { kur as apiDurumKur } from "./js/api-durum.js";

diyalogKur();
// `gezinme`den ÖNCE: panelin popstate dinleyicisi görünüm DEĞİŞMEDEN önce koşmalı
// (Chromium pencere dinleyicilerini kayıt sırasıyla çağırıyor — ölçüldü).
apiDurumKur();
gezinmeKur();
kutuphaneKur();
kitapKur();
ayarlarKur();
sozlukKur();
okuyucuKur();
cevrimdisiKur();
ekleKur();

/* ---------- başlangıç ---------- */
applySettings();
updateSettingsUI();
// Tarayıcının otomatik scroll restorasyonunu KAPAT (SPA kendi restorasyonunu yapar:
// loadChapter restoreRatio). Aksi halde geri jestinde tarayıcı pencereyi tepeye
// kaydırır, reader HÂLÂ görünürken bir scroll olayı tetiklenir ve updateActiveChapter
// aktif bölümü akışın İLK (en üstteki) bölümüne sıfırlar → konum başladığın bölüme
// geri yazılır ("bir önceki/ilk bölüme dönüyor" bug'ı; sonsuz okuma v2 ile geldi).
if ("scrollRestoration" in history) history.scrollRestoration = "manual";
history.replaceState({ view: "library" }, ""); // kök kayıt: buradan geri = uygulamadan çık

renderLibrary();
showView("library");

sozluk_secimKur();
terimPaneliKur();

// Açılışta bekleyen sözlük düzenlemelerini gönder (çevrimdışı eklenip telefonda
// kalmış olabilir); sunucu hâlâ kapalıysa kuyrukta bekler.
flushGlossQueue();

// Sıfırlamanın önbellek-kırıcı parametresini adres çubuğundan temizle. Uygulamanın
// kök history kaydından (yukarıda) SONRA koşar; `history.state` korunur.
if (location.search.includes("kabuk=")) {
  history.replaceState(history.state, "", location.pathname);
}

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
  // Kalıcı depolama: tarayıcı yer darlığında çevrimdışı bölüm önbelleğini silmesin.
  navigator.storage?.persist?.().catch(() => {});
  // Yeni SW sürümü devraldığında sayfayı bir kez tazele: aksi halde açık sayfa
  // eski kabuk JS/CSS'iyle çalışmayı sürdürür (örn. yeni eklenen düğmeler görünmez).
  // hadController: ilk kurulumda (sayfa zaten ağdan geldi) gereksiz reload atlanır.
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController || reloaded) return;
    reloaded = true;
    location.reload();
  });
}
