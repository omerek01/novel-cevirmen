/* Görünüm değişimi ve geçmiş (history) tabanlı uygulama-içi geri; alt gezinme. */

import { apiDurumGoster } from "./api-durum.js";
import { diyalogAcikMi, diyalogKapat } from "./diyalog.js";
import { settings } from "./ayarlar.js";
import { startOfflineDownloadAll } from "./cevrimdisi.js";
import { views } from "./durum.js";
import { openBook } from "./kitap.js";
import { renderLibrary } from "./kutuphane.js";
import { hudGoster, kokeneOdaklan, loadChapter, persistScroll } from "./okuyucu.js";
import { openGlossary } from "./sozluk.js";
import { ICONS, el } from "./temel.js";

/* ---------- görünüm ---------- */
export function showView(name) {
  for (const [key, node] of Object.entries(views)) node.hidden = key !== name;
  // Alt gezinme OKURKEN gizlenir: sonsuz okuma akışında ekranın altı metindir ve
  // sabit bir çubuk hem alanı yer hem parmağın altında kalır. `body.reading`
  // gövdenin alt boşluğunu da kaldırır (çubuk yokken boşluk anlamsız).
  const nav = el("bottomNav");
  if (nav) {
    nav.hidden = name === "reader";
    document.body.classList.toggle("reading", name === "reader");
  }
  // Okuyucuya her girişte HUD AÇIK başlar: bir önceki bölümden gizli devralınsa
  // kullanıcı başlıksız bir ekrana düşer ve nerede olduğunu göremez.
  if (name === "reader") hudGoster();
  // Okuyucudan çıkarken açık kalmış ayar sheet'i kapansın: body seviyesine
  // taşındığı için artık görünüm değişince kendiliğinden gizlenmiyor.
  if (name !== "reader") diyalogKapat("settingsPanel");
  senkronlaSekme(name);
}

/* ---------- alt gezinme ----------
   ÜÇ sekme: Stitch'in dördüncüsü ("Güncellemeler") bu projede bir ekrana
   karşılık gelmiyor — check-updates yalnız arka plan iş tipi. Boş bir sekme
   koymak, tasarımdan çıkarılan puan/yazar/özet alanlarıyla aynı türden bir boş
   vaat olurdu. */
export function senkronlaSekme(name) {
  const acik = diyalogAcikMi("settingsPanel");
  for (const t of document.querySelectorAll(".navtab")) {
    const etkin = acik ? t.dataset.tab === "settings"
                       : t.dataset.tab === "library" && name === "library";
    if (etkin) t.setAttribute("aria-current", "page");
    else t.removeAttribute("aria-current");
  }
}

/* ---------- tarayıcı/telefon geri tuşu = uygulama-içi geri ----------
   Her görünüm geçişi history'ye bir kayıt olarak işlenir (navigate). Geri tuşunda
   (popstate) o kayda karşılık gelen görünüm yeniden çizilir — böylece geri tuşu
   uygulamayı kapatmak yerine bir önceki ekrana döner. Kök (kütüphane) görünümünde
   geri tuşu uygulamadan çıkar (beklenen davranış). */
export function applyNavState(state) {
  // Okuyucudan başka görünüme geçerken son konumu ANINDA yaz (uygulama-içi geri'de
  // pagehide/visibilitychange tetiklenmez; throttle'lı son POST kaçarsa kütüphane/
  // liste bir bölüm geride kalırdı).
  if (!views.reader.hidden && state && state.view !== "reader") persistScroll();
  switch (state && state.view) {
    case "book":
      openBook(state.slug);
      break;
    case "glossary":
      openGlossary(state.slug);
      break;
    case "apidurum":
      apiDurumGoster();
      break;
    case "reader":
      // Köken varken KAYITLI KONUM geri yüklenmez: kullanıcı "kaldığın yere"
      // değil, terimin geçtiği cümleye gitmek istedi.
      loadChapter(state.url, {
        restoreRatio: state.ratio,
        koken: state.koken,
      }).then(() => {
        if (!state.koken) return;
        // Konum geri yükleme `requestAnimationFrame` içinde koşuyor; odaklama
        // doğrudan çağrılırsa o kare kaydırmayı EZİYOR. İki kare beklemek,
        // restore bitmiş olsun diye.
        requestAnimationFrame(() =>
          requestAnimationFrame(() => kokeneOdaklan(state.koken, state.url))
        );
      });
      break;
    default:
      renderLibrary();
      showView("library");
  }
}

// Navigasyon. replace=false (varsayılan): seviye geçişi → geçmişe YENİ kayıt (push).
// replace=true: aynı seviyede kalır (bölüm↔bölüm) → üstteki kaydı DEĞİŞTİR, geçmişi
// büyütme. Böylece okuyucu tek history kaydı tutar ve "geri" hep bir üst seviyeye
// (kitap/kütüphane) gider — bölüm bölüm geriye taramaz. Tüm "geri" aksiyonları
// history.back() kullanır (aşağıda), pushState DEĞİL → jest görsel hiyerarşiyle uyumlu.
export function navigate(state, replace = false) {
  if (replace) history.replaceState(state, "");
  else history.pushState(state, "");
  applyNavState(state);
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {

  window.addEventListener("popstate", (e) => {
    applyNavState(e.state || { view: "library" });
  });
  // Tüm "geri" düğmeleri = history.back(): geçmiş yığınını POP eder (popstate → önceki
  // görünüm). navigate() (push) KULLANMAZ — aksi halde "geri" ileri kayıt iter ve jest
  // desenkron olurdu (bu bug'ın kök nedeni). Kök kayıt daima {library} (init'te
  // replaceState) olduğundan back güvenli; kütüphanede back = uygulamadan çıkış.
  el("backBtn").addEventListener("click", () => history.back());
  el("bookBackBtn").addEventListener("click", () => history.back());
  el("glossaryBackBtn").addEventListener("click", () => history.back());

  /* Alt gezinme: ikonlar + davranış. Sekmeler MEVCUT işlevleri çağırır, yenisini
     uydurmaz — "Çevrimdışı" kütüphanedeki indirme akışının, "Ayarlar" ise
     `settingsBtn`in ta kendisidir (aynı işi iki ayrı kod yolundan yapmak, bu
     projede künye alanlarının ayrıştığı hatanın aynısı olurdu). */
  {
    const IKON = { library: ICONS.shelf, offline: ICONS.download, settings: ICONS.sliders };
    for (const tab of document.querySelectorAll(".navtab")) {
      const ad = tab.dataset.tab;
      tab.querySelector(".navtab-icon").innerHTML = IKON[ad] || "";
      tab.addEventListener("click", () => {
        if (ad === "library") {
          diyalogKapat("settingsPanel");
          navigate({ view: "library" });
        } else if (ad === "offline") {
          // İndirme kütüphane ekranının akışı: başka görünümdeysen önce oraya dön,
          // yoksa ilerleme satırı görünmeyen bir ekranda akardı.
          diyalogKapat("settingsPanel");
          if (views.library.hidden) navigate({ view: "library" });
          startOfflineDownloadAll();
        } else if (ad === "settings") {
          el("settingsBtn").click(); // TEK kaynak: panelin kendi aç/kapa mantığı
        }
        senkronlaSekme(views.library.hidden ? "" : "library");
      });
    }
  }
}
