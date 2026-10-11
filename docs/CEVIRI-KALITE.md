# Kaynak kanıtlı çeviri denetimi

Yeni metin çevirileri, mevcut kalıntı/sözlük/çift anlam kontrollerinden sonra,
önbelleğe yazılmadan önce İngilizce kaynakla birlikte denetlenir. Okuma,
prefetch, toplu ve yeniden çeviri aynı `translate_chapter` yolunu kullanır.

- `CEVIRI_KALITE=1` varsayılandır. `0` acil çıkış olarak yeni katmanı kapatır.
- Denetim seçilmiş model zincirini kullanır; ücretsiz seçim ücretli modele
  geçirilmez. Denetim, onarım ve doğrulama API kayıtlarında ayrı aşamalardır.
- Latin dışı harfli sözcük kaynakta veya etkin sözlükte açıklanmıyorsa
  kalıntıdır. Türkçe harfler, noktalama ve emoji bu sınıfa girmez.
- Model her paragraf için kapsam bildirir. Hata alıntıları kaynak ve çeviride
  birebir bulunmalı; tür, numara, güven ve bitiş nedeni doğrulanmalıdır.
  Kanıtı doğrulanamayan ya da biçimi bozuk bulgu onarılmaz; paragraf şüpheli
  işaretlenir ve rapor "denetlendi" sayılmaz.
- Kanıtı doğrulanan bütün bulgular (yüksek ve düşük güvenli dilbilgisi/anlam
  hataları, üslup kusurları) ve alfabe kalıntıları yalnız ilgili paragraflarda
  onarılır: en çok `MAX_ONARIM_TURU` (3) tur, her istekte en çok
  `MAX_ONARIM_PARAGRAF` (8) hedef; fazlası ayrı isteklere bölünür.
- Onarım hedefleri değişemez, boş/işaretçili/birleştirilmiş/kısaltılmış veya
  aşırı yeniden yazılmış (özgün çeviriye göre ölçülür) ya da metni değiştirmeyen
  yanıt kabul edilmez. Sözlük, İngilizce kalıntı ve çift anlam kontrolleri de
  uygulanır. Geçen aday kaynakla tekrar denetlenir. Onarım PARAGRAF PARAGRAF
  kabul edilir.
- ÖNCE ONAR, SON ÇARE İŞARETLE (2026-10-11, kullanıcı: "altta uyarı vermesinin
  ne anlamı var, doğru düzgün çevirmesi gerekiyor"). Doğrulamada bulunan hata
  onarımın DEĞİŞTİRDİĞİ yerdeyse aday reddedilir ve gerekçesiyle
  (`reddedilen_onarim`) sonraki tura geri verilir. Hata yalnız dokunulmamış yerde,
  yani ilk çeviride de duruyorsa aday KABUL edilir ve o hata sonraki turun hedefi
  olur. Eskiden bu durumda da onarım atılıyordu: canlıda (shadow-slave 961-971)
  onarım sonrası doğrulama 16 izin 6'sında hata buldu, hiçbiri onarımın getirdiği
  hata değildi (4'ü ilk çeviride vardı, 2'si aynı hatanın süreniydi) ve altısında
  da düzeltilmiş hatalarla birlikte özgün paragraf okura gitti. Turlar biter de
  hata kalırsa paragraf son kabul edilen hâliyle kalır; künyede yalnız metinde
  hâlâ duran hata "otomatik onarılamadı" notuyla gösterilir.
- Düşük güvenli ve üslup bulguları da onarılır (2026-10-11, kullanıcı kararı;
  canlı tekrarında 969'da aynı sıfatın art arda tekrarı 0,88 güvenli "uslup"
  bulgusuydu ve onarıma hiç gitmiyordu). Doğrulamada bunlar adayın kabulünü
  engellemez, kabul edilen adayda sonraki turun hedefi olur. Yalnız böyle notlar
  taşıyan paragrafı onarım değiştirmeye gerek görmezse zorla değişiklik istenmez;
  not `ceviri_kalitesi.supheli` içinde kalır ve künyede gösterilir. Denetim
  talimatı salt anlatım tercihini bildirmemesini, üslupta yalnız somut kusuru
  (gereksiz tekrar, doğal olmayan kuruluş) vermesini ister.
- KAYDET, İŞARETLE (2026-10-11, kullanıcı kararı): kalite katmanı çeviriyi
  düşürmez. Denetim hiç tamamlanamazsa (erişim, biçim, kapsam, hizalama) çeviri
  `durum: denetlenemedi` ve nedeniyle kaydedilir; künye bunu açıkça söyler.
  Eski davranışta tek doğrulanamayan bulgu ya da onarım sonrası kalan hata bütün
  çeviriyi reddediyordu; daha önce çevrilmemiş bölüm hiç okunamıyordu
  (shadow-slave 968, iki deneme). Toplu işler bölümü otomatik yeniden üretmez.
- `chapters.ceviri_kalitesi` ve arşivdeki aynı alan eklemeli göçle oluşturulur.
  Kaynak/çeviri değiştiğinde eski rapor geçersizleşir. Eski bölümlerde NULL,
  denetlenmiş çeviride sürüm/kapsam/onarım/şüphe ve metin özetleri bulunur.
- Eski önbellek okunduğunda yeni model çağrısı yapılmaz. Geçmiş çeviriler
  kendiliğinden onarılmaz. PDF/manga görsel üretimi bu katmanın dışındadır;
  hizalı metin yolunu kullanan içe aktarımlar denetlenir.

Bu denetim kusursuzluk garantisi değildir. Model hatayı kaçırabilir veya yanlış
şüphe üretebilir; kaynak kanıtı, güven eşiği ve tekrar doğrulama zararı sınırlar.
Her yeni çeviride ek denetim çağrısı, hatalı çeviride onarım/doğrulama çağrıları
zaman ve kota tüketir. Uzun metinler denetim paketlerine bölünür. Her ek onarım
turu bir onarım ve bir doğrulama çağrısıdır; yalnız hata kalan paragraflar için
koşar.

## Ölçüm ve dağıtım

`scripts/ceviri_kalite_kiyas.py --veri ornekler.json --cikti sonuc.jsonl` yalnız
istemleri hazırlar. `--calistir` ücretli Vertex deneyini başlatır; canlı DB'ye
ve uygulama koduna yazmaz. `--kip onarim` mevcut çevirinin yeni katmandan geçişini
ölçer. Deneyde sağlayıcı/model yedeği yoktur; hata ayrı sonuç olarak kalır.

2026-10-10 ölçümünde iki kitaptan dört tam bölüm kullanıldı. Canlı istemle
3.6 ve 3.8 hizalama/sözlük kontrollerini geçti; ikisinde de Türkçe hataları
görüldü. Sade istemin 3.6 kolunda bir ret çıktı. Bu nedenle sade istem üretime
alınmadı ve model tercih sırası değiştirilmedi. Kanıtlar:
`reports/ceviri-kalite-uygulama-2026-10-10/`.

Şema göçünden önce canlı SQLite backup alınmalı, etkin toplu işler kontrol
edilmeli. Çalışan servis ayrı sözlük çalışma ağacını kullanır; dağıtım bu
tabandan hazırlanır. Python değiştiği için restart gerekir. Kabuk v114'tür;
DATA_CACHE adı değişmez. Kullanıcı onayı olmadan push/dağıtım yapılmaz.
