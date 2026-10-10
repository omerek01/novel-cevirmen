# Bölüm bağlamlı çeviri uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Görevleri bu oturumda sırayla uygula; sonunda bağımsız bütün dal incelemesi yap.

**Goal:** Kaynak bağlı özet/terim analizi, yalnız çeviri üretimi ve onarımın kanıt kaydı.
**Architecture:** ceviri_baglam analiz/özet; ceviri_izleri sınırlı SQLite kayıtları; translate mevcut akış entegrasyonu; cache/pipeline N-1 kaynağı.
**Tech Stack:** Python, FastAPI, SQLite, mevcut SDK, pytest/Playwright; yeni bağımlılık yok.
**Spec:** ../specs/2026-10-10-roman-baglam-design.md

## Global Constraints

- 7cdc6a0 tabanı; ayrı roman-baglam dalı. Ana çalışma ağacı korunur.
- Kod/yorum/belge Türkçe; kontrol merkezine dosya yazımı yok.
- Seçili zincir korunur; cache okuması ücretsiz; yeni ücretli hakem otomatik seçilmez.
- Kaynak özete üstün; tam N-1; onaysız aday kalıcı kural değildir.
- URL başına 5 iz; gizli anahtar yok; başarısız kalite kapısı eski chapter/arşivi değiştirmez.

## Review Focus

1. Önceki URL yanlış kitap/gelecek/boşluk: yalnız gerçek N-1 kullanılır; Türkçe son bağlamı da süzülür.
2. Önceki kaynak değişir: hash uyumsuzluğunda özet kullanılmaz.
3. Model sahte alıntı, yanlış JSON/sınır veya eksik STOP verir: analiz kabul edilmez.
4. Onarım doğru anlamı kötüleştirir: ham ve onarım önce/sonrası görülebilir, üslup otomatik uygulanmaz.
5. Eşzamanlı çeviriler: ContextVar bağlamları birbirine karışmaz.

### Task 1: Bölüm analizi
Files: app/core/ceviri_baglam.py; tests/test_roman_baglam.py.
Interface: analiz(text,sozluk,kosullar,onceki_ozet,uret)->dict; ozetle(text,uret)->dict.
- [x] Kaynak/alıntı/sınır/STOP/aktif terim üstünlüğü testlerini önce çalıştır, RED.
- [x] En fazla 6 madde/1800 karakter/30 terim ve tamamlanmış kaynak bağlı analiz uygula, GREEN.
- [x] Ayrı analiz, kısa Türkçe stil ve translation-only talimatını oluştur.

### Task 2: N-1 ve iz deposu
Files: cache.py, ceviri_izleri.py, tests/test_roman_baglam.py, scripts/ceviri_iz_incele.py.
Interfaces: onceki_kaynak(slug,prev_url,no); ozet_oku/yaz; iz_kaydet/oku.
- [x] Yanlış kitap/gelecek/boşluk/hash/son5 deneme testleri RED→GREEN.
- [x] İki eklemeli SQLite tablo; başarısız iz kayıtları; mevcut DB korunur.
- [x] Salt-okunur teknik inceleme aracı.

### Task 3: Çeviri entegrasyonu
Files: translate.py, pipeline.py, .env.example, tests/conftest.py, tests/test_roman_baglam_akis.py.
Interface: mevcut translate_chapter + book_slug/bolum_url/onceki_bolum keyword-only.
- [x] Ayrı analiz→üretim, trace, eski yol, failed run ve pipeline testleri RED→GREEN.
- [x] Önceki kaynağı özetle/önbellekle; aktif kayıtları koru; yalnız kullanılan adayı bekleme kapısına gönder.
- [x] Mevcut tercüme kurallarını ve yedek zinciri koru; ret turunda da aynı translation-only talimatı kullan.

### Task 4: Kalite boyutları
Files: ceviri_kalite.py, tests/test_ceviri_kalite.py, docs/CEVIRI-KALITE.md.
- [x] Ayrı anlam/akıcılık, üslup otomatik dışlama ve rejected repair izi testleri RED→GREEN.
- [x] v2 boyutlar/kanıt; okuyucu payload'ında yalnız küçük rapor.
- [ ] Dokümantasyon ve tamamlanmış çalışma commit'i.

### Task 5: Ölçüm ve son doğrulama
Files: scripts/roman_baglam_kiyas.py, tests/test_roman_baglam_kiyas.py, reports/roman-baglam-uygulama/RAPOR.md.
- [x] Sabit kaynak/model/sözlük snapshotı ve yedeksiz deney testleri RED→GREEN.
- [ ] 961/957/ikinci kitap: analiz açık-kapalı; aynı taslak üzerinde onarım öncesi-sonrası; kalite/süre/token sınırlamalarını raporla.
- [ ] Tam pytest tests -q; NOVEL_TARAYICI_TEST=1 pytest tests/tarayici.
- [ ] Bağımsız son inceleme ve bulguları giderme; yerel commit. Push/dağıtım ayrı onay bekler.
