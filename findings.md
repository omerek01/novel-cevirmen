# Teknik Bulgular ve Kısıtlar: findings.md

Bu dosya Novel Çevirmen projesinin geliştirilmesi sırasında keşfedilen teknik kısıtları, kararları ve bulguları içerir.

## Keşfedilen Bulgular

1. **Scroll Konumu Senkronizasyon Yarışı (Scroll Restore Race):**
   - Sayfa yüklendiğinde veya bölüm değiştirildiğinde programatik `scrollTo(0,0)` çağrısı, scroll dinleyicisini tetikleyerek konumu sıfırlıyordu.
   - **Çözüm:** Scroll geri yüklenirken `isRestoring` bayrağı kullanılarak kayıt işlemi engellendi. Geri yükleme `requestAnimationFrame` sonrasında (DOM tamamen render edildikten sonra) tetiklenecek şekilde optimize edildi.

2. **iOS Zoom ve Mobil Arama Kutusunun Davranışı:**
   - Safari mobil tarayıcılarda arama kutularına odaklanıldığında, font boyutu `1rem` (16px) değerinden küçükse tarayıcı otomatik yakınlaştırma (zoom) yapıyor ve mobil görünümü bozuyordu.
   - **Çözüm:** Arama kutusu girdisi `font-size: 1rem` olarak ayarlanarak mobil yakınlaştırma (iOS zoom) engellendi.

3. **Veritabanı Migration İnvaryantları:**
   - SQLite veritabanında `CREATE TABLE IF NOT EXISTS` komutu mevcut tablolara yeni sütun eklemez.
   - **Çözüm:** `db.ensure_column` yardımıyla `PRAGMA table_info` kontrolü yapılıp eksik sütunlar için dinamik `ALTER TABLE ADD COLUMN` çağrısı gerçekleştirildi. Bu işlem tamamen idempotent hale getirildi.

## Mimari Kısıtlar

* **LAN İçi SQLite Paylaşımı:** Uygulama tek kullanıcılı bir kişisel okuyucudur, bu nedenle çoklu kullanıcı desteği veya bulut senkronizasyonu yerine LAN üzerinde paylaşılan bir SQLite dosyası tercih edilmiştir.
* **Service Worker Önbellek Yönetimi:** Çevrimdışı okuma desteğini sağlamak adına `sw.js` cache sürüm kontrolü (`novellink-v14`) kritik önem taşır. Yeni bir frontend paketi yayınlandığında sürüm numarasının artırılması zorunludur.
