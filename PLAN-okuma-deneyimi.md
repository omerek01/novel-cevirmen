# Plan: Okuma Deneyimi Fazı (Faz 4)

> Bağlam: TASARIM.md Faz 0-3 tamamlandı. Bu plan, mevcut çalışan PWA üzerine
> **okuma deneyimi** cilasını ekler. Kişisel kullanım; "mükemmel UI" hedef değil,
> ama günlük okumada hissedilen sürtünmeleri giderir.

## Amaç
Telefonda uzun romanları okurken kaldığın yeri kaybetmeden, ileri-geri kolayca
gezinerek ve gözü yormayan ayarlarla okumak.

## Hedef DEĞİL
- Yeni kaynak site, yeni çeviri modeli, sözlük/çeviri mantığı değişikliği.
- Backend mimarisinde büyük değişiklik. Mümkün olduğunca frontend + küçük API eklemesi.
- Hesap/çoklu-kullanıcı, bulut senkron (LAN + paylaşılan SQLite yeterli).

## Çözülen dertler
1. **Kaldığın yeri kaybetme:** bölüm ortasında kapatınca aynı yere dönememe.
2. **Geri gidememe:** sadece "sonraki bölüm" var; yanlış bölüme girince geri yok.
3. **Uzun kitapta bölüm bulma:** bölüm listesi uzayınca aranan bölüme inememe.
4. **Okuma konforu:** satır aralığı/kenar boşluğu/tema seçeneği dar.

---

## Kapsam (özellikler)

### E1 — Bölüm-içi okuma ilerlemesi
- Okuyucuda kaydırma konumunu bölüm URL'i başına `localStorage`'a yaz (cihaz-yerel;
  her cihaz kendi okuma noktasını tutar). Bölüm tekrar açılınca aynı konuma dön.
- Okuyucu üstünde ince ilerleme çubuğu (% kaydırma). Sadece `transform`/`width`
  yerine `transform: scaleX()` ile compositor-dostu.
- Etki alanı: `app/web/app.js`, `app/web/style.css`. Backend yok.

### E2 — Önceki bölüm düğmesi
- Okuyucu alt çubuğuna "← ÖNCEKİ BÖLÜM". 
- `prev_url` kaynağı: sayfadan "previous chapter" linkini, `next` gibi `fetch._parse`
  içinde çıkar; `SITES`/`GENERIC_SITE`'a `prev` selektörleri ekle.
- Kalıcılık: `cache` tablosuna `prev_url` sütunu eklenir (yeni sütun; eski satırlar
  `NULL`). Migration: `ALTER TABLE ... ADD COLUMN prev_url TEXT` idempotent guard ile.
- Etki alanı: `app/core/fetch.py`, `app/core/cache.py`, `app/server.py` (payload),
  `app/web/app.js`, `app/web/index.html`.

### E3 — Bölüme atlama / arama
- Kitap görünümünde bölüm listesinin üstüne arama kutusu; istemci-tarafı filtre
  (başlık + bölüm no). Yeni API yok; `chapterList` zaten yüklü.
- Etki alanı: `app/web/index.html`, `app/web/app.js`, `app/web/style.css`.

### E4 — Okuma ayarları genişletme
- Ayar paneline: satır aralığı (sık/normal/seyrek), kenar boşluğu (dar/normal/geniş),
  sepya tema seçeneği. Tümü CSS değişkeni + `localStorage` (mevcut `settings` objesi
  genişletilir; geriye-uyumlu defaultlar).
- Etki alanı: `app/web/app.js`, `app/web/style.css`, `app/web/index.html`.

---

## Mevcut ne var (yeniden kullan)
- `loadChapter`/`renderChapter` (app.js): okuyucu akışı — E1/E2 buraya bağlanır.
- `settings` + `applySettings`/`saveSettings` (app.js): E4 mevcut desene eklenir.
- `_next_chapter_url` (fetch.py): E2 prev için birebir simetrik yardımcı yazılır.
- `cache.save_chapter`/`get_chapter`: E2 prev_url buraya eklenir.
- `renderChapterList` (app.js): E3 filtresi mevcut listeyi süzer.

## Kapsam DIŞI (TODOS.md'ye)
- Kaydırmayla bölüm geçişi (swipe nav) — ayrı, gerekirse sonra.
- Sunucu-tarafı okuma konumu senkronu (cihazlar arası tam senkron) — gerekmiyor.
- Bölüm-içi tam-metin arama — kapsam dışı.

## Test planı
- Backend (yeni saf mantık): `fetch` prev-link çıkarımı için pytest
  (`_prev_chapter_url`/`_parse` prev alanı), `cache` prev_url yaz/oku + migration
  idempotensi. Test altyapısı yok → `pytest` + küçük `tests/` kurulur.
- Frontend (E1/E3/E4 saf-frontend): manuel QA — telefon + masaüstü, açık/koyu/sepya,
  kaldığın yere dönüş, filtre, prev/next sınır durumları (ilk/son bölüm).

## Riskler
1. **cache şema değişimi (E2):** mevcut `chapters.db`'yi bozma. Azaltma: yalnızca
   `ADD COLUMN`, idempotent guard, eski satırlar `NULL` (geriye uyumlu).
2. **prev link site-özel kırılganlık:** bazı sayfalarda prev linki olmayabilir →
   düğme pasif. Azaltma: `next` ile aynı en-iyi-çaba deseni, yoksa gizle.
3. **localStorage anahtar şişmesi (E1):** her bölüm için scroll anahtarı birikir.
   Azaltma: tek JSON objesi + son ~500 bölümle sınırla (LRU benzeri budama).

## İlk somut adım
E1 (scroll persist + ilerleme çubuğu) — tamamen frontend, en hızlı hissedilen kazanç.
Sonra E3 (filtre), E4 (ayarlar), en son E2 (prev — şema dokunuşu içerdiği için).
