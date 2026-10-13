# Okuma Salonu Arayüzü — Uygulama Planı

> **Ajanlar için:** superpowers:executing-plans ile görev görev uygulanır; adımlar `- [ ]` ile izlenir.

**Amaç:** PWA'yı onaylı "Okuma Salonu" tasarımına taşımak (davranış değişmeden; okuyucuya açılır-kapanır alt çubuk eklenerek).

**Mimari:** Değişiklik ağırlıkla `app/web/style.css` ve `fonts.css`'te. `index.html` kimlikleri ve JS/testlerin kullandığı sınıflar korunur; yeni işaretleme eklenir. Okuyucu alt çubuğunun saf durum mantığı ayrı modülde (`js/alt-cubuk.js`), Node ile test edilir.

**Teknoloji:** Vanilla JS ES modülleri, CSS değişkenleri, Playwright tarayıcı testleri, `node --test`.

**Tasarım belgesi:** `docs/superpowers/specs/2026-10-13-okuma-salonu-design.md`
**Onaylı görseller ve taşınacak CSS'in kaynağı:** `C:\Users\OMEREK\Desktop\PROJELER\gstack\novel-cevirmen\.stitch\designs\2026-10-13-okuma-salonu\` (`*.png`; `kaynak/okuma-salonu.css`, `kaynak/ekranlar.css`, `kaynak/*.html`). Her görevde ilgili kurallar bu dosyalardan taşınır, sınıf adları uygulamadaki karşılıklarına çevrilir.

## Genel kısıtlar

**Devralma tamamlandı (2026-10-13):** Görev 1–6'nın mevcut commit'leri korundu. Görev 7'nin eksik kapak geçişi `e6c75c4` ile tamamlandı; alt çubuk geçmişi/sıfırlaması, Literata ve küçük metin kontrastı düzeltildi. Görev 8: 1184 çevrimdışı (1 atlanan), 99 tarayıcı ve 46 JS testi geçti; üç temada 21 telefon PNG'si incelendi. Eski adım kutuları ilk planın tarihsel kaydıdır. Küçük görsel fark: büyük inceleme sayısı yerine mevcut sayı metni korunuyor. Ayrıntı: `reports/okuma-salonu-tamamlama/RAPOR.md`. Push/canlı onayı bekliyor.

- Kod, yorum, commit Türkçe. Push ve canlıya alma yalnız kullanıcı onayıyla.
- `app/web/` değişen her commit'te `sw.js` `SHELL_CACHE` bir artar (v119 → v120 → …).
- Yeni JS modülü ve yeni font dosyası `sw.js` `SHELL` listesine girer (`tests/test_modul_kabugu.py`).
- `data-theme` değerleri değişmez: `light`, `sepia`, `dark`. Metin kontrastı her temada ≥ 4.5:1, oran yanına yorum olarak yazılır.
- Hareket yalnız `transform`/`opacity`; 150–320 ms; `prefers-reduced-motion: reduce` hepsini kapatır.
- Her görev sonunda: `../../.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`, `NOVEL_TARAYICI_TEST=1 ../../.venv/Scripts/python.exe -m pytest tests/tarayici -q -p no:cacheprovider`, `node --test "tests/js/*.test.mjs"`; telefon boyutunda (390×844, 2x) üç temada ekran görüntüsü alınıp kullanıcıya gösterilir (`scratchpad/ekran_al.py` ile).

---

### Görev 1: Yazı tipleri ve tema belirteçleri

**Dosyalar:** Oluştur `app/web/fonts/{libre-caslon-display-400,libre-caslon-text-400,libre-caslon-text-400i,libre-caslon-text-700,alegreya-sans-400,alegreya-sans-500,alegreya-sans-700,alegreya-sans-sc-500,alegreya-sans-sc-700}-{latin,latin-ext}.woff2`; Değiştir `app/web/fonts.css`, `app/web/style.css:14-108`, `app/web/sw.js`; Test `tests/test_yazi_tipleri.py`.

- [ ] Google Fonts CSS2 uçlarından (`https://fonts.googleapis.com/css2?family=...` , Chrome kullanıcı ajanıyla) latin ve latin-ext woff2 dosyalarını indir; `fonts.css`'e mevcut Inter/Literata kalıbıyla (`font-display:swap`, aynı `unicode-range` değerleri) `@font-face` ekle. Inter dosyalarını ve kurallarını kaldır.
- [ ] Başarısız test yaz:

```python
import re
from pathlib import Path
WEB = Path(__file__).resolve().parents[1] / "app" / "web"

def test_fonts_css_deki_her_dosya_var_ve_kabukta():
    css = (WEB / "fonts.css").read_text(encoding="utf-8")
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    dosyalar = re.findall(r"url\((fonts/[^)]+\.woff2)\)", css)
    assert dosyalar
    for d in dosyalar:
        assert (WEB / d).exists(), d
        assert f'"/{d}"' in sw, d

def test_inter_kalkti_yeni_aileler_var():
    css = (WEB / "fonts.css").read_text(encoding="utf-8")
    assert "Inter" not in css
    for aile in ("Libre Caslon Display", "Libre Caslon Text", "Alegreya Sans", "Alegreya Sans SC"):
        assert f"font-family:'{aile}'" in css.replace('"', "'").replace(": ", ":")
```

- [ ] Testi koştur, düştüğünü gör; `sw.js` SHELL'e her dosyayı ekle; geçtiğini gör.
- [ ] `style.css` `:root`/`[data-theme="dark"]`/`[data-theme="sepia"]` belirteçlerini tasarım belgesindeki renklere çevir (`light` = #fbfaf6 kâğıt, `sepia` = #f2ede2, `dark` = #14110e); yeni belirteçler: `--brass`, `--stamp`, `--green`, `--shelf-top`, `--shelf-front-1`, `--shelf-front-2`, `--shelf-bottom`, `--display: "Libre Caslon Display", serif`, `--book: "Libre Caslon Text", serif`, `--sans: "Alegreya Sans", system-ui, sans-serif`, `--caps: "Alegreya Sans SC", var(--sans)`. Kâğıt dokusu `body::before` kuralını taşı. Kontrast oranlarını ölç (`scratchpad` içinde küçük bir Python WCAG hesabı) ve yorum olarak yaz.
- [ ] Üç test takımını koştur; ekran görüntülerini al; `SHELL_CACHE` → v120; commit `feat(arayuz): Okuma Salonu yazı tipleri ve tema belirteçleri`.

### Görev 2: Kütüphane

**Dosyalar:** Değiştir `app/web/index.html:19-63`, `app/web/js/kutuphane.js:111-240`, `app/web/style.css` (kütüphane bölümü); Test `tests/tarayici/test_kutuphane_salon.py`.

- [ ] Başarısız tarayıcı testi (mevcut `tests/tarayici/test_kitap_sayfasi.py` kurulum kalıbıyla; tohum kitapları `tohum.py`'den):

```python
def test_kutuphane_salon_ogeleri(sayfa_kutuphane):  # mevcut fikstür adına uyarlanır
    s = sayfa_kutuphane
    assert s.locator(".lib-title").inner_text() == "Kütüphane"
    assert s.locator("#resumeFiche .fiche-label").inner_text().strip().lower() == "ödünç kartı"
    assert s.locator("#resumeFiche .fiche-stamp").count() == 1
    assert s.locator(".shelf-heading-name").first.inner_text().strip() != ""
    kapaksiz = s.locator(".spine:not(.has-cover) .spine-mono")
    if kapaksiz.count():
        assert "cloth" in (kapaksiz.first.evaluate("e => e.parentElement.className") or "")
```

- [ ] `index.html`: `section-label` başlığını `<h1 class="lib-title">Kütüphane</h1>` + `<p id="libSubtitle" class="lib-subtitle"></p>` yap; `libStats` metni alt satıra taşınır (`renderLibStats` hedefi `libSubtitle`, biçim: `"8 kitap · 667 çevrilmiş bölüm"` — kitap sayısı `durum` kütüphane listesinden, toplam `/api/stats` `total`).
- [ ] `renderResumeFiche`: etiket `Ödünç kartı`, başlık, `Bölüm N — ad` (italik), kapak (`book.cover` varsa `<img class="fiche-cover">`), tarih damgası `<span class="fiche-stamp">13 EKİ<small>2026</small></span>` (son okuma tarihi `getLastRead(...).ts` ya da `updated_at`; ay kısaltmaları `["OCA","ŞUB","MAR","NİS","MAY","HAZ","TEM","AĞU","EYL","EKİ","KAS","ARA"]`), cetvel ilerlemesi ve `Devam et` düğmesi. Tıklama davranışı aynen.
- [ ] Durum çiplerini katalog sekmesi görünümüne çevir; her çipe sayı (`<sup>`) ekle (sayılar `setShelfFilter`'ın kullandığı listeden).
- [ ] `buildShelfSection`: başlık pirinç etiketlik (`shelf-heading` → yeni stil, sayı içinde "Noveller · 7"); `makeSpine`: kapaksız kitapta `spine-art` sınıfına `cloth` ekle; iş rozeti (`spine-job`) ayraç görünümü; `makeAddSpine` metni "Rafa kitap ekle" (yatay, kesilmez).
- [ ] CSS'i `kaynak/okuma-salonu.css` "KÜTÜPHANE" bölümünden taşı (`.odunc*`→`.fiche-*`, `.raf-*`→`.shelf-*`, `.kapak`→`.spine-art`, `.yafta*`→`.spine-title/.spine-tag`).
- [ ] Testler + ekran görüntüleri; `SHELL_CACHE` +1; commit `feat(arayuz): kütüphane Okuma Salonu görünümü`.

### Görev 3: Kitap ekranı

**Dosyalar:** `app/web/index.html:66-113`, `app/web/js/kitap.js`, `style.css`; Test `tests/tarayici/test_kitap_sayfasi.py` (mevcut testler geçmeli) + yeni test `test_kitap_kunyesi`.

- [ ] Başarısız test: kitap ekranında `.book-hero .spine-art` (kapak), `.book-hero-title` (kitap adı), `#resumeBtn` içinde `small` (Bölüm N · %x) ve `.chapter-row.current` için `::before` şerit yerine erişilebilir `aria-current="true"`.
- [ ] `bookView` başına kahraman bölümü (kapak + kısa raf + tür/durum etiketi + bilgi satırı) ekle; `resumeBtn` iki satırlı yeşil düğme; `book-actions` üç karo (Sözlük/İndir/Toplu çevir + alt sayılar); "Diğer işlemler" özeti; "Bölümler" başlığı Caslon; bölüm satırı içindekiler düzeni (numara pirinç küçük büyük harf, ad Libre Caslon Text, telefonda olan bölümde telefon simgesi, güncel bölümde kırmızı şerit + "burada"). Silme düğmesi (`.chapter-del`) korunur, soluk gösterilir.
- [ ] CSS `kaynak/ekranlar.css` "kitap ekranı" bölümünden; testler; `SHELL_CACHE` +1; commit.

### Görev 4: Okuyucu ve açılır-kapanır alt çubuk

**Dosyalar:** Oluştur `app/web/js/alt-cubuk.js`, `tests/js/alt-cubuk.test.mjs`, `tests/tarayici/test_okuyucu_alt_cubuk.py`; Değiştir `app/web/index.html:237-266`, `app/web/js/okuyucu.js` (`onReaderScroll`, `kur`), `app/web/sw.js`, `style.css`.

**Arayüz:** `alt-cubuk.js` → `export function sonrakiHal(hal, olay)`; `hal ∈ {"kapali","acik"}`, `olay ∈ {"hap","kapat","asagi-kaydir","yukari-kaydir"}`; dönen değer yeni hal. `export function kalanDakika(oran, sozcuk)` → `Math.max(1, Math.round((1 - oran) * sozcuk / 230))`.

- [ ] Başarısız Node testi:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { sonrakiHal, kalanDakika } from "../../app/web/js/alt-cubuk.js";
test("hap açar, kapat ve aşağı kaydırma kapatır", () => {
  assert.equal(sonrakiHal("kapali", "hap"), "acik");
  assert.equal(sonrakiHal("acik", "kapat"), "kapali");
  assert.equal(sonrakiHal("acik", "asagi-kaydir"), "kapali");
  assert.equal(sonrakiHal("kapali", "yukari-kaydir"), "kapali");
});
test("kalan dakika en az 1", () => {
  assert.equal(kalanDakika(0.99, 100), 1);
  assert.equal(kalanDakika(0.5, 2300), 5);
});
```

- [ ] Modülü yaz (saf, DOM'suz), Node testini geçir; `sw.js` SHELL'e `/js/alt-cubuk.js`.
- [ ] `index.html` okuyucuya `<nav id="okuyucuAlt" class="okuyucu-alt" data-hal="kapali">` ekle: `#altHap` (ilerleme halkası SVG + `#altKalan` + yukarı ok), `#altOnceki`, `#altBolumler`, `#altSozluk`, `#altSonraki`, `#altKapat`. `okuyucu.js`: hap/kapat tıklaması `sonrakiHal`; `onReaderScroll` içinde mevcut `hudGuncelle` yön bilgisinden `asagi-kaydir` olayı; Önceki/Sonraki mevcut `chapterListPrev`/`pickNextTarget` + `navigate` yolunu kullanır (yeni gezinme mantığı yazılmaz); Bölümler → `navigate({view:"book", slug})`; Sözlük → `navigate({view:"glossary", slug})`. Halka ve kalan süre `updateProgress` içinde güncellenir.
- [ ] Başarısız tarayıcı testi: bölüm açılınca `#okuyucuAlt[data-hal="kapali"]`; `#altHap` tıklanınca `acik`; `#altKapat` → `kapali`; açıkken aşağı kaydırınca `kapali`; `#altSonraki` sonraki bölüme gider (tohumdaki iki bölümlü kitapla). Uygula, geçir.
- [ ] Okuma görünümü: bölüm başı (`BÖLÜM N` küçük büyük harf pirinç, başlık Caslon, süs çizgisi), ilk paragrafta büyük ilk harf (`.chapter p:first-of-type::first-letter`), sözlük terimi noktalı pirinç alt çizgi, künye katalog fişi görünümü; metin sola yaslı (`text-align: start`; iki yana yaslama kaldırılır). Üst çubuk HUD davranışı aynen.
- [ ] Testler + ekran görüntüleri (açık/kapalı, üç tema); `SHELL_CACHE` +1; commit `feat(okuyucu): Okuma Salonu görünümü ve açılır-kapanır alt çubuk`.

### Görev 5: Sözlük, incelenecekler ve terim paneli

**Dosyalar:** `app/web/index.html:116-203, 443-540`, `app/web/js/sozluk.js`, `sozluk-inceleme.js`, `terim-paneli.js` (yalnız işaretleme), `style.css`; mevcut testler: `test_sozluk_*.py`, `test_terim_paneli.py`.

- [ ] Başarısız test: sözlük ekranında `.gloss-title` = "Sözlük", `#glossReviewSayi` içinde sayı öğesi `.review-count`, terim satırında `.gloss-source` italik aile `Libre Caslon Text`, uzun açıklama paragrafı (`.gloss-hint` ilk) `<details>` içinde ("?" ile açılır).
- [ ] Büyük başlık + alt satır (terim sayısı); inceleme kutusu inceleme kartı görünümü (büyük kırmızı sayı + "İncele"), "?" açıklamaları (2026-10-09 kararı); ekleme formu alt çizgili alanlar; süzgeçler tek satır yana kayan çipler; terim satırı (İngilizce italik → Türkçe kalın, küçük büyük harf etiketler); terim paneli alttan açılan panel görünümü, koşul altına örnek koşul düğmeleri (tıklayınca koşul alanına metni ekler), Örnek/Köken/Cümleye git korunur.
- [ ] Tüm sözlük tarayıcı testleri geçmeli (seçiciler korunduğu için); `SHELL_CACHE` +1; commit.

### Görev 6: Ayarlar paneli ve alt gezinme

**Dosyalar:** `app/web/index.html:544-640`, `style.css`.

- [ ] Başarısız test: `#settingsPanel` içinde bölüm etiketleri "Sayfa", "Çeviri modeli", "Bu bölüm", "Bakım"; tema düğmeleri (`[data-theme-opt]`) örnek sayfa öğesi (`i.theme-swatch`) taşır.
- [ ] Ayarları dört bölüme ayır (öğeler ve kimlikler aynen), tema örnek kutuları, parçalı seçimler, model listesi radyo satırları (mevcut `#modelSecim` doldurma kodu korunur, yalnız CSS). Alt gezinme pirinç gösterge çizgisi.
- [ ] Testler; `SHELL_CACHE` +1; commit.

### Görev 7: Hareket

**Dosyalar:** `style.css`, `app/web/js/gezinme.js` (View Transitions sarmalayıcısı).

- [ ] Başarısız tarayıcı testi: `prefers-reduced-motion: reduce` ile açılan sayfada `.spine` öğelerinin `getComputedStyle(...).animationName` değeri `none`.
- [ ] Tasarım belgesindeki hareketleri ekle (raf yerleşme, kart yükselme, sekme göstergesi, hap↔çubuk dönüşümü, bölüm başlığı maske yükselişi, ilerleme çizgisi); `navigate` içinde `document.startViewTransition` varsa kapak → kitap kahramanı geçişi (`view-transition-name: kapak-<slug>`), yoksa doğrudan.
- [ ] Testler; `SHELL_CACHE` +1; commit.

### Görev 8: Son doğrulama

- [ ] Üç test takımı; 390×844'te bütün ekranların üç temada görüntüsü, onaylı PNG'lerle yan yana; farklar düzeltilir.
- [ ] `novel-cevirmen/CLAUDE.md` `app/web/` paragrafına yeni modül (`alt-cubuk`) ve yazı tipleri notu; NovelLink `context/` güncellenir; push/canlı için kullanıcıya sorulur.
