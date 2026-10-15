# Gerçek Ad politikası — Claude'dan devralma

Tarih: 2026-10-15. Çalışma ağacı: `.worktrees/roman-baglam`.

## Sonuç

Büyü'nün verdiği anlamlı **Gerçek Ad (True Name) Türkçe**, kişinin kendi adı
İngilizce yazılır. Claude'un `cf61873` commit'i çeviri, terim önerisi ve sınıflama
istemlerini değiştirmiş; mevcut sözlük düzeltmesine geçerken oturum limiti dolmuştu.

Canlı sözlükte iki kayıt mevcut API üzerinden, görülen `taban_surum` ile düzeltildi:

| Kaynak | Önceki karşılık | Yeni karşılık | Yeni tür | Kaynak kanıtı |
|---|---|---|---|---|
| Nightingale | Nightingale | Bülbül | Gerçek adı | 373 ve 378. bölüm |
| Sky Tide | Sky Tide | Gök Gelgiti | Gerçek adı | 403. bölüm |

`Gerçek adı` türüne `turkce` politikası yazıldı. Diğer dört Gerçek Ad zaten Türkçeydi:
Lost from Light → Işıktan Mahrum; Changing Star → Değişen Yıldız;
Raised by Wolves → Kurtlar Tarafından Büyütülen; Song of the Fallen → Düşmüşlerin Şarkısı.
Sunny, Sunless, Nephis, Kai, Cassie, Effie ve Tyris aynen İngilizce kaldı.
İki değiştirilen kaydın kimliği, ilk bölümü ve koşulu korundu; sözlük geçmişinde iki
`manual/guncelle` kaydı doğrulandı. Eski bölüm çevirileri değiştirilmedi.

## Güvenlik ve kapsam

Canlı veritabanı SQLite backup ile önceden yedeklendi; bütünlük `ok`:
`/home/OMEREK/novel-cevirmen-sozluk/backups/chapters-gercek-ad-20261015T132443Z.db`.
Aynı adlı `.json` dosyası önceki/sonraki iki sözlük kaydını ve doğrulama özetini tutar.
Kontrol sırasında görev dışında Ascended inceleme durumu ve Nightmare koşulunda
eşzamanlı değişiklikler görüldü; bunlara müdahale edilmedi. Başlangıç yedeğiyle bütün
sözlüğün son hâlinin aynı olduğu iddia edilmez.

Kod düzeltmeleri:

- Otomatik sözlük doğrulaması da ortak `translate.GERCEK_AD_KURALI`nı kullanır.
- Ad tutarlılığı denetimi, açık Türkçe tür politikasıyla çevrilen adı yanlış
  tutarsızlık saymaz; kişinin kendi adının yanlış Türkçeleşmesi hâlâ işaretlenir.
- Grafik nedenleri önbelleği politika ekleme, değiştirme ve kaldırmayı imzasında izler.
  Bu bağımlılık bağımsız incelemede bulundu ve gerçek inceleme listesi regresyonuyla
  düzeltildi; ikinci incelemede önemli açık bulunmadı.

## Doğrulama ve dağıtım

Regresyonlar düzeltme öncesi başarısız, sonrasında başarılı görüldü. Son tam
çevrimdışı koşu: **1301 geçti, 1 atlandı**; mevcut FastAPI/Pillow kullanımdan kaldırma
uyarıları var. İlk tam tarayıcı koşusu 104 geçti. Önbellek düzeltmesinden sonraki tam
koşu 103 geçti, `test_dar_ekran.py::test_kitap_sozluk_ve_terim_paneli_yatay_tasmaz[zoom200]`
sözlükte 5 px yatay taşma nedeniyle kaldı; aynı dosya ayrı tekrarda **3/3 geçti**.
Bu testin kararsızlığı proje bağlamında önceden kayıtlı; bu görevde kök nedeni
kanıtlanmadı veya arayüz değiştirilmedi. Son tam tarayıcı koşusu tamamen yeşil değildir.
Yeni istemle gerçek model çağrısı ve gerçek Android cihaz denemesi yapılmadı.
Sözlük verisi mevcut canlı uygulamanın uçlarıyla yazıldı; kod push edilmedi,
servis yeniden başlatılmadı. Kullanıcı kodu canlıya almayı sonraya bıraktı.
Ana çalışma ağacındaki eski işler ve Claude'un önceki dört commit'i korundu.
