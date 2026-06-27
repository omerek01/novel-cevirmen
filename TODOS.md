# TODOS

> /autoplan tarafından ertelenen kapsam (Okuma Deneyimi / Faz 4 incelemesi).

## Okuma deneyimi — ertelenenler
- [ ] Swipe ile bölüm geçişi (mobil sağa/sola kaydır → prev/next).
- [ ] Bölüm-içi tam-metin arama.
- [ ] E4 kenar boşluğu (margin) ayarı — panel sadeliği için ertelendi.
- [ ] Sepya tema — eklenince `toggleTheme` → `setTheme(name)` + segmented control
      (Açık/Sepya/Koyu) refactor'u; `[data-theme="sepia"]` için kontrast-doğrulanmış
      (≥4.5:1) CSS değişken seti gerekir.

## Dayanıklılık (tema dışı, ayrı faz)
- [ ] fetch/çeviri kırılınca okuyucuda zengin hata durumu + son başarılı bölümün
      cache'ten gösterimi (CEO önerisi).
- [ ] Cloudflare çekme dayanıklılığı: lncrawl/FlareSolverr güncel tut; çekme
      başarısızlığında yeniden deneme.
- [ ] Toplu çeviriyi sunucu-tarafı arka plan işine taşı (sekme kapansa da sürsün).

## Genel teknik borç
- [ ] `DB_PATH` modül-sabiti test için enjekte edilebilir değil (monkeypatch gerekiyor).
- [ ] Backend genelinde test kapsamını artır (merge_books, translate JSON kurtarma).
