# Kaynak bağlı bölüm analizi ve roman çevirisi

Kullanıcı 2026-10-10 tarihinde özet/terim analizi, önceki bölüm özeti ve araştırmadaki dört önerinin planlanıp uygulanmasını istedi. Amaç kaynak anlamını korurken tutarlı ve doğal Türkçe üretmektir.

## Mimari ve kapsam

7cdc6a0 canlı tabanından ayrı roman-baglam dalı kullanılır. Ana çalışma ağacı ve sunucu korunur. Tüm dosyalar novel-cevirmen altında; NovelLink kontrol merkezine yazım yok. Seçili sağlayıcı/model zinciri değişmez, yeni ücretli hakem otomatik seçilmez. Push/dağıtım ayrı onaya bağlıdır.

Akış: N-1 kaynak bağlı özet → güncel kaynak analizi/özet/terim adayları → yalnız çeviri üretimi → mevcut deterministik kontroller → anlam/akıcılık denetimi → gerekirse tek hedefli onarım. PDF/manga HTML yolu kapsam dışıdır. Cache okuması yeni model çağrısı yapmaz. CEVIRI_ANALIZ=1 varsayılandır; 0 eski üretim yoluna döner. CEVIRI_KALITE ayrı bayraktır.

Önceki bağlam yalnız aynı kitabın tam N-1 bölümü ve doğrulanmış kaynak hash'i ile kullanılır; boşluk atlanmaz, gelecek/başka kitap kullanılmaz. Önceki Türkçe son metni de aynı kurala bağlıdır. Eski N-1 kaynağı varsa özeti bir kez tembel üretilir; kaynak değişirse eski özet kullanılmaz. Bu aşama kaynak metni çevirmez.

Analiz en fazla 6 Türkçe özet maddesi/1800 özet karakteri/30 terim üretir. Her maddede gerçek kaynak paragrafı ve birebir destek alıntısı şarttır; JSON, tip/sınır ve STOP doğrulanır. Özetin tüm iddialarının doğruluğu deterministik olarak kanıtlanamaz; bu nedenle özet talimat veya kaynak yerine geçmez. Özgün kaynak üstündür. Sıradan kelimeler terim yapılmaz. İzinli terim türleri: kisi, yer, grup, nesne, yetenek, kategori, diger.

Çeviri aşaması yalnız translation JSON alanını üretir; terim çıkarım sorumluluğu ayrı analizdedir. Mevcut ad/lakap/koşul/hiyerarşi/deyim/eksiksizlik kuralları korunur. Kısa üslup talimatı doğal Türkçe, doğru eylem/özne/olumsuzluk, deyim ve sahne bağlamını ister; ayrıntı atmayı veya yeni olay eklemeyi yasaklar. Sözlük karşılıkları temel biçimdir, Türkçe ek/kök değişimleri serbesttir. Aday karşılıklar yalnız bölüm içinde kullanılır; aktif sözlükle yazım varyantı çakışırsa aktif sözlük üstün gelir. Gerçek çeviride kullanılan adaylar mevcut bekleme/onay kapısına gider; bilgi grafiği veya kalıcı sözlük doğrudan değiştirilmez.

## Kanıt kaydı ve kalite

Her denemenin kaynak metni/hash'i, ilgili sözlük/koşullar, istem/sistem, aşama/model/model sürümü/token/bitiş bilgisi, ham çeviri, onarım önce-sonrası, bulgular, nihai durum ve hata türü saklanır. Anahtar/fabrika/env kaydedilmez. URL başına son beş deneme; başarısız deneme de tutulur. Bu iz okuyucu payload'ına eklenmez. Salt-okunur inceleme aracı sunulur.

Kalite raporu v2: kaynak sadakati (anlam), Türkçe akıcılığı (dilbilgisi), üslup önerisi ayrı sayılır. Üslup önerisi yüksek güvenle bile otomatik onarılmaz. Aynı modelin kendini denetlemesi doğruluk garantisi değildir; farklı hakem kıyas aracında ayrı deneydir. Onarım tek tur, hedefli ve atomiktir; başarısızsa eski chapter/arşiv korunur. Kaynak alıntısı yalnız metin bağını kanıtlar. Önce/sonra kanıtı teknik izde kalır; okuyucu yalnız sayaç/şüphe özetini alır.

## Kabul ve doğrulama

Yanlış kitap/gelecek/boşluk/hash değişimi; sahte alıntı/STOP/JSON/limit; aktif terim üstünlüğü; yalnız çeviri üretimi; eski bayrak yolu; başarısız iz/eski chapter korunması; iki pipeline metin yolu; paralel bağlam izolasyonu; anlam/akıcılık/üslup ayrımı test edilir. Tam çevrimdışı ve gerçek tarayıcı testleri tamamlanır. 961/957 ve ikinci kitapta kaynak/model/sözlük sabit açık-kapalı deney yapılır, sonuçlar ve sınırlamalar raporlanır. Kalite artışı deney görülmeden vaat edilmez.
