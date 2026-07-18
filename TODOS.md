# TODOS

> Güncelleme (2026-07-16): Kalan iş büyük ölçüde codex ile uygulandı, incelenip
> düzeltildi ve commit'lendi (`30d0a99`, `da0afd0`). Kalan tek küçük madde en altta.

## Tamamlandı — faz-sonraki-plan (okuma deneyimi + dayanıklılık)

- [x] Swipe ile bölüm geçişi — `app/web/app.js`.
- [x] Bölüm-içi tam-metin arama — `app/web/app.js` (`openFind`/`runFind`).
- [x] Kenar boşluğu (margin) ayarı — `style.css` `--reading-margin` + `data-mg`.
- [x] Sepya tema + Açık/Sepya/Koyu segmented control — `style.css` `[data-theme="sepia"]`.
- [x] Okuyucuda graceful hata durumu — `app.js` `renderError`, tipli hatalar.
- [x] Çekme yeniden-deneme + CDP gerçek-Chrome yolu — `app/core/fetch.py`.
- [x] Sunucu-taraflı arka plan toplu çeviri — `app/core/jobs.py`.
- [x] `db_path()` test-enjekte edilebilir — `app/core/db.py`.
- [x] Çevrimdışı "kaldığın yer" (resume + kütüphane etiketi) — `app.js` `resolveResume`.

## Tamamlandı — codex ile uygulandı, incelenip düzeltildi

- [x] Test kapsamı: `epub_export`, `jobs`, `pipeline` için pytest (çevrimdışı, mock'lu) — 74/74 yeşil.
- [x] QA: İngilizce başlıklarda noktalı-İ giderildi (`lang="en"`); bölüm no güvenilir sayfa başlığını URL'ye tercih eder.
- [x] Bulk job KALICILIĞI: SQLite `jobs` tablosu + her bölümde `next_url` checkpoint + restart'ta auto-resume (single-flight) + `GET /api/book/{slug}/job` keşif.
- [x] Kütüphane sırtında job durum rozeti (N/total · devam et, bitti, hata) + çalışan işe yeniden bağlanma.
- [x] Restart'sız `POST /api/clearance/refresh` (Cloudflare oturumu tazele) + ayar düğmesi.
- [x] ePub numarasız-bölümlü kitapları da paketler (regresyon düzeltmesi).

> İnceleme sonrası düzeltilen üç sorun: (1) mevcut DB'deki eski uyumsuz `jobs`
> tablosu startup'ı çökertiyordu → migration; (2) `_set`/`stop` persist yarışı →
> kilit içine alındı; (3) ePub numarasız-kitap regresyonu.

## Kalan / sıradaki

- [ ] İnteraktif "duraklat" (paused) durumu: iş restart'sız duraklatılıp sürdürülebilsin.
      (Şu an: `stop` kalıcı biter; yarım iş yalnız sunucu restart'ında otomatik sürer.)

## Kaynak Çeşitliliği Fazı — onaylı plan (2026-07-18, /autoplan)

> Plan: `~/.gstack/projects/novel-cevirmen/OMEREK-faz-sonraki-plan-design-20260718-000427.md`
> Test planı: aynı dizinde `...-test-plan-20260718.md`. Sevk sırası planın
> "Faz 4 Final Kapı" bölümünde; 22 görev `tasks-*-review-*.jsonl` dosyalarında.

Fazdan bilinçli ERTELENENLER (inceleme kararlarıyla):
- [ ] Okuma geçmişi listesi UI (reading_log'un doğal ekranı)
- [ ] Ayarlarda "sistem" bloğu (son kontrol, bekleyen işler, cache boyutu)
- [ ] library/glossary bağlantılarını `db.connect()`'e taşı (WAL/busy_timeout tutarlılığı)
- [ ] Tam kaynak/revizyon veri modeli (¶-yaması vs refresh çakışması kalıcı çözümü)
- [ ] Bölüm-bazlı has_new takibi (discovered_at/read_at)
- [ ] Kapak görseli çekme (og:image)
- [ ] Tek "İçe Aktar" kapısı UI (otomatik tür algılama — Yaklaşım C)
- [ ] Yerleşik TTS (UC2 ön-deneyi ePub+harici okuyucuyu yeterli bulursa burada kalır)
- [ ] Manga tam entegrasyonu / "çevrilmiş görsel klasörü içe aktar" (tracer go derse)
- [ ] LAN erişim koruması (token) — dosya yükleme yüzeyi büyüdü, öncelik arttı

- [ ] QA bulgusu (2026-07-19, telefon): geri jesti tutarsiz — bazen bir geri, bazen anasayfa, bazen uygulamadan cikis. navigate()/popstate/history katmani incelenecek (app.js applyNavState + history.replaceState cagrilari; olasi suclu: replaceState'in push yerine kullanildigi/atlandigi gecisler).
