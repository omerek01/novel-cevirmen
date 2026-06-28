# Faz 5: Dayanıklılık — kısmi tamamlama kaydı

> Bu plan tamamen uygulanmadı. **Sevk edilen** kısım aşağıda (commit `9a89db5`).
> Geri kalan kapsam (bulk job kalıcılığı vb.) **bilinçli olarak düşürüldü** —
> uygulama şu an istenildiği gibi çalışıyor. Kalan işler gerekirse **ayrı, yeni
> bir planda** ele alınacak. Tam orijinal plan + autoplan inceleme raporu git
> geçmişinde (commit `3b95b3a` / `bc676d3`) korunuyor.

## Sevk edilen (commit `9a89db5`)

### R1 — Reader graceful-failure UX
Çekim/çeviri patlayınca okunan bölüm ve footer korunur; footer-üstü sticky
`#readerError` kartı. Sınıfa-göre birincil eylem (CF → "nasıl çözülür" rehberi,
OriginError → "bekle", geçici/network → "tekrar dene"), cihaz-farkında CF mesajı
(telefon vs masaüstü), boş/kısa çeviri için boş-durum kartı. a11y: `role="alert"`,
≥44px dokunma hedefi, `prefers-reduced-motion`, `aria-live`. Nav butonunda spinner
+ yükleme penceresinde nav/swipe kilidi (`isNavigating`).
Etki: `app/web/app.js`, `app/web/index.html`, `app/web/style.css`.

### R3-tip (backend) — tipli çekme hatası
`fetch.py`'ye `class CloudflareChallenge(FetchError)`; `_extract_html` challenge
dalında onu fırlatır. `server.py` tipli hata yanıtları döndürür
(`CloudflareChallenge` / `OriginError` / `FetchError` / `TranslateError`) `error_class`
alanıyla → frontend kırılgan string-eşleştirmesi yapmadan sınıfa göre davranır.
Etki: `app/core/fetch.py`, `app/server.py`.

### R5-WAL — merkezi WAL bağlantısı
`db.connect()` = `journal_mode=WAL` + `busy_timeout=10000`; `cache.py` onu kullanır.
Eşzamanlı yazar + telefon polling'inde `database is locked` riskini azaltır.
Etki: `app/core/db.py`, `app/core/cache.py`.

54/54 test geçiyor.

## Düşürülen (yeni planda yeniden değerlendirilecek)
- **R2** — bulk job kalıcılığı (SQLite `jobs` tablosu, checkpoint, single-flight,
  açılışta auto-resume, `GET /api/book/{slug}/job` keşif endpoint'i). Mevcut bellek-içi
  `jobs.py` yeterli görülüyor; kalıcılık gerektiğinde ayrı planlanacak.
- **R3 (kalan)** — job `paused` durumu + restart'sız `POST /api/clearance/refresh`.
- **R4** — job lifecycle yapısal log'u.
- **Rozet** — kütüphane kartında job durum rozeti + "Devam et" + tamamlanma bildirimi.
- **QA** — R2/R3/R4 için `tests/test_jobs.py` / `test_pipeline.py` / `test_db_wal.py`.
