/* Okuma ayarları (tema, punto, satır aralığı, kenar, sonsuz okuma), çeviri modeli
   seçimi, harcama göstergesi, kabuk sürümü ve sıfırlama. */

import { refreshStreamEnd, setStatus } from "./okuyucu.js";
import { fetchWithTimeout } from "./sozluk.js";
import { ICONS, THEME_ICON, el, markSegment } from "./temel.js";

export const LS_SETTINGS = "novellink:settings";
export const DEFAULT_SETTINGS = {
  theme: "light",
  fontPx: 19,
  font: "serif",
  lineHeight: "normal",
  margin: "normal",
  // Sonsuz okuma: bölüm sonuna gelince sonrakini akışa kendiliğinden ekle. Kapalıyken
  // akış tek bölümdür ve devam elle ("SONRAKİ BÖLÜM →") olur — manga'nın site'den
  // sonraki bölümü çekmesi de aynı anahtara bağlıdır.
  infinite: true,
};
export const THEMES = ["light", "sepia", "dark"];
export const LINE_HEIGHTS = { sik: "1.5", normal: "1.75", seyrek: "2.1" };
export const MARGINS = { dar: "0.8rem", normal: "1.3rem", genis: "2.2rem" };

export const settings = loadSettings();
export function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(localStorage.getItem(LS_SETTINGS)) || {}) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}
export function saveSettings() {
  localStorage.setItem(LS_SETTINGS, JSON.stringify(settings));
}

/* ---------- ayarları uygula ---------- */
export function applySettings() {
  const root = document.documentElement;
  root.dataset.theme = settings.theme;
  root.style.setProperty("--reading", settings.fontPx + "px");
  root.style.setProperty(
    "--reading-font",
    settings.font === "sans"
      ? 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
      : 'Georgia, "Times New Roman", serif'
  );
  root.style.setProperty(
    "--reading-line-height",
    LINE_HEIGHTS[settings.lineHeight] || LINE_HEIGHTS.normal
  );
  root.style.setProperty("--reading-margin", MARGINS[settings.margin] || MARGINS.normal);
}
export function updateSettingsUI() {
  el("fontValue").textContent = settings.fontPx;
  el("fontFamily").textContent = settings.font === "sans" ? "Sans" : "Serif";
  el("libThemeToggle").innerHTML = THEME_ICON[settings.theme] || ICONS.moon;
  markSegment("theme", settings.theme, "data-theme-opt");
  markSegment("lh", settings.lineHeight, "data-lh");
  markSegment("mg", settings.margin, "data-mg");
  markSegment("inf", settings.infinite ? "1" : "0", "data-inf");
}
export function setTheme(name) {
  if (!THEMES.includes(name)) return;
  settings.theme = name;
  saveSettings();
  applySettings();
  updateSettingsUI();
}
export function cycleTheme() {
  const i = THEMES.indexOf(settings.theme);
  setTheme(THEMES[(i + 1) % THEMES.length]);
}
/* ---------- çeviri modeli seçimi ---------- */
/* Ayar SUNUCUDA durur (`/api/settings/model`), okuyucunun localStorage'ında değil.
   Üç sebep: çeviriyi sunucu yapıyor · telefon ve PC aynı seçimi görmeli · okumanın
   gövdesi PREFETCH'ten ve toplu çeviriden geliyor, onlar istemci olmadan koşuyor ve
   istemci-taraflı bir ayarı okuyamazlardı. */
export let modelSecenekleri = [];

export function cizModelSecim(secili) {
  const kutu = el("modelSecim");
  if (!kutu) return;
  kutu.innerHTML = "";
  for (const m of modelSecenekleri) {
    const b = document.createElement("button");
    b.className = "seg";
    b.dataset.model = m.ad;
    b.textContent = m.etiket;
    b.title = m.not || m.ad;
    b.setAttribute("aria-pressed", m.ad === secili ? "true" : "false");
    kutu.appendChild(b);
  }
  const notu = el("modelNotu");
  if (notu) {
    const bulunan = modelSecenekleri.find((m) => m.ad === secili);
    /* Ölçüm notu görünür duruyor: kullanıcı seçerken neyin bedelini ödediğini
       bilmeli (3.7/3.8 uzun bölümleri reddedip dakikalar yakabiliyor, Claude
       halkaları ise PARA harcıyor). */
    notu.textContent = bulunan ? bulunan.not : "";
    notu.classList.toggle("model-ucretli", !!(bulunan && bulunan.ucretli));
  }
}

/* Harcama GÖSTERGESİ — fren değil (kullanıcı kararı). Sürpriz harcamanın kaynağı
   zaten yapısal olarak kapalı: ücretli model elle seçiliyor ve ücretsiz zincir asla
   ücretliye inmiyor. Gösterge "bu gidişle ne olur" sorusunu cevaplamak için var,
   o yüzden pencere AYLIK (fatura da öyle okunuyor). */
export function cizHarcama(harcama) {
  const satir = el("modelHarcama");
  if (!satir) return;
  if (!harcama || !harcama.istek) {
    satir.hidden = true;
    return;
  }
  const dokum = harcama.modeller
    .map((m) => `${m.model.replace(/^claude-/, "")} ${m.istek}`)
    .join(" · ");
  satir.hidden = false;
  satir.textContent =
    `Bu ay ücretli çeviri: ${harcama.istek} bölüm ≈ ` +
    `$${harcama.maliyet.toFixed(2)} (${dokum})`;
}

export async function loadModelSecim() {
  const kutu = el("modelSecim");
  if (!kutu) return;
  try {
    const res = await fetch("/api/settings/model");
    if (!res.ok) throw new Error(`sunucu ${res.status}`);
    const data = await res.json();
    modelSecenekleri = data.secenekler || [];
    cizModelSecim(data.secili);
    cizHarcama(data.harcama);
  } catch {
    kutu.innerHTML = "";
    const notu = el("modelNotu");
    if (notu) notu.textContent = "Sunucuya ulaşılamadı — model seçimi okunamadı.";
  }
}

/* ---------- kabuk sürümü + sıfırlama (bayat kabuk kaçış kapısı) ---------- */
export const KABUK_ONEK = "novellink-shell-";
export const VERI_ONBELLEK = "novellink-data";

/* Sunucunun ŞU ANKİ kabuk sürümü — `sw.js` HTTP önbelleği ATLANARAK okunur ve
   içindeki SHELL_CACHE çıkarılır.

   Neden ikinci bir sürüm sabiti tutmuyoruz: app.js'e ayrı bir sabit koysaydık
   sw.js ile birlikte bumplanmayı unutmak sürüm bilgisinin KENDİSİNİ bayatlatırdı
   (yanlış "güncel" yazan bir gösterge, göstergesizlikten kötüdür). Tek kaynak
   sw.js.

   ZAMAN AŞIMI ŞART (ölçülen vaka, ts.net üzerinden telefon): Tailscale tökezlediğinde
   bu adrese giden istek HATA VERMEZ, dakikalarca askıda kalır — `sw.js` içindeki
   `fetchWithTimeout` de tam olarak bu "kara delik" yüzünden var. Zaman aşımı olmadan
   aşağıdaki `await` hiç dönmüyor ve sürüm satırı BOŞ kalıyordu; kullanıcı da
   sıfırlamanın işe yarayıp yaramadığını göremiyordu ("sıfırla düzgün çalışmıyor,
   anlamadım"). Boş bir gösterge, göstergesizlikten kötüdür. */
export async function sunucuKabukSurumu(ms = 4000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch("/sw.js", { cache: "no-store", signal: ctrl.signal });
    const m = (await res.text()).match(/SHELL_CACHE\s*=\s*"([^"]+)"/);
    return m ? m[1] : null;
  } finally {
    clearTimeout(timer);
  }
}

/* Sunucuya ulaşmayı BİRDEN ÇOK KEZ dener; "ulaşıldı mı" ile "sürüm okunabildi mi"
   sorularını AYIRIR.

   Ölçülen kök neden (2026-09-06, kullanıcı bildirimi "sunucuya bağlanmıyor"):
   sunucu, `tailscale serve` proxy'si ve tünelin üçü de SAĞLAMDI — PC'den
   `https://<makine>.ts.net/api/books` 200 dönüyordu. Arıza telefonun ilk
   isteğindeydi: Android'de Tailscale boştayken düşük güç durumuna geçiyor ve
   tünel ilk pakette hazır olmuyor. Ölçüm: PC'den atılan `tailscale ping`in
   İLKİ zaman aşımına uğradı, İKİNCİSİ 38 ms'de döndü (doğrudan LAN yolu).
   Tek atışlık 4 sn'lik kontrol bu UYANMA ANINI "sunucu kapalı" diye okuyup
   sıfırlamayı reddediyordu. Başarısız ilk istek tünelin uyanmasını ZATEN
   tetiklediği için ikinci deneme çoğunlukla tutar.

   İkinci bir arıza da burada kapanıyor: eski kontrol `sunucuKabukSurumu()`nün
   `null` dönmesini "ulaşılamadı" sayıyordu, oysa `null` "sunucuya ULAŞILDI ama
   sürüm deseni eşleşmedi" demek. Sunucu ayaktayken bile sıfırlamayı reddedecek
   bir yoldu. Artık ağ hatası (throw) ile desen eşleşmemesi (null) ayrı. */
export async function sunucuyaUlas(denemeler = 3, ms = 4000) {
  for (let i = 0; i < denemeler; i++) {
    try {
      return { ulasildi: true, surum: await sunucuKabukSurumu(ms) };
    } catch {
      // Son denemede bekleme: kullanıcıyı boşuna oyalamaz.
      if (i < denemeler - 1) await new Promise((r) => setTimeout(r, 700));
    }
  }
  return { ulasildi: false, surum: null };
}

/* Panel her açılışta GERÇEK durumu okur ve TELEFONDAKİ ile SUNUCUDAKİNİ KIYASLAR.
   Eskiden yalnız telefondaki sürüm yazıyordu; "v68" görmek güncel mi bayat mı
   olduğunu söylemiyordu, yani sıfırlamanın işe yarayıp yaramadığı doğrulanamıyordu
   (kullanıcı bildirimi: "tam sıfırlamıyor gibi"). */
export async function showShellVersion() {
  const out = el("shellVersion");
  if (!out) return;
  out.classList.remove("shell-ver-stale");
  if (!("caches" in window)) {
    out.textContent = "(önbellek yok — hep ağdan)";
    return;
  }
  let telefonda;
  try {
    telefonda = (await caches.keys()).filter((k) => k.startsWith(KABUK_ONEK));
  } catch (err) {
    // Sessiz boşaltma YASAK: satırın boş kalması, kullanıcıya sıfırlamanın işe
    // yarayıp yaramadığını göremediği bir ekran bırakıyordu ("anlamadım").
    out.textContent = "(önbellek okunamadı: " + (err?.name || "hata") + ")";
    out.classList.add("shell-ver-stale");
    return;
  }
  const kisa = (k) => k.replace(KABUK_ONEK, "");
  if (!telefonda.length) {
    out.textContent = "(kurulmadı)";
    return;
  }
  // Birden çok kabuk önbelleği = önceki güncelleme YARIM kalmış. Tek başına bir
  // bulgudur: activate'in temizliği koşmamış demektir.
  if (telefonda.length > 1) {
    out.textContent = telefonda.map(kisa).join(" + ") + " — karışık, sıfırla";
    out.classList.add("shell-ver-stale");
    return;
  }
  const bu = kisa(telefonda[0]);
  // Yerel sürümü HEMEN yaz. Aşağıdaki sunucu kıyası askıda kalırsa (Tailscale kara
  // deliği) bu satıra hiç dönülmüyordu ve gösterge BOŞ kalıyordu — asıl şikâyetin
  // kaynağı buydu. Kıyas sonuçlanırsa üzerine yazılır.
  out.textContent = bu;
  // Gösterge için İKİ deneme yeter: burada bekleme kullanıcıyı oyalar ve panel
  // zaten yeniden açılabilir. Sıfırlama düğmesi (yıkıcı işlem) üç deneme yapar.
  const { ulasildi, surum: sunucuda } = await sunucuyaUlas(2);
  if (!ulasildi) {
    // "güncel" demek YANLIŞ olurdu; sürümü yaz ve ulaşılamadığını SÖYLE — sıfırlama
    // bu hâldeyken kabuğu silip yerine yenisini indiremeyeceği için tehlikelidir.
    out.textContent = bu + " · sunucuya ulaşılamıyor";
    out.classList.add("shell-ver-stale");
    return;
  }
  if (!sunucuda) {
    out.textContent = bu;
    return;
  }
  const o = kisa(sunucuda);
  out.textContent = bu === o ? bu + " · güncel" : bu + " -> sunucuda " + o + ", sıfırla";
  if (bu !== o) out.classList.add("shell-ver-stale");
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {

  /* ---------- olaylar: navigasyon ---------- */
  el("libThemeToggle").addEventListener("click", cycleTheme);

  /* ---------- olaylar: ayarlar (segmented + stepper) ---------- */
  document.querySelectorAll("[data-theme-opt]").forEach((b) =>
    b.addEventListener("click", () => setTheme(b.getAttribute("data-theme-opt")))
  );
  document.querySelectorAll("[data-lh]").forEach((b) =>
    b.addEventListener("click", () => {
      settings.lineHeight = b.getAttribute("data-lh");
      saveSettings();
      applySettings();
      updateSettingsUI();
    })
  );
  document.querySelectorAll("[data-mg]").forEach((b) =>
    b.addEventListener("click", () => {
      settings.margin = b.getAttribute("data-mg");
      saveSettings();
      applySettings();
      updateSettingsUI();
    })
  );
  // Sonsuz okuma aç/kapa: açıkken bölüm sonunda sonraki kendiliğinden eklenir, kapalıyken
  // akış tek bölümde durur ve "SONRAKİ BÖLÜM →" düğmesiyle devam edilir. Anahtar okuyucu
  // açıkken de çevrilebilir → akışın sonu (gözlemci + bitiş kartı) hemen yeniden kurulur.
  document.querySelectorAll("[data-inf]").forEach((b) =>
    b.addEventListener("click", () => {
      settings.infinite = b.getAttribute("data-inf") === "1";
      saveSettings();
      updateSettingsUI();
      refreshStreamEnd();
    })
  );

  el("modelSecim").addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-model]");
    if (!b || b.getAttribute("aria-pressed") === "true") return;
    const onceki = modelSecenekleri.find(
      (m) => el("modelSecim").querySelector(`[data-model="${m.ad}"]`)
               ?.getAttribute("aria-pressed") === "true",
    );
    cizModelSecim(b.dataset.model); // iyimser: dokunuş anında geri bildirim
    try {
      const res = await fetch("/api/settings/model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: b.dataset.model }),
      });
      if (!res.ok) throw new Error(`sunucu ${res.status}`);
      const data = await res.json();
      cizModelSecim(data.secili);
      /* Sözlükle AYNI kural: yalnız yeni çevrilen bölümde geçerli.
         Söylenmezse kullanıcı açık duran bölümün değişmesini bekler ve "çalışmadı"
         sanır. */
      setStatus("Model seçildi — yeni çevrilen bölümlerde geçerli.");
    } catch {
      if (onceki) cizModelSecim(onceki.ad); // yazılamadı: gerçeğe geri dön
      setStatus("Model kaydedilemedi — sunucuya ulaşılamadı.");
    }
  });

  el("settingsBtn").addEventListener("click", () => {
    el("settingsPanel").hidden = !el("settingsPanel").hidden;
    if (!el("settingsPanel").hidden) {
      showShellVersion();
      loadModelSecim();
    }
  });

  el("shellReset")?.addEventListener("click", async () => {
    const btn = el("shellReset");
    btn.disabled = true;
    btn.textContent = "Sıfırlanıyor…";
    /* SUNUCU ERİŞİMİ ÖN KOŞUL. Sıfırlama kabuk önbelleğini SİLİP service worker'ı
       kaldırıyor; yerine yenisini ancak ağdan indirebilir. Sunucuya ulaşılamıyorken
       basılırsa uygulama telefonda tümden açılmaz hâle gelir (indirilen bölümler
       `novellink-data`da durur ama onlara ulaşacak kabuk kalmaz). Bu, kullanıcının
       "bir şey çalışmıyor" diye bastığı anda tam olarak gerçekleşebilecek senaryodur —
       Tailscale koptuğunda uygulama önbellekten açılmaya devam ettiği için ağın
       gittiği fark edilmiyor. */
    try {
      // ÜÇ deneme: bu yıkıcı bir işlem ve yanlış bir "ulaşılamıyor" kullanıcıyı
      // sunucu sapasağlamken kilitliyor (ölçülen vaka). Tünelin uyanması için
      // birkaç saniye beklemek, hatalı reddin bedelinden ucuz.
      btn.textContent = "Sunucu deneniyor…";
      if (!(await sunucuyaUlas(3)).ulasildi) {
        btn.textContent = "Sunucuya ulaşılamıyor";
        alert(
          "Sunucuya ulaşılamıyor, bu yüzden sıfırlama yapılmadı.\n\n" +
          "Sıfırlama uygulama kabuğunu siler ve yerine yenisini sunucudan indirir; " +
          "şu an indiremeyeceği için uygulama açılmaz hâle gelirdi.\n\n" +
          "Üç kez denendi. Telefon uykudaysa Tailscale'in tüneli ilk isteklerde " +
          "hazır olmayabilir: Tailscale uygulamasını bir açıp kapatın, sonra " +
          "tekrar deneyin. PC'deki sunucunun da açık olduğundan emin olun."
        );
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = "Sıfırla";
        }, 2500);
        return;
      }
    } catch {}
    try {
      if ("serviceWorker" in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map((r) => r.unregister()));
      }
      if ("caches" in window) {
        const keys = await caches.keys();
        // İndirilen bölümler (novellink-data) KORUNUR; yalnız kabuk önbellekleri silinir.
        await Promise.all(
          keys.filter((k) => k !== VERI_ONBELLEK).map((k) => caches.delete(k))
        );
      }
    } catch {}
    /* Düz `location.reload()` YETMİYOR: `unregister()` kaydı siler ama açık sayfa
       UNLOAD olana kadar hâlâ eski service worker tarafından KONTROL EDİLİYOR, yani
       reload navigasyonu onun fetch handler'ından geçebiliyor. Benzersiz sorgulu bir
       navigasyon hem onu hem HTTP önbelleğini kesin olarak atlar. Parametre açılışta
       temizlenir (adres çubuğunda kalmasın) — bkz. aşağıdaki temizleyici. */
    location.replace(location.pathname + "?kabuk=" + Date.now());
  });
  el("fontMinus").addEventListener("click", () => {
    settings.fontPx = Math.max(14, settings.fontPx - 1);
    saveSettings();
    applySettings();
    updateSettingsUI();
  });
  el("fontPlus").addEventListener("click", () => {
    settings.fontPx = Math.min(30, settings.fontPx + 1);
    saveSettings();
    applySettings();
    updateSettingsUI();
  });
  el("fontFamily").addEventListener("click", () => {
    settings.font = settings.font === "sans" ? "serif" : "sans";
    saveSettings();
    applySettings();
    updateSettingsUI();
  });

  el("clearanceRefresh")?.addEventListener("click", async () => {
    const btn = el("clearanceRefresh");
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Yenileniyor…";
    try {
      const res = await fetch("/api/clearance/refresh", { method: "POST" });
      if (!res.ok) throw new Error();
      btn.textContent = "Yenilendi ✓";
    } catch {
      btn.textContent = "Yenilenemedi";
    }
    setTimeout(() => {
      btn.textContent = old;
      btn.disabled = false;
    }, 2500);
  });
}
