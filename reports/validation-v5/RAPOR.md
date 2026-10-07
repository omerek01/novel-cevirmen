# Faz 2A v5 — Çıkarıcı Recall Düzeltmesi + Kör Holdout

**Karar: REGRESSION FAIL.** Kör holdout ÇALIŞTIRILMADI, yeni istem turu ve model kıyası başlatılmadı, 1–100 başlatılmadı.

313 ve 670 geçti. 691'de üç unvandan ikisi doğru temsil edildi; üçüncüsü (Nether → Prince of the Underworld) modelce BULUNDU ama kanıtın sonuna kaynakta olmayan tek bir kapanış tırnağı (`’`) eklendiği için doğrulayıcı reddetti. Kriter "FOUND veya doğru eşdeğer atlama" ve "geçersiz kanıt kabulü = 0" birlikte uygulandığında öğe grafiğe girmiyor, yani 691 FAIL.

## A. Yapılan değişiklikler

- **İstem v5** (`ISTEM_SURUMU=5`, `CIKARICI_SURUMU=5`; şema `delta-3-v4-final` DEĞİŞMEDİ): tek çağrıda STAGE A (iç kapsama taraması, çıktısı istenmez) + STAGE B (yalnız JSON delta). Kontrol listesi A–F (`KAPSAMA_KATEGORILERI`), boş delta öncesi 9 sinyal (`BOS_DELTA_ONCESI_SINYALLER`), CHECK ≠ EMIT, kanıt kopyalama disiplini, tamamlayıcı temsil kuralı, öğretmen yönü, ad/unvan/takma ad/Gerçek Ad/kimlik açığa çıkması ayrımı, temsil boşluğu. Aynı bölüm başlığı: `ALREADY EXTRACTED FROM THIS CHAPTER — DO NOT RE-EXTRACT`. Örnekler kurgu adlarla (Arden/Mira, Ayla/Boran, Orion/Lina…).
- **Sağlayıcı kapısı:** `CIKARICI_MODELI = "vertex/gemini-3.6-flash"`, `saglayici_dogrula()` tanımlı Vertex modeli dışındaki her adı reddeder. `vertex/sahte` gibi tanınmayan adlar da reddedilir, çünkü çeviri yolu bunları sessizce ücretsiz Gemini anahtar havuzuna gönderirdi (V4 testi tam olarak bu adı kullanıyordu). Yanıtlayan model istenenden farklıysa sonuç reddedilir. Bu ihlal `provider_policy_violation` olarak sınıflanır, PROVIDER_BLOCKED olarak değil. Çeviri zinciri ve ayar ucu değişmedi; çıkarıcı `secili_zincir()` okumaz (test ediliyor).
- **Bastırma sınıfı** (`bastirma_sinifi`): her "atla" kararı EXACT_DUPLICATE ya da SEMANTIC_DUPLICATE olarak etiketlenir.
- **Öğretmen kalıpları:** `mentored` ve `trained/mentored him|her` eklendi. "X was Y's teacher" kalıbı, iyelik ekini terim eşleyicisi yuttuğu için hiç eşleşmiyordu; düzeltildi. Kanıt birebirlik kuralları GEVŞETİLMEDİ.
- **Betik:** `scripts/validation_v5.py` (yalnız simülasyon, ücretsiz Gemini sayacı, korunan tablo hash'leri, gold/holdout hash denetimi, üzerine yazma yok).

## B. Sağlayıcı doğrulaması

| | |
|---|---|
| mantıksal çağrı | 3 (313, 670, 691) |
| sağlayıcı denemesi | 3, hepsi `vertex/gemini-3.6-flash`, HTTP 200, tekrar 0 |
| istenen zincir | yalnız `vertex/gemini-3.6-flash` |
| **ücretsiz Gemini çağrısı** | **0** |
| PROVIDER_BLOCKED | 0 |

## C. Çapraz temsil bastırma denetimi

| Sınıf | Kod yolları |
|---|---|
| EXACT_DUPLICATE | aynı üçlü + aynı ad (`tekrar`), aynı delta içi tekrar, aynı-N rün planı (`system_block`), aynı durum anahtarı/değeri/epistemik durum, son sınıflamada `atla:zaten var` |
| SEMANTIC_DUPLICATE | aynı kanonik kimlik, farklı yazım (alias → asıl), simetrik ilişkinin ters yönü |
| COMPLEMENTARY_KNOWLEDGE | **Doğrulayıcıda hiçbir yol bastırmıyordu.** 313'teki kayıp modelin kendi bastırmasıydı (bağlamda `Tessai --oldurdu--> Kido`). v5 istemi bunu açıkça yasaklıyor. Koşuda Kido dead kabul edildi. |

## D. Bilinen regresyon sonuçları

| Bölüm | Beklenen | Sonuç |
|---|---|---|
| 313 | Kido life_status=dead | **BULUNDU + KABUL** (`Kido, who was now dead`) |
| 313 | Lord of the Dead ölümü kabul edilmemeli | Model yine iki kez önerdi (oldurdu + dead), ikisi de reddedildi. Güvenlik geçti. |
| 670 | Sunny ogretmeni Effie | **BULUNDU**, doğru yön. Aynı-N eski grafik eşdeğeri olarak EXACT atlandı. Ters yön üretilmedi. |
| 691 | Nether → Demon of Destiny | bulundu, aynı-N eşdeğeri atlandı |
| 691 | Hope → Demon of Desire | **BULUNDU + KABUL** (unvani; identity_revelation değil) |
| 691 | Nether → Prince of the Underworld | Bulundu, tür doğru (unvani). **Kanıt geçersiz:** sona kaynakta olmayan `’` eklendi. O karakter olmadan span birebir geçerli. → **MISSING** |
| 691 | Gerçek Ad karışıklığı / gereksiz kimlik birleştirmesi / gereksiz kimlik incelemesi | 0 / 0 / 0 (V4'te gereksiz kimlik öğesi 2'ydi) |

Sonuç: 313 PASS, 670 PASS, 691 **FAIL** → **REGRESSION FAIL**.

## E–G. Holdout

Holdout listesi model sonucu görülmeden donduruldu: `holdout-chapters.json`, SHA-256 `8f57363c855dec513786c3201e051191373140bbe27a2e7d6984dd23c15ef4b7`. Bölümler: 83, 187, 343, 374, 542, 590, 681, 744, 782, 887. Seçim gerekçesi dosyada.

Regresyon geçmediği için gold OLUŞTURULMADI ve hiçbir holdout bölümü çalıştırılmadı. Liste ileriki bir tur için temiz kaldı: hiçbir model sonucu ya da istem değişikliği ona bakılarak yapılmadı.

## H. Hassasiyet / hatırlama (yalnız bilinen regresyon seti)

| | V4 final (aynı 3 bölüm) | v5 |
|---|---:|---:|
| beklenen öğe | 5 | 5 |
| model buldu | 2 | **5** |
| doğru temsil (kabul ya da eşdeğer atlama) | 1 | **4** |
| recall_proxy (doğru temsil) | 0,20 | **0,80** |
| yanlış kabul | 0 | 0 |
| geçersiz kanıtla kabul | 0 | 0 |

Hassasiyet proxy'si: kabul edilen 2 öğe (Kido dead, Hope unvanı) elle denetlendi, ikisi de doğru (2/2). Örneklem çok küçük, genel bir hassasiyet iddiası değildir.

## I. Güvenlik metrikleri

schema_failures 0 · future_knowledge_violations 0 (bağlam N−1 süzgeçli, ≤4000 token) · wrong_direction_accepted 0 · high_impact_unsupported_accepted 0 (Lord of the Dead ×2 reddedildi) · unsupported_review_accepted 0 · true_name_confusions 0 · identity_overreach 0 · deterministic_duplicates_raw 0 / written 0 · korunan tablolar (chapters, glossary, sozluk_yazim, varlik_bag, varlik_deger, bilgi_*) önce/sonra hash'leri **eşit** · gold SHA-256 `0d2fbead…610f` değişmedi, FIXTURE_CORRECTION yok.

## J. Kategori bazında kayıplar

Tek kalan kayıp **kanıt kopyalama uyumu**: model, açık "DO NOT add or close quotation marks" kuralına rağmen alıntıyı kendi kapattı. Aynı öğede V4'teki hatanın aynısı. Sınıf: **PROMPT / MODEL CAPABILITY** (talimat uyumu). VALIDATOR değil: kural "birebir span" ve doğru uygulandı. CONTEXT değil: ilgili satır kesilmedi ve kaynak tam verildi. Recall kategorisi kayıpları (life_status, öğretmen, unvan) bu sette kapandı.

## K. Maliyet / gecikme

Giriş 47.112 · çıkış 875 · düşünme 11.625 token → ~**0,082 $** (0,75 $/M giriş, 3,75 $/M çıkış+düşünme; tahmin, fatura değil). Bölüm başı 22,9–37,8 sn. Talimat ~4.700 token (≈+670 gerçek giriş tokeni/bölüm). Bilgi bağlamı bütçesi 4000'de kaldı ve talimat büyümesinden etkilenmez; kesilen satır sayısı V4 ile aynı (0 / 78 / 13).

## L. Testler

`pytest tests -q`: **1044 passed**, 3 mevcut deprecation uyarısı. Yeni `tests/test_cikarici_v5.py` (28 test) şunları kapsıyor: sağlayıcı kapısı, çeviri ayarından bağımsızlık, kapsama/boş delta sözleşmesi, kanıt birebirliği, tamamlayıcı bilgi, parazit→konak (bu negatif kontrol testlerde HİÇ YOKTU, eklendi), öğretmen yönü ve hatırlama, ad/unvan/Gerçek Ad, aynı-N deterministik bastırma, kapasite boşluğu, doğrulama kipinin grafiği değiştirmemesi, üretim kodunda gerçek ad ya da bölüm numarası bulunmaması. `git diff --check` temiz. V4 ham yanıtları yeni doğrulayıcıda yeniden oynatıldı ve 7 bölümün 7'sinde kararlar aynı çıktı.

Not (aşırı uyum kalıntısı, bu turda DEĞİŞTİRİLMEDİ): `bilgi_kanit.py` içinde önceki turlardan kalma iki ifade parçası duruyor: `stood in its middle` (bulundugu_yer) ve `walked in, alive` (alive). Ad ya da bölüm numarası değiller, ama belirli bir bölümün cümlesinden alınmışlar.

## M. Öneri

**REGRESSION FAIL**

Kullanıcı kararı bekleyen seçenekler (hiçbiri çalıştırılmadı):

1. **Model kıyası (yalnız Vertex):** `vertex/gemini-3.8-flash`, aynı dondurulmuş 3 bölüm, aynı istem/bağlam/gold ile. 3 çağrı, ~0,08–0,10 $. Soru: kanıt kopyalama uyumu model kapasitesi mi?
2. **Doğrulayıcı kuralı kararı:** kanıtın başında ya da sonunda, kaynakta o konumda olmayan eşleşmemiş tırnak karakterlerini birebirlik denetiminden ÖNCE kırpmak. İçerik değişmez, ama bu bir kanıt kuralı değişikliğidir ve bu görevde açıkça yasaklandığı için yapılmadı.
