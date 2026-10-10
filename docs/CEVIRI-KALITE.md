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
- Yüksek güvenli dilbilgisi/anlam hataları ve alfabe kalıntıları yalnız ilgili
  paragraflarda tek tur onarılır. En fazla sekiz hedef paragraf onarılır.
- Onarım hedefleri değişemez, boş/işaretçili/birleştirilmiş/kısaltılmış veya
  aşırı yeniden yazılmış yanıt kabul edilmez. Onarılan paragraflar kaynakla
  tekrar denetlenir; sözlük, İngilizce kalıntı ve çift anlam kontrolleri de
  uygulanır. Bütün kabul kapıları geçmeden özgün metin değiştirilmez.
- Düşük güvenli şüpheler otomatik düzeltilmez. `ceviri_kalitesi.supheli` içinde
  tutulur ve okuyucunun bölüm künyesinde gösterilir. Bu, kesin hata kararı değildir.
- Kontrol tamamlanmaz veya onarım başarısız olursa `KaliteKontrolHatasi`
  döner. Yeni çeviri kaydedilmez, eski çeviri/arşiv korunur. Toplu işler tüm
  bölümü otomatik yeniden üreterek kalite onarımını tekrarlamaz.
- `chapters.ceviri_kalitesi` ve arşivdeki aynı alan eklemeli göçle oluşturulur.
  Kaynak/çeviri değiştiğinde eski rapor geçersizleşir. Eski bölümlerde NULL,
  denetlenmiş çeviride sürüm/kapsam/onarım/şüphe ve metin özetleri bulunur.
- Eski önbellek okunduğunda yeni model çağrısı yapılmaz. Geçmiş çeviriler
  kendiliğinden onarılmaz. PDF/manga görsel üretimi bu katmanın dışındadır;
  hizalı metin yolunu kullanan içe aktarımlar denetlenir.

Bu denetim kusursuzluk garantisi değildir. Model hatayı kaçırabilir veya yanlış
şüphe üretebilir; kaynak kanıtı, güven eşiği ve tekrar doğrulama zararı sınırlar.
Her yeni çeviride ek denetim çağrısı, hatalı çeviride onarım/doğrulama çağrıları
zaman ve kota tüketir. Uzun metinler denetim paketlerine bölünür; onarım turu
sayısı bir olarak kalır.

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
