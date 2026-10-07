# Faz 2A — Validation v2

7 Ekim 2026 · Shadow Slave · **Karar: REPEAT VALIDATION**

V2 değişiklikleri uygulandı ve v1 ile aynı 19 bölüm aynı Vertex modeliyle çalıştırıldı. Şema hatası **14 → 0**. Buna rağmen 670'te yönü ters bir öğretmen ilişkisi doğrulayıcıdan geçti; 691'de sıradan ad/True Name ayrımı ve kimlik önerileri sorunlu. **1–100 backfill başlatılmadı.** Bu rapor bir geçiş onayı değildir.

## Yöntem ve kapsam

- Bölümler: **2, 15, 24, 61, 106, 162, 273, 313, 352, 360, 381, 394, 479, 555, 670, 691, 822, 848, 923**. Başka bölümde model çıkarımı yapılmadı.
- Model: `vertex/gemini-3.6-flash`; çeviri modeli/zinciri değiştirilmedi.
- Çıkarıcı/istem/şema: `2 / 2 / delta-2`. Structured output API düzeyinde uygulandı.
- Sunucunun canlı SQLite verisi `sqlite3.backup` ile ayrı kopyaya alındı. Model koşusu `/tmp/novel-validation-v2-20261007` içindeki ayrı kod ve DB ile çalıştı. Canlı servise dağıtım/restart yapılmadı.
- Her bölüm N−1 bağlamıyla bağımsız değerlendirildi. Bu set, 1→100 kronolojik pilotunun yerine geçmez.
- 19 mantıksal model çağrısı, 21 sağlayıcı denemesi. 106'da iki HTTP **429**, sonra başarı; model değişikliği yok. Gerçek HTTP kodları `provider_attempts.json` dosyasında.
- Son doğrulayıcıdaki canonical eşleştirme ve sayaç düzeltmeleri için kaydedilmiş yanıtlar API çağırmadan tekrar denetlendi. `v2.initial.json` ilk kararları, `v2.json` son kararları saklar. 19 ham yanıt byte düzeyinde aynı. Son denetim, aynı sunucu DB kopyasında yerelde tamamlandı.

## Uygulanan v2 kontratı

1. API response JSON schema: nesne/dizi tipleri, zorunlu alanlar, enum'lar, NULL zaman alanları ve ek alan yasağı. Model çıktısı ayrıca uygulamada denetleniyor.
2. Şema, prompt ve doğrulayıcı enum'ları aynı sabitlerden üretiyor. Life status için ayrı `anyOf` dalı kullanılıyor. [Vertex JSON schema sözleşmesi](https://docs.cloud.google.com/java/docs/reference/google-cloud-vertexai/latest/com.google.cloud.vertexai.api.GenerationConfigOrBuilder).
3. İzinli durum anahtarları: `shadow_cores`, `shadow_fragments`, `soul`, `memory_tier`, `role`, `type`, `life_status`. Depolamadaki mevcut adlara eşleme var; veri göçü yok. Desteklenmeyen anahtar ölçülüp reddediliyor; kendiliğinden review oluşturmuyor.
4. `life_status` yalnız `alive/dead/missing/presumed_dead/unknown`. Değer ile epistemik durum ayrı; eski believed iddia sonradan alive+confirmed gelince tarihçede korunuyor.
5. Konum state değil; `bulundugu_yer`. Sözlükte olmayan uçlar düşük önemle varlık adayı; otomatik sözlük/entity yazımı yok.
6. N−1 bilgisi ile N'nin zaten kayıtlı deterministik/rün bilgisi ayrı prompt bölümleri. İkisi **toplam 4.000 token** bütçesini paylaşıyor.
7. Normalizasyon ve mevcut grafik/aynı bölüm kontrolü kanıttan önce. Eski alias'lar çözülürken gelecekteki kimlik bağları kullanılmıyor; ortak kanıt doğrulayıcısına bölüm sınırı geçiriliyor.
8. Alias, unvan, True Name ve okur düzeyindeki identity revelation promptta ayrılıyor; epistemik durumların anlamları açık. NULL hikâye zamanları korunuyor. Şema hatalarında model output/API uyumsuzluğu/şema tasarım hatası ayrımı var; kör şema tekrarı yok.

## V1–V2 karşılaştırması

`accepted_*`, doğrulayıcının **planladığı** yazımları sayar; gerçek yazım veya insan tarafından onaylanmış doğruluk anlamına gelmez. V1 yalnız beş bölümün deltasını değerlendirebildi; bu nedenle ret sayıları bir doğruluk yüzdesi gibi kıyaslanamaz.

| Metrik | V1 | V2 |
|---|---:|---:|
| `schema_failures` | 14 | 0 |
| `raw_relationships` | 48 | 21 |
| `accepted_relationships` | 0 | 4 |
| `evidence_failures` | 14 | 7 |
| `already_known_proposals` | 0 (v1 sayacı güvenilmez) | 0 |
| `deterministic_same_chapter_duplicates` | ölçülmedi; ham yeniden eşleşme 17* | 0 |
| `unsupported_state_keys` | ölçülmedi; ham yeniden eşleşme 10* | 0 |
| `new_entity_candidates` | 0 | 2 |
| `identity_revelations` | 2 | 2 |
| `epistemic_non_confirmed` | 1 ham / 0 değerlendirilen | 0 |
| `review_items` | 0 | 9 |
| `future_knowledge_violations` | 0 | 0 |
| `context_dropped` | 896 | 918 |
| `model_retries` | 0 | 2 |
| `cost` (başarılı yanıt tokenlarından tahmin) | $0.312 | $0.385 |


* V1'in bozuk pozisyonlu dizi öğeleri yalnız tekrar eşleşmesi için alan adlarına çevrildi; Türkçe durum anahtarları v2'deki karşılıklarına eşlendi. Bu retrospektif denetim, v1'in şema/acceptance sonuçlarını değiştirmez. V1'in bütün ham önerileri güvenle normalleştirilemediğinden sayılar tam bir lore doğruluk ölçümü değildir. Ayrıntılar audit dosyasında.

Aynı bölümün **gerçekten kayıtlı deterministik** verisiyle eşleşen tekrarlar, ham yeniden eşleştirmede v1'de **17/67**, v2'de **0/27**. Rün metninden gelmek tek başına 'zaten kayıtlı' demek değildir: 15 ve 106'da rün bloğunun bazı bilgileri mevcut deterministik kayıtta bulunmuyor.

Ek ayrım: `same_chapter_existing_proposals = 11`. Bunlar N'de eski model/elle grafik kaydında zaten var, ama N−1 bilgisi veya rün kaydı değiller. İki ana tekrar metriğine katılmadılar; kanıt kontrolünden önce ALREADY_EXISTS olarak atlandılar.

V1 raporunun 'bütün öneriler confirmed' cümlesi ham veriyle tam uyuşmuyor: 61'de bir `believed` önerisi var, ancak şemadan düştü. V2'de **tüm epistemik öneriler confirmed**; doğal epistemik çeşitlilik bu sette hâlâ gösterilemedi. Yapay çeşitlilik zorlanmadı.

V1'de modelin ham review önerisi 6, değerlendiricinin üretebildiği review 0; v2'de ham review önerisi 3, doğrulayıcının simüle ettiği review 9. Kalıcı review iki koşuda da 0. Ham identity sayısı 2 → 2, fakat 670'teki kesin yanlış identity önerisi 1 → 0; v2'nin iki identity önerisi 691'de inceleme adayı. Tüm yeni ilişki/güncelleme `gecerli_baslangic/gecerli_bitis` alanları NULL; tahmini tarih üretilmedi.

## Bölüm sonuçları

| Bölüm | Ham ilişki | Planlanan ilişki | Planlanan durum | Kanıt reddi | Önceki bilgi | Aynı bölüm rün | Aynı bölüm eski grafik | Review | Bağlam token | Kesilen |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 507 | 0 |
| 15 | 4 | 0 | 0 | 3 | 0 | 0 | 1 | 3 | 1323 | 0 |
| 24 | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 1184 | 0 |
| 61 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1222 | 0 |
| 106 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 2061 | 0 |
| 162 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1848 | 0 |
| 273 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3320 | 0 |
| 313 | 2 | 0 | 1 | 0 | 0 | 0 | 2 | 0 | 3983 | 0 |
| 352 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4000 | 5 |
| 360 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3424 | 0 |
| 381 | 5 | 1 | 0 | 0 | 0 | 0 | 4 | 0 | 3984 | 1 |
| 394 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 2984 | 0 |
| 479 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3993 | 59 |
| 555 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3195 | 0 |
| 670 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 3987 | 78 |
| 691 | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 2 | 3989 | 13 |
| 822 | 3 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 3985 | 122 |
| 848 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4000 | 372 |
| 923 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3995 | 268 |

## Yazmasız çalışma ve bütçe kanıtı

Grafik, durum, çeviri, sözlük, review, kronoloji başı ve işleme/öneri kayıtlarının içerik SHA-256 özetleri **önce = sonra**. Son yerel denetimin başlangıç özetleri model koşusunun başlangıç özetleriyle de aynı. Özellikle bağ sayısı **1.036 → 1.036**, durum **48 → 48**; `bilgi_bas`, `bilgi_inceleme`, `bilgi_isleme`, `bilgi_oneri` satırları **0 → 0**. Yıkıcı merge ve kalıcı graph/review/head/translation yazımı **0**. Sağlayıcı/kullanım telemetrisi yalnız ayrı çalışma DB'sinde tutuldu.

| Korunan tablo | Önce | Sonra | İçerik özeti |
|---|---:|---:|---|
| `chapters` | 1213 | 1213 | aynı |
| `glossary` | 1468 | 1468 | aynı |
| `sozluk_yazim` | 0 | 0 | aynı |
| `varlik_bag` | 1036 | 1036 | aynı |
| `varlik_deger` | 48 | 48 | aynı |
| `bilgi_bas` | 0 | 0 | aynı |
| `bilgi_inceleme` | 0 | 0 | aynı |
| `bilgi_isleme` | 0 | 0 | aynı |
| `bilgi_oneri` | 0 | 0 | aynı |

Bağlamın en yüksek değeri **4000 token**. Kesilenlerin tamamı eski doğrudan bağlar; varlık, kimlik, durum, yakın geçmiş ve aynı bölüm deterministik satırları bu koşuda korunmuş. 848'de **372** satır kesildi (v1: 366); aynı bölüm verisinin de bütçeye katılması bu farkı açıklıyor. Saptanan yön/kanıt/True Name hataları eski bağlam eksikliğinden kaynaklanmıyor; bütçe artırılmadı.

## Altı bölümün ayrıntılı incelemesi

### Bölüm 15

**Metnin kurduğu:** Sunny Dreamer olur, Lost from Light True Name'ini alır; görünüşü Shadow Slave'e evrilir ve Shadow Bond yeteneğini edinir. Puppeteer's Shroud bir Memory olarak verilir.

**Doğru:** Dreamer/True Name/Shroud türü tekrar edilmiyor; iki eski rün bağının kapatılması yıkıcı işlem yerine review'e yönlendiriliyor. Hikâye zamanları tahmin edilmemiş.

**Yanlış / eksik:** Görünüş, Aspect rank ve yetenek için model, özneyi içermeyen rün satırlarını kanıt gösteriyor; üç öneri katı denetimde reddediliyor. Bunlar bu bölümün deterministik veri listesinde yok; 'model tekrar etti' diye saymak hatalı olur.

**Tartışmalı:** First Seal özel varlık mı, sistem olayı/kavramı mı? Düşük önemli aday olarak kaldı. Rün parser kapsamı tamamlanmadan bu ilk bölümlerin önemli lore'u eksik kalabilir.

**Aynı bölüm deterministik veri:**

```text
BAĞ Puppeteer's Shroud --turu--> Memory (öğrenildi b15, confirmed, sistem)
BAĞ Sunny --rutbesi--> Dreamer (öğrenildi b15, confirmed, sistem)
BAĞ Sunny --gercek_adi--> Lost from Light (öğrenildi b15, confirmed, sistem)
```

**Ham model deltası:**

```json
{
  "new_relationships": [
    {
      "ozne": "Sunny",
      "iliski": "gorunusu",
      "nesne": "Shadow Slave",
      "kanit": "[Aspect Name: Shadow Slave.]",
      "durum_bilgisi": "confirmed",
      "gecerli_baslangic": null,
      "gecerli_bitis": null
    },
    {
      "ozne": "Shadow Slave",
      "iliski": "rutbesi",
      "nesne": "Divine",
      "kanit": "[Aspect Rank: Divine.]",
      "durum_bilgisi": "confirmed",
      "gecerli_baslangic": null,
      "gecerli_bitis": null
    },
    {
      "ozne": "Sunny",
      "iliski": "yetenegi",
      "nesne": "Shadow Bond",
      "kanit": "Innate Ability: [Shadow Bond].",
      "durum_bilgisi": "confirmed",
      "gecerli_baslangic": null,
      "gecerli_bitis": null
    },
    {
      "ozne": "Auro of the Nine",
      "iliski": "rutbesi",
      "nesne": "Awakened",
      "kanit": "[You have defeated an awakened human: Auro of the Nine.]",
      "durum_bilgisi": "confirmed",
      "gecerli_baslangic": null,
      "gecerli_bitis": null
    }
  ],
  "new_aliases": [],
  "relationship_updates": [
    {
      "ozne": "Sunny",
      "iliski": "gorunusu",
      "nesne": "Temple Slave",
      "degisim": "ended",
      "kanit": "[Dormant Aspect Temple Slave is evolving...]",
      "durum_bilgisi": "confirmed",
      "gecerli_bitis": null
    },
    {
      "ozne": "Sunny",
      "iliski": "rutbesi",
      "nesne": "Aspirant",
      "degisim": "ended",
      "kanit": "He was an Aspirant no more.",
      "durum_bilgisi": "confirmed",
      "gecerli_bitis": null
    }
  ],
  "state_changes": [],
  "identity_revelations": [],
  "contradictions": [],
  "new_entities": [
    {
      "ad": "First Seal",
      "kanit": "[The First Seal is broken.]",
      "tur": "kavram"
    }
  ],
  "review_items": []
}
```

**Doğrulayıcı sonucu:**

| Öneri | Sınıf | Karar |
|---|---|---|
| new_relationships: Auro of the Nine / rutbesi / Awakened | ALREADY_EXISTS | atla:aynı bölüm eski grafik |
| new_relationships: Sunny / gorunusu / Shadow Slave | NEEDS_REVIEW | reddedildi:ozne kanıt cümlesinde geçmiyor |
| new_relationships: Shadow Slave / rutbesi / Divine | NEEDS_REVIEW | reddedildi:ozne kanıt cümlesinde geçmiyor |
| new_relationships: Sunny / yetenegi / Shadow Bond | NEEDS_REVIEW | reddedildi:ozne kanıt cümlesinde geçmiyor |
| relationship_updates: Sunny / gorunusu / Temple Slave | CONFLICTS_WITH_EXISTING | inceleme |
| relationship_updates: Sunny / rutbesi / Aspirant | CONFLICTS_WITH_EXISTING | inceleme |
| new_entities: First Seal | NEEDS_REVIEW | inceleme |
| review: temporal_conflict | high | Elle/rün bağı için 'ended' önerisi: Sunny gorunusu Temple Slave |
| review: temporal_conflict | high | Elle/rün bağı için 'ended' önerisi: Sunny rutbesi Aspirant |
| review: new_entity_candidate | low | Sözlükte olmayan ad: First Seal |

### Bölüm 106

**Metnin kurduğu:** Stone Saint bir Echo'dan Shadow'a dönüştürülür. Nitelik listesi ve 0/200 sayacı gölgenin yeni durum rününde görünür.

**Doğru:** Kayıtlı Shadow türü ve Sunny'nin gölgesi bağı yeniden çıkarılmıyor. `shadow_fragments` depoda `Shadow Fragments` anahtarına eşleniyor.

**Yanlış / eksik:** Spark of Divinity'nin kanıt rününde Stone Saint adı yok; ilişki reddediliyor. Aynı bölüm deterministik listesinde nitelik ve sayaç kaydı bulunmuyor. V1 raporunun bunların tamamının zaten kayıtlı olduğu varsayımı bu snapshot'ta doğrulanmıyor.

**Tartışmalı:** Sayaç için kabul planı, rün cümlesinin bağlamından özne tayini gerektiriyor. Model state kanıtında entity adının geçmesini zorunlu tutan ilişki denetimi uygulanmıyor; state evidence bağlamı ayrıca incelenmeli.

**Aynı bölüm deterministik veri:**

```text
BAĞ Stone Saint --turu--> Shadow (öğrenildi b106, confirmed, sistem)
BAĞ Sunny --golgesi--> Stone Saint (öğrenildi b106, confirmed, sistem)
```

**Ham model deltası:**

```json
{
  "new_relationships": [
    {
      "ozne": "Stone Saint",
      "iliski": "niteligi",
      "nesne": "Spark of Divinity",
      "kanit": "Shadow Attributes: [Battle Master], [Stalwart], [Spark of Divinity].",
      "durum_bilgisi": "confirmed",
      "gecerli_baslangic": null,
      "gecerli_bitis": null
    }
  ],
  "new_aliases": [],
  "relationship_updates": [],
  "state_changes": [
    {
      "varlik": "Stone Saint",
      "anahtar": "shadow_fragments",
      "deger": "0/200",
      "kanit": "[Shadow Fragments: 0/200.]",
      "durum_bilgisi": "confirmed"
    }
  ],
  "identity_revelations": [],
  "contradictions": [],
  "new_entities": [],
  "review_items": []
}
```

**Doğrulayıcı sonucu:**

| Öneri | Sınıf | Karar |
|---|---|---|
| new_relationships: Stone Saint / niteligi / Spark of Divinity | NEEDS_REVIEW | reddedildi:ozne kanıt cümlesinde geçmiyor |
| state_changes: Stone Saint / Shadow Fragments / 0/200 | NEW | işle |

### Bölüm 360

**Metnin kurduğu:** Cassie, Sunny'nin sırrını bir vizyondan öğrendiğini ve Nephis'e verdiğini anlatır. Sunny ile Cassie'nin güven/dostluk bağı kırılır; hastanede Nephis'in bedeni gösterilir.

**Doğru:** V1'deki hospital complex entity/serbest fiziksel durum önerileri yok. Karaktere özel bilgi aktarımı mevcut graph modeline zorla yazılmıyor.

**Yanlış / eksik:** Review kanıtı yalnız 'When you killed that spy from the Castle.' cümlesi. Bu tek cümle açıklamadaki bütün True Name/Nephis iddialarını desteklemiyor. Review'lerin kanıt kapsamı ilişki denetimi kadar sıkı değil.

**Tartışmalı:** Friendship kırılması otomatik ilişki kapanışı olarak çıkarılmadı; bunun 'aynı anda düşman oldular' diye otomatik temsil edilmemesi temkinli. Retroactive revelation review'i olay/karakter bilgisi kuyruğunu büyütmemeli.

**Aynı bölüm deterministik veri:**

```text
(yok)
```

**Ham model deltası:**

```json
{
  "new_relationships": [],
  "new_aliases": [],
  "relationship_updates": [],
  "state_changes": [],
  "identity_revelations": [],
  "contradictions": [],
  "new_entities": [],
  "review_items": [
    {
      "kategori": "retroactive_revelation",
      "aciklama": "Cassie reveals she learned Sunny's True Name in a vision when he killed Harper in the Castle, and subsequently gave the secret to Nephis.",
      "onem": "medium",
      "kanit": "When you killed that spy from the Castle."
    }
  ]
}
```

**Doğrulayıcı sonucu:**

| Öneri | Sınıf | Karar |
|---|---|---|
| review: retroactive_revelation | medium | Cassie reveals she learned Sunny's True Name in a vision when he killed Harper in the Castle, and subsequently gave the secret to Nephis. |

### Bölüm 670

**Metnin kurduğu:** Effie'nin Sunny'ye mızrak kullanmayı öğrettiği hatırlatılır. Kılık değiştirmiş Sunny'yi Effie tanır; okur onun Sunny olduğunu baştan bilir.

**Doğru:** Yanlış `Effie = Sunny` kimlik önerisi kalktı. Doofus lakabı, zayıf tek cümle kanıtı nedeniyle otomatik alias yerine düşük önemli review olarak bırakıldı.

**Yanlış / eksik:** **Kesin hata:** `Effie → ogretmeni → Sunny` kabul planına girdi. İlişki etiketi 'öğretmeni', ters etiketi 'öğrencisi'; doğru yön **Sunny → ogretmeni → Effie**. Kanıtta iki adın bulunması yönün doğruluğunu garanti etmiyor.

**Tartışmalı:** Bu hatanın nedeni bağlam bütçesi değil, ilişki rol/yön denetiminin eksikliği. Graph'a yazılmadı, fakat gerçek pilotta yanlış bağ yaratabilecek bir kabul hatası.

**Aynı bölüm deterministik veri:**

```text
(yok)
```

**Ham model deltası:**

```json
{
  "new_relationships": [
    {
      "ozne": "Effie",
      "iliski": "ogretmeni",
      "nesne": "Sunny",
      "kanit": "Sunny knew of her abilities better than most, since Effie had taught him how to wield a spear.",
      "durum_bilgisi": "confirmed",
      "gecerli_baslangic": null,
      "gecerli_bitis": null
    }
  ],
  "new_aliases": [],
  "relationship_updates": [],
  "state_changes": [],
  "identity_revelations": [],
  "contradictions": [],
  "new_entities": [],
  "review_items": [
    {
      "kategori": "alias",
      "aciklama": "Effie addresses Sunny as 'Doofus', which is her personal nickname for him, though both named entities do not co-occur in the single verbatim sentence.",
      "onem": "low",
      "kanit": "She craned her neck and stared at the towering demon with an inexorable expression, then blurted out in a soft, childish voice: \"D—doofus?!\""
    }
  ]
}
```

**Doğrulayıcı sonucu:**

| Öneri | Sınıf | Karar |
|---|---|---|
| new_relationships: Effie / ogretmeni / Sunny | NEW | işle |
| review: alias | low | Effie addresses Sunny as 'Doofus', which is her personal nickname for him, though both named entities do not co-occur in the single verbatim sentence. |

### Bölüm 691

**Metnin kurduğu:** Noctis, Nether'ın Demon of Destiny olduğunu ve Hope'un Demon of Desire olarak bilindiğini anlatır. Prince of the Underworld ile Nether bağlantısı açıklanır.

**Doğru:** Kimlik önerileri yalnız review: birleştirme yapılmıyor. Kaynağa uymayan veya aynı canonical düğüme çözülen alias önerileri yazılmıyor.

**Yanlış / eksik:** `Prince of the Underworld → gercek_adi → Nether` sıradan kişisel adı büyülü True Name ile karıştırıyor. Nether'ın unvanı için kanıt 'Then there' yerine 'There' ile başlıyor; birebir kaynak koşulunu karşılamıyor, fakat son doğrulayıcı bu unvanın aynı bölüm eski grafikte zaten var olduğunu kanıttan önce saptayıp atlıyor. Ellipsis içeren Nether alıntısı ise cümle havuzunun sınırını aşıyor ve reddediliyor.

**Tartışmalı:** İki çift hem alias hem identity revelation olarak öneriliyor. Prince/Nether okur düzeyinde açıklama için makul aday; Hope/Demon of Desire'ın ayrı yeni kimlik mi, unvan mı olduğu önceki metinle denetlenmeli. İki kritik review'i iki doğrulanmış identity revelation gibi saymamak gerekir.

**Aynı bölüm deterministik veri:**

```text
(yok)
```

**Ham model deltası:**

```json
{
  "new_relationships": [
    {
      "ozne": "Nether",
      "iliski": "unvani",
      "nesne": "Demon of Destiny",
      "kanit": "There is the youngest, Nether — the Demon of Destiny, who secluded himself in the darkness of the Underworld.",
      "durum_bilgisi": "confirmed",
      "gecerli_baslangic": null,
      "gecerli_bitis": null
    }
  ],
  "new_aliases": [
    {
      "asil": "Prince of the Underworld",
      "ad": "Nether",
      "tur": "gercek_adi",
      "kanit": "’Huh... so the Prince of the Underworld was actually called Nether?",
      "durum_bilgisi": "confirmed"
    },
    {
      "asil": "Demon of Desire",
      "ad": "Hope",
      "tur": "takma_adi",
      "kanit": "Or at least they were, until the Demon of Desire decided to come and live among us mortals, becoming known as Hope.",
      "durum_bilgisi": "confirmed"
    }
  ],
  "relationship_updates": [],
  "state_changes": [],
  "identity_revelations": [
    {
      "ad_1": "Prince of the Underworld",
      "ad_2": "Nether",
      "kanit": "’Huh... so the Prince of the Underworld was actually called Nether?",
      "aciklama": "Prince of the Underworld'ın gerçek adının Nether olduğu anlaşıldı."
    },
    {
      "ad_1": "Demon of Desire",
      "ad_2": "Hope",
      "kanit": "Or at least they were, until the Demon of Desire decided to come and live among us mortals, becoming known as Hope.",
      "aciklama": "Demon of Desire'ın Hope adıyla bilindiği anlaşıldı."
    }
  ],
  "contradictions": [],
  "new_entities": [],
  "review_items": []
}
```

**Doğrulayıcı sonucu:**

| Öneri | Sınıf | Karar |
|---|---|---|
| new_relationships: Nether / unvani / Demon of Destiny | ALREADY_EXISTS | atla:aynı bölüm eski grafik |
| new_aliases: Prince of the Underworld / gercek_adi / Nether | NEEDS_REVIEW | reddedildi:kanıt verilen cümlelerden değil |
| new_aliases: Demon of Desire / takma_adi / Hope | NEEDS_REVIEW | reddedildi:özne ve nesne aynı |
| identity_revelations: Prince of the Underworld / Nether | NEEDS_REVIEW | inceleme |
| identity_revelations: Demon of Desire / Hope | NEEDS_REVIEW | inceleme |
| review: identity_merge | critical | Kimlik açığa çıkması önerisi (b691): Prince of the Underworld = Nether |
| review: identity_merge | critical | Kimlik açığa çıkması önerisi (b691): Demon of Desire = Hope |

### Bölüm 848

**Metnin kurduğu:** Sunny'nin geniş durum rünü, yeni Memories ve 777/4000 sayacı gösterilir. Düzyazı Soul Serpent'in Rain'e verildiğini ve hayatta olduğunu da belirtir.

**Doğru:** N'nin kayıtlı yedi bağı ve fragment sayacı tekrar edilmiyor; boş delta bu rün ağırlıklı bölüm için önemli iyileşme. 372 eski bağ kesilirken öncelikli bilgi ve aynı bölüm verisi korunuyor.

**Yanlış / eksik:** Bu örnekte açık bir yanlış öneri yok. Ancak boş delta tek başına recall başarısı kanıtı değil: düzyazının bütün yeni lore'unun kapsandığı ayrıca ölçülmedi.

**Tartışmalı:** Soul Serpent'in Rain'e verildiği veya alive durumu önceki graph'ta temsil edilmiyorsa eksik delta olabilir. Rün tekrarlarını bastırma hedefi tüm düzyazıyı susturmak anlamına gelmemeli; sonraki denetimde bu kapsama kontrol edilmeli.

**Aynı bölüm deterministik veri:**

```text
BAĞ Sunny --anisi--> Shadow Chair (öğrenildi b848, confirmed, sistem)
BAĞ Sunny --anisi--> Overpriced Saddle (öğrenildi b848, confirmed, sistem)
BAĞ Sunny --kusuru--> Clear Conscience (öğrenildi b848, confirmed, sistem)
BAĞ Sunny --ruya_capasi--> Tower of Longing (öğrenildi b848, confirmed, sistem)
BAĞ Sunny --niteligi--> Master of Shadows (öğrenildi b848, confirmed, sistem)
BAĞ Sunny --anisi--> Evil Eye (öğrenildi b848, confirmed, sistem)
BAĞ Sunny --anisi--> Bone Singer (öğrenildi b848, confirmed, sistem)
DURUM Sunny.shadow_fragments = 777/4000
```

**Ham model deltası:**

```json
{
  "new_relationships": [],
  "new_aliases": [],
  "relationship_updates": [],
  "state_changes": [],
  "identity_revelations": [],
  "contradictions": [],
  "new_entities": [],
  "review_items": []
}
```

**Doğrulayıcı sonucu:**

| Öneri | Sınıf | Karar |
|---|---|---|
| boş delta | — | yazım/review planı yok |

## Planlanan bütün mutasyonlar için ek denetim

Dört ilişki ve üç durum yazımı önerildi; **hiçbiri uygulanmadı**. 670'teki ters yön kesin hatadır. 162'de `Sunny oldurdu Harper` için seçilen düzyazı cümlesi bıçaklamayı kanıtlıyor, tek başına ölümü açıkça kanıtlamıyor; bölümdeki ayrı 'slain' rünü Harper'ın dead state'ini güçlü biçimde destekliyor. 313'te Lord of the Dead'in bedeninden çıkan parazitin öldürülmesiyle kişinin life status'u ayrılmalı. 381'de vassal clan için `grubu` etiketinin doğru ilişki sınıfı olup olmadığı gözden geçirilmeli. 394'te Leo Striker'ın Colosseum'da bulunması seçilen cümleyle açık biçimde destekleniyor.

## 670 false-belief testi mi?

**NO.** Bu sahnede okur düzeyinde önceki yanlış inancın düzeltilmesi yok. Sunny'nin kimliğini okur zaten biliyor; Effie'nin onu tanıması karaktere özel bilgidir. 670'i false-belief örneği diye seçen özgün doğrulama-seti varsayımı yanlıştı.

### Sonraki epistemik mini-test için adaylar — çalıştırılmadı

Kaydedilmiş kaynaklar kalıp taramasıyla bulundu ve çevre cümleleri okundu. Bunlar doğrulanmış model başarıları değil, sonraki mini-test adaylarıdır; hiçbiri v2 model koşusuna eklenmedi.

| Bölüm | Metindeki ayrım | Ne sınanabilir? |
|---|---|---|
| 412 | Kurtulanlar arkadaşlarının görsel yanılsama yapan bir yaratığa yenildiğini yanlış sanıyor; anlatı gerçek kopyalama yeteneğini açıklıyor. | `believed` ile anlatının düzelttiği bilgi; hayali otomatik kimlik merge olmadan. |
| 431 | Bazı insanlar Ivory Tower'ın Tear'ın ortasında bulunduğuna ve ilk kopan ada olduğuna inanıyor. | Tarihsel konum iddiasının `believed` olarak korunması; NULL zaman ve tahmin yasağı. |
| 685 | Sun Prince'in ruhunun metal colossus'ta bulunduğu halk inancı; Kai sentience/ceset yorumunda emin değil. | `believed` ile `uncertain` ayrımı ve akrabalık iddiasının kesinleştirilmemesi. Konum state yapılmamalı. |
| 686 | Sisten gelen ses ve kaybolmalar önce söylenti; sonrasında araştırma ekibi gerçekten kayboluyor. | `rumor` → desteklenen gözlem ayrımı. Event/karakter bilgisi zorla graph'a yazılmamalı. |

209'da 'ölü sanma' kalıbı var ama yanıt 'teknik olarak ölü' ve ontolojik ayrım içeriyor; temiz alive/dead kontrolü değil. 798'de ise annenin ölü olduğu doğrulanıyor, yanlış inanç düzeltilmiyor. Salt kalıp eşleşmesi bu ikisini iyi false-belief vakası yapmaz.

## Maliyet ve çalışma süresi

19 bölümlük ana koşu: **202,350 giriş**, **3,999 yanıt**, **58,129 düşünme tokenı**. Bölüm işlem sürelerinin toplamı **461.83 sn** (~7,7 dakika). Son çevrimdışı yeniden denetim bu süreden ayrıdır ve API maliyeti yaratmaz.

Tahmin, projenin kayıtlı fiyat tablosunu kullanır: giriş **$0,75/M**, yanıt+düşünme **$3,75/M**. Ana koşu **$0.384742** (~$0,385). Structured-output ön kontrolündeki tamamlanmış tek ek çağrı **$0.012483**; kayıtlı başarılı yanıtların toplam tahmini **$0.397226** (~$0,397). Bütçe hesabı düzeltildiğinde kesilen bir hazırlık çağrısı da vardır. İki 429 denemesi ve kesilen çağrının faturalanmış tokenları alınamadı; bu rakam sağlayıcı faturası veya tüm denemelerin kesin toplamı değildir. Canlı kullanım göstergesine bu izole koşu aktarılmadı.

## Kabul kararı ve kalan iş

**REPEAT VALIDATION.** Graph mimarisini yeniden tasarlamak gerekmiyor; structured output ve yazmasız güvenlik sınırları çalışıyor. Ancak tek bir ters yönün `işle` kabulü bile 1–100'e geçmek için yeterince önemli bir doğruluk hatasıdır.

Sonraki turda, yeni kronolojik backfill öncesinde:

1. Öğretmen/öğrenci gibi yönlü ilişkilerin semantic rol denetimini ekle; 670'i negatif kontrol yap.
2. Sıradan ad, unvan ve büyülü True Name ayrımını daha dar uygula; 691'deki çift alias/identity önerilerini denetle.
3. 15/106 rün parser kapsamını ve state evidence özne bağlamını denetle; ilişki kanıt kurallarını genel olarak gevşetme.
4. Review açıklamasının kanıtla gerçekten desteklendiğini doğrula; salt olay/karakter bilgisi review gürültüsünü sınırla.
5. Dört epistemik aday için ayrı küçük testi raporla; mevcut sette diversity üretmek için confirmed olguları düşürme.
6. Aynı 19 bölümlük karşılaştırmayı koru; 4.000 token bütçesini sırf kesilen satır sayısı büyüdü diye artırma.

Bu maddeler yeni bir v3/mini-test kararı için raporlandı. **1–100 çalıştırılmadı ve otomatik başlatılmayacak.**

## Testler ve dosyalar

Son kodda **976 test geçti** (`python -m pytest tests -q`); bilgi-delta çekirdeğinin 20 testi arasında kontrollü life status geçmişi, gelecek alias izolasyonu, same-chapter sayacının ayrılması, bilinmeyen varlıklar, desteklenmeyen state ve response schema bağlamının çeviriye sızmaması var. `git diff --check` temiz.

- `v1.json`: özgün 19 v1 ham kayıt.
- `v2.initial.json`: ilk v2 model çıktı/kararları.
- `v2.json`: aynı ham yanıtlarla son doğrulayıcı sonuçları.
- `v2.audit.json`: karşılaştırma, bölüm kaynakları, candidate taraması, DB parmak izleri ve v1 ham tekrar analizi.
- `v2.model-audit.json`: sunucudaki ilk model koşusunun audit'i.
- `provider_attempts.json`: aynı işlem kimliği altındaki 21 gerçek sağlayıcı denemesi.
- `sources.json`, `candidate-sources.json`: elle incelenen kaynaklar.
- `manifest.json`: kod ve ham yanıt SHA-256 özetleri.
- `scripts/validation_v2.py`: tekrar çalıştırılabilir sabit-set koşucu; `--replay` API çağırmaz.
