# Faz 2A — Hedefli Validation v4

7 Ekim 2026 · **Karar: REPEAT VALIDATION — READY FOR 1–100 değil.**

Kod ve hedefli testler tamamlandı. Önce üç ana hedefte model çağrıldı. **360 kopuşu fark etti, ancak kanıt/ilişki alanları olmayan ve bozuk özne içeren review üretti. 431 geçti. 848 sağlayıcı 504 → 429 → 429 nedeniyle model çıktısı veremedi.** Kullanıcının beklenmeyen yeni problemde DUR kuralıyla kalan dört model çağrısı başlatılmadı. 1–100 backfill başlatılmadı.

## Kapsam ve koşu

- Planlanan final gate: **360, 431, 848, 162, 313, 670, 691**.
- Gerçek model çağrısı: **360, 431, 848**; **3 mantıksal çağrı / 6 sağlayıcı denemesi**. Sonuncu yanıt üretmedi. 162/313/670/691 için yeni model çağrısı **0**.
- İlk üç kapsam zaten başlatılmıştı; 360 sorunu görüldüğünde 848 çağrısı başlamıştı. Başlamış çağrı sonucu kaydedildi, regression aşaması açılmadı. İkinci/19 bölümlük model koşusu ve otomatik tekrar başlatılmadı.
- Model `vertex/gemini-3.6-flash`; çıkarıcı/istem **4/4**, şema **delta-3 değişmedi**. Graph vocabulary, temporal model ve graph tabloları yeniden tasarlanmadı.
- Ayrı `/tmp/novel-validation-v4-20261007` kod ve SQLite kopyası. Canlı deploy/restart yok. `v4.primary.audit.json` korunan tabloların önce/sonra içerik hash eşitliğini doğruluyor. Grafik 1036 bağ, 48 değer; head/isleme/oneri/review tabloları boş kaldı.
- Mevcut 23 V3 ham yanıt validator-only replay edildi: **0 yeni model çağrısı**, ham metin aynı, korunan tablolar aynı. `v3-validator-replay.json`, `replay-audit.json`.
- Final gate’in tamamı koşulmadığından dört regression bölümünde V4 model precision/recall başarısı iddia edilmiyor. Offline regression ve gerçek fixture testleri ayrı kanıttır.

## Çağrıdan önce dondurulan fixture

`expected-delta.json` SHA-256: `0d2fbead465291f1f50269f1cf026299a50daad1e79ffb39981ebb3a4426610f`. Yerel freeze hash ile remote model koşusunun hash’i aynı. Model çıktısına göre gold değiştirilmedi.

| Bölüm | Knowledge type | Beklenti | Epistemik durum | Temsil | Sonuç |
|---|---|---|---|---|---|
| 360 | existing_relationship_conflict | Sunny / yoldasi / Cassie | confirmed | review | DETECTED_RAW_BUT_UNUSABLE |
| 431 | historical_location_belief | Ivory Tower / bulundugu_yer / Tear | believed | model | ACCEPTED |
| 848 | transfer_or_entrustment | Rain / MISSING_RELATION_CAPABILITY / Soul Serpent | confirmed | capability_gap_allowed | PROVIDER_UNMEASURED |
| 848 | life_status | Soul Serpent / life_status / alive | confirmed | model | PROVIDER_UNMEASURED |
| 162 | explicit_system_kill | Sunny / oldurdu / Harper | confirmed | deterministic | NOT_RUN |
| 162 | explicit_system_death | Harper / life_status / dead | confirmed | deterministic | NOT_RUN |
| 313 | explicit_prose_death | Kido / life_status / dead | confirmed | model | NOT_RUN |
| 670 | teacher_direction | Sunny / ogretmeni / Effie | confirmed | model | NOT_RUN |
| 691 | title | Nether / unvani / Demon of Destiny | confirmed | model | NOT_RUN |
| 691 | title | Nether / unvani / Prince of the Underworld | confirmed | model | NOT_RUN |
| 691 | title | Hope / unvani / Demon of Desire | confirmed | model | NOT_RUN |

Toplam **11** öğe: 2 deterministik, 7 model, 1 ilişki review’i, 1 capability-gap kabul edilebilir transfer. `expected_model_items=9`, modelin fark edip geçerli delta/review/gap olarak temsil etmesi gereken bütün non-deterministic sorumlulukları sayar. Başarılı yanıt alınmış gold öğe 2; provider yüzünden ölçülemeyen 2; henüz model çağrılmamış 5.

### FIXTURE_CORRECTION — V3 beklentisinin semantik düzeltilmesi

V3’ün Rain → golgesi → Soul Serpent fixture beklentisi bu tur vocabulary audit’inde fazla güçlü bulundu. `golgesi` mevcut metadata’da **master → Shadow**, `kendi_golgesi` kişinin kendi gölgesi, `anisi` owner → Memory, `yanki` owner → Echo; `grubu` üyelik, `yoldasi` sosyal yoldaşlık. Genel `sahibi`, custody/entrustment/transfer relation yok. Bir teslim/emanet verme mastership veya Memory/Echo türünü kendi başına kanıtlamaz. Ayrıca 848 rünleri Soul Serpent’i hâlâ Sunny’nin Shadows listesinde gösteriyor ve prose bağlantısının sürdüğünü söylüyor. Eski master bağını kapatmak veya Rain’i yeni master yapmak kanıtı aşar.
Bu yüzden V4 transfer gold’u, **model çağrısından önce** `MISSING_RELATION_CAPABILITY` review’ine izin verecek biçimde donduruldu. **Bu V4 gold’una sonuçtan sonra yapılan bir düzeltme değildir.** Yeni relation eklenmedi. Yanlış ownership triple yerine transferin graph-worthy bilgi olarak görülmesi ve insan temsil kararı gerekir. Transferin görülüp görülmediği 848 API hatası nedeniyle bu koşuda ölçülemedi.

## Genel extraction değişiklikleri

- Empty delta öncesi dört prose kontrolü: named transfer/entrustment, explicit life status, collective unresolved belief, mevcut companion bağının açık bozulması. Rünlerde varlığın görünmesi yeni prose bilgisini bastırmıyor; suppression yalnız exact triple/state için.
- Gave/entrusted/was given/handed over/now belongs dilinde item ve new_holder rolleri kontrol edilir. Teslim/emanet mastership’e körlemesine map edilmez; uygun relation yoksa mevcut review şemasında capability gap. Previous holder kaynak/önceki graph’tan audit edilir; kaynağın kurmadığı holder tahmin edilmez.
- Explicit alive/still alive/survived/not dead kanıtı; appeared/moved/spoke/present tek başına yeterli değil. Full ad ve kısa adı aynı bounded span’da görülebilir; kaynak dışı/zamirsiz özne şartı kaldırılmadı. Pozitif gerçek 848 testi, eski ikinci sentence-only kontrolünün bounded span’ı reddettiğini gösterdi; bu redundant kontrol kaynak içindeki bounded span kontrolüne düzeltildi.
- Collective belief örnekleri prompta ve deterministik epistemik işaret kapısına eklendi. Tek karakter özel inancı dışarıda. Collective believed hiçbir şekilde confirmed’a yükseltilmez; tarih belirsizse iki temporal alan NULL.
- Companion rupture, var olan N−1 bağ + iki açık isim + bounded source + açık ihanet/güven kırılması gerektirir. Review açıklaması dar kanıttan yeniden üretilir; secret/vision gibi ek model açıklamaları taşınmaz. Companion update gelse de AUTO CLOSE yok. Argument/anger/disagreement yeterli değil.
- Production logic’e 360/431/848 veya o bölümlerin gerçek kişi/entity adlarıyla special case eklenmedi. Gerçek isimler yalnız fixture/test/rapor verisinde; prompt örnekleri farklı kurmaca isimlerle genel.
- API şeması değişmedi. Bu yüzden optional review alanlarının eksikliği JSON schema failure olmayabilir; semantik kapı review’i reddeder. 360’ta tam olarak bu durum görüldü.

## V3’ün dört raw rün tekrarı

| Tekrar | Gözlenen ana kategori | Ek etken | V4 hazırlığı |
|---|---|---|---|
| Sunny anisi Puppeteer’s Shroud | D: exact claim context’te vardı, çıktı yine tekrarladı | B: curly/straight apostrophe presentation mismatch | Shared canonical name/triple + named-field JSON |
| Sunny gorunusu Shadow Slave | D | A/C/E yok | Shared canonical JSON row |
| Shadow Slave rutbesi Divine | D | A/C/E yok | Shared canonical JSON row |
| Sunny yetenegi Shadow Bond | D | A/C/E yok | Shared canonical JSON row |

D sınıflandırması gözlenen instruction compliance sonucudur; modelin içsel nedenini bildiğimiz anlamına gelmez. Dört claim’in çağrıdan önce context’e girdiği ve normalize triple’ın aynı olduğu doğrulandı; timing yok, relation mismatch yok. İlkinde yazım farkı ek etken. V4 prompt ve validator `canonical_triple/canonical_plan` paylaşır; parser’ın internal `_evrim` işareti graph fact listesine girmez. Output alan adlarıyla tekilleştirilmiş rün JSON listesi çağrıdan önce 4000 ortak bütçeye girer.
`15-canonical-context-audit.json` eski/yeni context’i gösterir. **15’te yeni model çağrısı yapılmadı**; aynı bölümde model compliance düzeldiği iddia edilmiyor. V4’ün iki yanıtında raw deterministic duplicate 0, yazılan duplicate 0; bu tam yedi bölüm veya eski 15 davranışının kanıtı değildir. Kullanıcının güncel kapısı korunur: <=1 raw tekrar, root cause anlaşılmış ve yazımda bastırılmışsa tek başına blocker değil.

## İstenen özel sonuçlar

| Bölüm | Kontrol | YES / NO | Kanıt / sınır |
|---|---|---|---|
| 360 | Relationship conflict detected? | YES (raw signal) | Model açıklamasında betrayal/rupture var |
| 360 | Evidence bounded? | NO | `kanit` alanı yok |
| 360 | Review useful? | NO | `iliski`/`nesne` yok; `ozne` entity adı yerine uzun açıklama. Kuyruğa alınmadı |
| 431 | Collective belief detected? | YES | Ivory Tower bulundugu_yer Tear |
| 431 | Epistemic = believed? | YES | confirmed’a yükseltilmedi |
| 431 | No fabricated temporal range? | YES | başlangıç/bitiş NULL |
| 848 | Transfer detected? | NO — UNMEASURED | API yanıtı yok; modelin görmezden geldiği söylenemez |
| 848 | Correct representation OR capability gap surfaced? | NO — UNMEASURED | Güvenli gap yolu/testi hazır, model başarısı yok |
| 848 | Alive detected? | NO — UNMEASURED | API yanıtı yok; full-pipeline fixture testi başarılı |
| 848 | No rune duplication written? | YES | Simulation hiçbir graph yazımı yapmadı |

360’ın bozuk `ozne` alanı “SunnyResponse to Cassie’s betrayal and relationship rupture: …” ile başlıyor. Bu JSON parse/schema hatası değil, expected structured review contract’ının semantik başarısızlığı. Eksik kanıt sonradan fixture’dan doldurulup model başarısı gibi sayılmadı.

## V4 metrikleri — kısmi koşu

| Metrik | Değer | Kapsam / açıklama |
|---|---:|---|
| `schema_failures` | 0 | 2 başarılı yanıt; review semantic failure ayrı |
| `model_failures` | 1 | 848 provider failure |
| `future_knowledge_violations` | 0 | Başarılı bağlamlar + offline failed-context audit |
| `wrong_direction_accepted` | 0 | V4 başarılı yanıtlar; ayrıca negatif control geçiyor |
| `high_impact_unsupported_accepted` | 0 | Başarılı yanıtlar + negative control |
| `unsupported_review_accepted` | 0 | 360 unsupported review reddedildi |
| `true_name_confusions` | 0 | V4 raw primary 0; 691 model tekrar çalışmadı |
| `deterministic_same_chapter_duplicates_raw` | 0 | Yalnız alınan V4 yanıtları |
| `deterministic_duplicates_written` | 0 | Simulation / protected hashes |
| `expected_model_items` | 9 | Planlanan 7 bölüm: 9 non-deterministic sorumluluk |
| `model_found` | 1 | Usable structured expected item: 431. 360 raw signal usable item değil |
| `validator_accepted` | 1 | Gold 431 öğesi. Gold dışı Sunny/Sky Below ile toplam planlanan ilişki 2 |
| `review_correct` | 0 | Beklenen 360 review: 0. Diğer dar yön incelemesi gold başarısı sayılmadı |
| `capability_gaps_detected` | 0 | Gerçek model/delta koşusunda 0; offline pozitif testi bu sayıya eklemedik |
| `missing_expected_items` | 1 | Kesin usable missing: 360. Ölçülemeyenler missing recall diye sunulmuyor |
| `unmeasured_expected_items` | 7 | 848 iki öğe + çağrılmayan regression beş öğe |
| `precision_proxy` | 1.0 | 2/2 otomatik kabul planı; küçük örnek, 7 bölüm için garanti değil |
| `recall_proxy` | 0.5 | 1/2 başarılı yanıt alınan expected item; final-gate recall N/A |
| `primary_end_to_end_recall_proxy` | 0.25 | 1/4 primary expected item; API başarısızlığı dahil |
| `final_seven_chapter_recall_proxy` | N/A | Kapsam tamamlanmadı |
| `confirmed` | 2 | Alınan raw relationship/alias/state öğeleri |
| `strongly_implied` | 0 | Alınan raw relationship/alias/state öğeleri |
| `believed` | 1 | Alınan raw relationship/alias/state öğeleri |
| `rumor` | 0 | Alınan raw relationship/alias/state öğeleri |
| `uncertain` | 0 | Alınan raw relationship/alias/state öğeleri |
| `disproven` | 0 | Alınan raw relationship/alias/state öğeleri |
| `deception` | 0 | Alınan raw relationship/alias/state öğeleri |

`expected-delta-results.json` öğe bazında ACCEPTED / DETECTED_RAW_BUT_UNUSABLE / PROVIDER_UNMEASURED / NOT_RUN ayrımını saklar. Raw açıklamada konuyu fark etme ile kanıtlı usable delta aynı metrik değildir. Boş/ölçülemeyen 0/0 sonuç başarı sayılmadı.

## Sağlayıcı ve maliyet

| Bölüm | HTTP denemeleri | Sonuç |
|---|---|---|
| 360 | 429 → 200 | JSON alındı, review usable değil |
| 431 | 200 | Collective belief kabul |
| 848 | 504 → 429 → 429 | Model API failure, ham yanıt yok |

HTTP kodları kopya SQLite’ın `api_olay` kayıtlarından işlem/call kimliğiyle doğrulandı. Runner callback’in positional kod/süre alanları null kalmıştı; kaynak telemetri `verified-provider-attempts.json` içinde, ham model yanıtı değiştirilmedi. Altı provider attempt = 2 başarılı, 4 geçici hata. Sonuç, 429’un kapasite mi kota mı olduğu konusunda tek başına teşhis değildir.
Başarılı yanıt usage’ından repo fiyatıyla tahmin: **$0.0453615** (input 26282, output 592, thinking 6248; $0.75/M ve $3.75/M). Bu **toplam fatura değildir**. Dört başarısız denemenin token/ücretleri bilinmiyor. V3 replay ve offline kontrollerin model maliyeti 0.

## Precision regression ve testler

Gerçek bölüm kaynaklı beş negative control **5/5** geçiyor: Effie→ogretmeni→Sunny ret; Prince→gercek_adi→Nether ret; stabbing-alone→oldurdu ret; parasite death→host dead ret; unsupported geniş review ret. `negative-controls.json` ham kontrol ve final validator kararlarını taşır. Hiçbiri graph/review yazmadı.
Gerçek 360/431/848 bounded fixture testleri; isimlerden bağımsız beş transfer örneği, beş collective belief biçimi, appearance/movement/speech/presence negatif life testleri, no-auto-close ve canonical apostrophe/same-schema kontrolleri geçti. **1013 passed, 3 mevcut deprecation warning**. Hedefli 57 test de geçti. Graph temporal/schema mimarisi aynı.

## Final hard gate kararı

Gözlenen acceptance güvenliği bozulmadı. Buna rağmen 360 usable review kapısı **FAIL**, 848 transfer/alive kapıları **UNMEASURED**, dört regression model bölümü **NOT RUN**. Tam yedi bölümlük gate **PASS değildir**. Bu nedenle **REPEAT VALIDATION**. Kullanıcının DUR kuralıyla yeni model çağrıları kesildi; 19 bölüm yeniden çağrılmadı.
Sonraki deneme için çözülmesi gerekenler: review örneğinin tüm mevcut structured alanları ve bounded evidence zorunluluğu açık olmalı; prompttaki eski “ONE sentence” genellemesi bounded-span talimatıyla tutarlı hale getirilmeli. 848 ancak sağlayıcı yanıt verdiğinde ölçülebilir. Bu rapor promptun düzeltilmiş yeni bir model sonucunu içermez; eksik veri elle tamamlanmadı.

**1–100 başlatılmadı. READY FOR 1–100 verilmediği için gerçek backfill yürütme komutu önerisi bu raporda aktive edilmedi.**

Kanıtlar: `expected-delta.json/.sha256`, `prior-state-audit.json`, `v3-duplication-audit.json`, `15-canonical-context-audit.json`, `848-context-audit.json`, `v3-validator-replay.json`, `replay-audit.json`, `negative-controls.json`, `v4.json`, `v4.primary.audit.json`, `verified-provider-attempts.json`, `metrics.json`.
