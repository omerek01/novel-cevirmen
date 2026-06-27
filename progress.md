# Gelişme Raporu: progress.md

Bu dosya Novel Çevirmen uygulamasında yapılan değişiklikleri, test sonuçlarını ve sürüm geçmişini özetler.

## Yapılan İşler

1. **Scroll Oranı Entegrasyonu (E1):**
   - Frontend üzerinde `scrollY` oranı hesaplandı, throttle edilerek `POST /api/book/:slug/position` API'sine yönlendirildi.
   - `books` veritabanı şemasına `current_ratio` alanı eklendi ve migration tamamlandı.

2. **Geriye Doğru Navigasyon (E2):**
   - Okuyucu alt çubuğuna "← Önceki Bölüm" eklendi.
   - Sayfa çekim mantığı `_nav_chapter_url` fonksiyonu ile birleştirilerek hem `next` hem `prev` bağlantılarını ortak ele alacak şekilde genelleştirildi.
   - `chapters` tablosuna `prev_url` kolonu eklendi.

3. **Bölüm Arama ve Filtreleme (E3):**
   - Kitap arayüzünde hızlı arama girdisi oluşturuldu. JavaScript tarafında anlık süzme yapacak `filterChapters` eklendi.

4. **Satır Aralığı Stepper (E4):**
   - Kullanıcının okuma rahatlığı için CSS değişkeni `--reading-line-height` üzerinden üç kademeli satır aralığı ayarı eklendi.

5. **Test, Hata Giderme ve Doğrulama:**
   - 7 adet pytest test dosyası oluşturuldu.
   - Toplam **36/36** test başarıyla tamamlandı.
   - Kitap okunurken aşağı kaydırınca ayarlar panelinin yukarıda kaybolması (static pozisyon problemi) giderildi. `.settings-panel` sınıfı `position: sticky` ve `top: calc(...)` olacak şekilde güncellendi.
   - `sw.js` dosyası cache sürümü `novellink-v15` değerine yükseltildi.

## En Son Test Çıktısı (2026-06-27)
```
collected 36 items

tests\test_api.py ....                                                   [ 11%]
tests\test_cache_migration.py ....                                       [ 22%]
tests\test_fetch_nav.py ........                                         [ 44%]
tests\test_library_position.py .......                                   [ 63%]
tests\test_merge_books.py ....                                           [ 75%]
tests\test_translate_recovery.py .........                               [100%]

======================== 36 passed, 1 warning in 1.99s ========================
```
* **FastAPI Sunucu Testi:** localhost:8000 üzerinden uçtan uca `/api/books` test edilmiş, 200 OK koduyla şemadaki yeni `current_ratio` alanları doğrulanmıştır.
