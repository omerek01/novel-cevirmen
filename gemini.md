# Proje Anayasası: NOVELLINK (gemini.md)

Bu dosya Novel Çevirmen uygulamasının veri şemalarını, mimari kurallarını ve teknik davranış invaryantlarını tanımlar.

## 1. Veri Şemaları (SQLite Database)

Veritabanı yolu varsayılan olarak `db_path()` aracılığıyla belirlenen dinamik bir SQLite dosyasıdır. İki ana tablo ve migration'lar mevcuttur.

### `books` Tablosu
Kitap listesi ve cihazlar arası paylaşılan anlık okuma konumları bu tabloda saklanır.
* `slug` (TEXT PRIMARY KEY): Romanın benzersiz kimliği.
* `title` (TEXT): Romanın adı.
* `current_url` (TEXT): En son okunan bölümün URL'i.
* `current_title` (TEXT): En son okunan bölümün başlığı.
* `chapter_no` (INTEGER): En son okunan bölüm numarası.
* `updated_at` (REAL): Son güncelleme zaman damgası.
* `current_ratio` (REAL): Okuma konumu oranı (0.0 ile 1.0 arası).

### `chapters` Tablosu
Çevrilen bölümlerin yerel/sunucu tarafı önbelleğidir.
* `url` (TEXT PRIMARY KEY): Bölümün orijinal web adresi.
* `book_slug` (TEXT): Kitap slug'ı.
* `book_title` (TEXT): Roman başlığı.
* `title` (TEXT): Bölüm başlığı.
* `chapter_no` (INTEGER): Bölüm numarası.
* `translation` (TEXT): Türkçe çeviri metni.
* `next_url` (TEXT): Sonraki bölümün URL'i.
* `detected_names` (TEXT): JSON formatında saptanan özel isim listesi.
* `chunk_count` (INTEGER): Çevrilen metin blok sayısı.
* `created_at` (REAL): Oluşturulma zamanı.
* `prev_url` (TEXT): Önceki bölümün URL'i.

### `aliases` Tablosu
Aynı kitabın farklı sitelerdeki slug'larını kanonik bir slug ile eşler.
* `alias` (TEXT PRIMARY KEY): Alternatif slug.
* `canonical` (TEXT): Kanonik slug.

---

## 2. Mimari Kurallar ve İnvaryantlar

1. **Oran Tabanlı Scroll (scrollY ratio):**
   - Okuma konumu piksel (px) cinsinden değil, oran (`scrollY / (scrollHeight - innerHeight)`) olarak saklanır. Font veya pencere boyutları değişse de konum kaymaz.
   - Oran verisi sunucudaki `books.current_ratio` sütununda tutulur. Çevrimdışı durumlarda ise tarayıcıda `localStorage` üzerinde yedeklenir.

2. **Geri Gidebilme (Prev Chapter Nav):**
   - `chapters` tablosundaki `prev_url` sütunu ve istemci tarafındaki bölüm listesi tabanlı hibrit türetme algoritması kullanılır.
   - `prev_url` bulunamadığında veya veritabanında eski kayıtlarda `NULL` olduğunda istemci tarafındaki bölüm listesinden önceki bölüm bulunur.

3. **Geriye Dönük Uyumluluk (Idempotent Migration):**
   - Veritabanı şemasında yapılan tüm güncellemeler `db.ensure_column` aracılığıyla idempotent şekilde çalıştırılır. Mevcut DB dosyaları bozulmadan ek sütunlar (`current_ratio`, `prev_url`) eklenir.

---

## 3. Metodoloji ve GSD (Get Shit Done) Protokolü

* **Metodoloji:** Proje otomasyon ve geliştirme süreçlerinde B.L.A.S.T. protokolü kaldırılmış olup **GSD (Get Shit Done)** metodolojisi kullanılmaktadır.
* **Dil Ayarı (Language Setting):** Tüm GSD iş akışlarında, iletişimde ve oluşturulan belgelerde varsayılan dil **Türkçe (`turkish`)** olarak ayarlanmıştır (`response_language=turkish`).

