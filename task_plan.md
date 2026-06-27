# Task Plan: Okuma Deneyimi (Faz 4) - task_plan.md

Bu dosya Faz 4 geliştirme hedeflerini, kontrol listesini ve tamamlanma durumlarını içerir.

## Hedefler ve Kapsam

* [x] **E1: Bölüm-içi okuma ilerlemesi (Scroll Oranı):** Okuma konumunun piksel yerine oran bazlı saklanması. Sunucu senkronu (`books.current_ratio`) ve `localStorage` offline yedeği.
* [x] **E2: Önceki Bölüm Butonu (Prev Chapter):** Okuyucu panelinin altına "Önceki Bölüm" butonunun eklenmesi, veritabanına `prev_url` sütununun eklenmesi ve hibrit navigasyon desteği.
* [x] **E3: Bölüm Atlama ve Arama:** Kitap görünümünde bölüm listesi üstüne istemci taraflı anlık arama/filtreleme kutusunun eklenmesi.
* [x] **E4: Satır Aralığı Ayarı:** Okuma ayarları paneline satır aralığı stepper (sık/normal/seyrek) ayarının eklenmesi.

---

## Kontrol Listesi ve Geliştirme Aşamaları

### Faz 4.1: Temel Altyapı ve Veri Modeli
* [x] `books` tablosuna `current_ratio` alanı eklenmesi.
* [x] `chapters` tablosuna `prev_url` alanı eklenmesi.
* [x] `db.ensure_column` ile idempotent migration testlerinin yapılması.

### Faz 4.2: Frontend Geliştirmeleri
* [x] `app/web/app.js` dosyasında scroll oranının hesaplanması ve `throttle` edilerek sunucuya/localStorage'a yazılması.
* [x] Önceki bölüm düğmesinin eklenmesi ve CSS yerleşiminin (iki-yuvalı footer) yapılması.
* [x] Bölüm listesi arama filtresinin eklenmesi.
* [x] Satır aralığı stepper'ının ve ilgili CSS değişkenlerinin eklenmesi.

### Faz 4.3: Doğrulama ve Test
* [x] Pytest entegrasyonu ve 36 birim/entegrasyon testinin yazılması.
* [x] Uçtan uca API doğrulamasının yapılması.
* [x] `sw.js` cache sürümünün `novellink-v14` değerine yükseltilmesi.

---

## Ertelenenler (Gelecek Fazlar)
* [ ] Mobil cihazlar için kaydırarak (swipe) bölüm geçişi.
* [ ] Bölüm içi tam metin arama desteği.
* [ ] Sepya teması ( segmented control & `setTheme` refaktörü gerektirir).
* [ ] Cloudflare çekme dayanıklılığı (lncrawl / FlareSolverr).
