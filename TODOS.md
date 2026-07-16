# TODOS

> Güncelleme (2026-07-16): Önceki listedeki tüm ertelenmiş maddeler
> `faz-sonraki-plan` dalında tamamlandı (aşağıda kanıtla). Gerçek kalan/sıradaki
> iş en altta.

## Tamamlandı — faz-sonraki-plan

- [x] Swipe ile bölüm geçişi (mobil sağa/sola) — `app/web/app.js` (touchstart, ~satır 1065).
- [x] Bölüm-içi tam-metin arama — `app/web/app.js` (`openFind`/`runFind`/`findMatches`).
- [x] Kenar boşluğu (margin) ayarı — `style.css` `--reading-margin` + ayar paneli `data-mg`.
- [x] Sepya tema + Açık/Sepya/Koyu segmented control — `style.css` `[data-theme="sepia"]`, `setTheme`.
- [x] Okuyucuda graceful hata durumu (kırılınca mevcut bölüm korunur + hata kartı) — `app.js` `renderError`, tipli hatalar.
- [x] Çekme yeniden-deneme (üstel geri-çekilme) + CDP gerçek-Chrome yolu — `app/core/fetch.py`.
- [x] Sunucu-taraflı arka plan toplu çeviri (sekme kapansa da sürer) — `app/core/jobs.py`.
- [x] `db_path()` test-enjekte edilebilir (`NOVEL_DB_PATH`) — `app/core/db.py`.
- [x] merge_books + translate JSON-kurtarma testleri — `tests/test_merge_books.py`, `tests/test_translate_recovery.py`.

## Kalan / sıradaki

### Test kapsamı — dedicated testi olmayan backend modülleri
- [ ] `app/core/epub_export.py` — ePub üretimi (cache'ten bölüm seçimi, boş aralık → ("", b""), dosya adı aralığı).
- [ ] `app/core/jobs.py` — toplu iş yaşam döngüsü (pipeline mock'lanarak: done/stopped/error, next_url zinciri, `_prune`).
- [ ] `app/core/pipeline.py` — `get_or_translate` (cache-hit API'siz, refresh, want_source yükseltme; fetch/translate mock).

### QA'de bulunan kozmetik (2026-07-15 raporu; kod hatası değil, tercih meselesi)
- [ ] İngilizce başlıklarda Türkçe büyük-harf noktalı-İ ("REİNCARNATİON") — spine `text-transform:uppercase`.
- [ ] Reincarnation bölüm no 1788↔1768 gösterim tutarsızlığı (novelfull URL-slug vs sayfa başlığı).

### Dayanıklılık — bilinçli düşürülen kapsam (bkz. PLAN-dayaniklilik.md "Düşürülen")
- [ ] Bulk job kalıcılığı (SQLite `jobs` tablosu, checkpoint, açılışta auto-resume, keşif endpoint'i).
- [ ] Job `paused` durumu + restart'sız `POST /api/clearance/refresh`.
- [ ] Kütüphane kartında job durum rozeti + "Devam et" + tamamlanma bildirimi.
