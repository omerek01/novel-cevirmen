# Güncel Türkçe ve düzenleme sonrası anlam koruması

14 Ekim 2026, Türkiye saati. Kullanıcı yetkisi: “düzeltene kadar devam et sonra canlıya al”.
İlk araştırma ve üretime alınmayan aday: [RAPOR.md](RAPOR.md).

## Yapılan düzeltme

- Çeviri, cilalama, kaynak denetimi ve onarım, `core/ceviri_dili.py` içindeki
  aynı güncel ve anlaşılır Türkçe ölçütünü kullanır. Gündelik sesi kitabi
  karşılıkla ağırlaştırma somut kusurdur. Örnekler dil düzeyini açıklamak içindir;
  otomatik sözcük değiştirme/yasak listesi yoktur. Kaynağın bilerek resmî sesi ve
  dünya terimleri korunur. Beklenenden fazlasını yapma anlamı yalnız hevesli
  karakter özelliğine indirgenmez.
- Cilalama yalnız somut kusuru en küçük değişiklikle onarmayı ister. Cilalama
  öncesi metnin kopyası, değişen paragraflarda aynı kalite denetimi çağrısına
  eklenir. Önceki metin doğru kabul edilmez; İngilizce kaynak son dayanaktır.
- Onarım doğrulaması bir önceki kabul edilmiş metni de görür. Kaybolan doğru
  ayrıntının önceki metindeki birebir kanıtı varsa, değişmemiş yakın sözcük
  nedeniyle yeni eksiltme yanlışlıkla kabul edilmez. Böyle bir bulgu adayı
  reddeder. Uydurma veya adayda hâlâ bulunan alıntı bu kabul kararını değiştirmez.
- Yeni sürekli çağrı veya model seçimi eklenmedi. Seçilmiş sağlayıcı zinciri,
  STOP, paragraf/ad/sözlük korumaları ve kaydet–işaretle politikası korunur.

## Ölçüm ve sınırlılıkları

İlk uygulama pilotunda ortak ölçüt tek başına yetmedi; 3.8 Flash, gayretkeş
karşılığını üç koşuda da bırakabildi. O aday elendi. Somut dil örnekleri eklendikten
sonra aynı 11 paragrafta kayıtlı kusurları onarma ve cilalama+kaliteyi iki tekrar
çalıştırma koşullarının üçünde de gayretkeş giderildi; yiğit ve binlik denizci ölçeği
korundu. Bütün kabul edilen çağrılar STOP ile tamamlandı. İki çıktı hevesli kullandığı
için beklentiyi aşma anlamı ayrıca netleştirilerek tam bölüm ölçümüne geçildi.

Son ölçüm yeni gerçek `translate_chapter` akışını kullandı. Canlı kaynaktan ve
sözlükten salt okunur anlık görüntü alındı; modüller ayrı süreçte yüklenip geçici
veritabanında çalıştırıldı. Deney izi/kota günlükleri de geçici veritabanındaydı.
Canlı bölüm ve sözlüğe deney sırasında yazılmadı. Tam bölüm sonuçları ve dağıtım
kanıtı, aşağıda tamamlanan çıktılardan kaydedilir.

Bu küçük örneklem bir Türkçe roman değerlendirme veri seti veya insan altın
çevirisi değildir. Bilinen regresyonun somut örnek olarak talimata alınması,
kelimeyi daha önce görmemiş modelin bağımsız başarısı sayılmaz. Tam bölümler ve
başka kitap kontrolü bu dar örneğin dışındaki akışı sınar; bütün gelecek
çevirilerin hatasız olacağı iddiası yoktur.

## Yazılım doğrulaması

- Altı yeni davranış testi önce hata verdi: önceki metin aktarımı, hizalama,
  onarımın önceki metni görmesi, gerçek çeviri akışındaki aktarım ve yeni
  eksiltmenin kabul edilmemesi/uydurma kayıp kanıtının etkisizliği.
- Son çevrimdışı takım: **1190 geçti, 1 atlandı**. Son hedefli kontrol:
  kalite/cilalama/JS çalıştırıcısı **56 geçti**. Mevcut FastAPI/Pillow
  kullanımdan kalkma uyarıları kaldı.
- Tarayıcı: ilk takım **98 geçti, 1 kaldı** (195 px dar ekran taşma kontrolü).
  İlgili dosyanın yeniden koşusunda **3 geçti**. Arayüz dosyası değiştirilmedi;
  kabuk v127. İlk hatanın kök nedeni ayrıca kanıtlanmadı.
- Bağımsız kod incelemesinde bulunan yeni eksiltme kabul boşluğu, kırmızı/yeşil
  regresyonla düzeltildi; ikinci incelemede önemli açık bulgu kalmadı.

## Tam bölüm sonuçları ve dağıtım hazırlığı

| Kitap / bölüm | Hizalı paragraf | Kalite sonucu | Onarılan paragraf (0 tabanlı) | Çağrı | Süre |
|---|---:|---|---|---:|---:|
| Shadow Slave 983 | 36 | Denetlendi, şüphe 0 | Yok | 3 | 98,5 sn |
| Shadow Slave 984 | 41 | Denetlendi, şüphe 0 | 6 | 5 | 116,0 sn |
| RSSG 1880 | 53 | Denetlendi, şüphe 0 | Yok | 3 | 156,6 sn |

Toplam 130 hizalı paragraf, 11 STOP yanıtı. Kaynak ve çeviri SHA-256 değerleri
doğrulandı. 983/21 artık **“Beklenenden bu kadar fazlasını yapmanı kim istedi ki
senden?”** diyor. 983/17'de yiğit, 983/24'te birkaç bin asker/bir iki bin denizci
korunuyor. Bu üç yer ayrıca kaynaktan incelendi. Modelin sıfır bulgu vermesi
tek başına bütün bölümün insan tarafından doğrulandığı anlamına gelmez.

984 ve RSSG deneyi üretim verisine uygulanmayacak; kontrol için çalıştırıldı.
983'ün doğrulanmış çevirisi mevcut kaynak ve eski çevirinin aynı kaldığı
kontrol edilerek, eski metin arşivlenerek aktarılacak. Sözlük ve okuma konumu
değiştirilmeyecek. Kullanıcı yetkisi bu düzeltmenin push ve canlıya geçişini kapsar.

Dağıtım öncesi SQLite backup:
`backups/chapters-dil-duzeltme-20261013T212631Z.db`, bütünlük **ok**.
Çalışan servis `/home/OMEREK/novel-cevirmen-sozluk`; önceki sürüm `12612d2`.
Ana ağacın Git durumu ve dört değişik dosyanın hash'i ayrıca korunmak üzere
`backups/dil-duzeltme-oncesi-20261013T212631Z.json` içine kaydedildi.
Etkin toplu iş yoktu; restart öncesinde tekrar kontrol edilecek.

Bu dosya push öncesi doğrulamayı kaydeder. Gerçek dağıtım sonucu sunucudaki
`backups/` kaydına ve NovelLink `context/proje-ozeti.md` güncel canlı bölümüne
işlenir. Metinsiz ölçüm özeti: [duzeltme-ozet.json](duzeltme-ozet.json).
