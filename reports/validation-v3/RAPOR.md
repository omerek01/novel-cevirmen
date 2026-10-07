# Faz 2A — Validation v3

7 Ekim 2026 · **Karar: REPEAT VALIDATION**

V3 uygulandı; aynı 19 bölüm ve ayrı dört epistemik bölüm çalıştırıldı. 670 yönü düzeldi, 691 True Name hatası engellendi. Buna rağmen 848’in iki açık düzyazı bilgisi, 360’taki ilişki çatışması ve 431’in okur düzeyindeki inancı kaçıyor. Rün tekrarları da sıfıra yaklaşmadı. **1–100 backfill başlatılmadı.**

## Kapsam, güvenlik ve yöntem

- Ana set: **2, 15, 24, 61, 106, 162, 273, 313, 352, 360, 381, 394, 479, 555, 670, 691, 822, 848, 923**.
- Ayrı epistemik mini-test: **412, 431, 685, 686**. Ana metriklere eklenmedi.
- Model `vertex/gemini-3.6-flash`; sürümler **3 / 3 / delta-3**. Structured output, N−1, birleşik 4000 token bütçe korundu.
- **19 + 4 mantıksal çağrı**, **19 + 4 sağlayıcı denemesi**. Model fallback/retry yok. Yön doğrulaması için ikinci LLM çağrısı yapılmadı.
- Ayrı `/tmp/novel-validation-v3-20261007` kodu/DB kopyası; mini-test ayrı `mini.db`. Canlı servis deploy/restart edilmedi. Son validator replay yerelde aynı donmuş snapshot üzerinde API çağırmadan yapıldı.
- Ham 23 yanıt replay boyunca birebir değişmedi. `*.initial.json` ilk değerlendirmeyi, `v3.json` ve `mini.json` son değerlendirmeyi tutuyor.
- Korunan tabloların satır içeriği SHA-256 önce/sonra aynı: chapters, glossary, sozluk_yazim, varlik_bag, varlik_deger, bilgi_bas, bilgi_inceleme, bilgi_isleme, bilgi_oneri. Grafik 1036 bağ / 48 değer; head/review/oneri/isleme boş kaldı. API telemetrisi kopyada yazılabilir; grafik incelemesi kalıcı yazılmaz.
- Kaynak N içindeki adlar görülebilir; geçmiş açıklamalar/bağlar N−1 süzgeçlidir. Aynı N rün planı ayrı ve “simulation, not persisted” olarak etiketlidir. Gelecek bağ/alias N üzerinden canonical kimlik oluşturmaz. Yeni isim/sözlük kaydı, destructive merge ve head ilerletme yok.

## Uygulanan doğrulama

1. Mevcut ILISKILER’in tamamına subject_role, object_role, symmetry, inverse label, direction_sensitive ve strong-evidence metadata eklendi. Yeni ilişki türü/`adi` eklenmedi. Kanonik yön öğretmen için **öğrenci → ogretmeni → öğretmen**; lider için grup → lider; diğerleri aşağıdaki denetim tablosunda. `ogrencisi` yalnız ters görünüm etiketi, yeni ilişki türü değil.
2. Saf deterministik semantic gate, kaynak span’ı + iki açık isim + rol örüntüsünü denetliyor. Ters yön reddediliyor; rol kurulamazsa NEEDS_REVIEW, otomatik kabul yok. Bu regex kapısı tam bir dil anlama garantisi değildir; kapsanmayan paraphrase incelemeye gider.
3. `gercek_adi` yalnız açık True Name ifadesi/sistem ödülüyle. Ordinary naming yeterli değil. Canonical ad mevcut glossary source/kimlik; tekil Türkçe target geri eşlemesi mevcut kayda çözülüyor. Model canonical ad yazdı diye yeni `adi` bağı veya merge yok.
4. True Name/unvan/alias tek ilişkiyle temsil ediliyor; aynı raw delta’daki relationship+alias kopyası bastırılıyor. “title … becoming known as name” genel rol örüntüsü unvanın taşıyıcıya yönünü koruyor. İsim uçları kendi canonical adlarıyla eşleşirken çapraz alias’lar uçları yutmuyor. 691’de iki gereksiz critical identity önerisi kuyruğa alınmadı. Gerçek okur kimlik ifşası, iki isim + açık reveal kanıtı varsa insan incelemesine kalır.
5. Rün öznesi yalnız mevcut parser’ın doğrulanmış blok/ödül bağlamından geliyor. Normal düzyazıda eksik özne hâlâ ret. `oldurdu`: saldırı, bıçaklama, yaralama, yenme yeterli değil; açık öldürme veya Spell slain gerekir. İnsan kill bildirimi victim dead state de üretir.
6. Life status için gerçek özne ve alive/dead/missing/presumed_dead/unknown değeri kurulmalı. Diğer kontrollü state değerinde özellik ve değer kanıtı aranıyor. Unsupported key review üretmiyor.
7. Modelin serbest review açıklaması güvenilir kabul edilmiyor. Yapılandırılmış uçlar + kaynak kanıtı + graph issue gerekir; açıklama doğrulanan dar iddiadan yeniden üretilir. Olay özeti, karakterin özel bilgisi, motivasyon, atmosfer veya geçici mood kuyruğa sokulmaz.
8. Eski model/NULL epistemik kayıt üzerine gerçek believed önerisi sırf bağ zaten var diye atlanmıyor. Elle/rün geçmişini değiştirecek farklı epistemik iddia incelemeye gider.

## V1 / V2 / V3 — ana 19 bölüm

Accepted ilişkiler **yazım planıdır**, insan onayı veya gerçek yazım değildir. `wrong_accepted_relationships` yanlış semantik/yön; `high_impact_evidence_failures` yetersiz yüksek etkili kanıtı ayrı sayar. Karşılaştırmadaki `unsupported_review_items` kuyruğa kabul edilen kanıtsız iddia sayısıdır: V3 **0**. Çekirdeğin ret sayacı 3, karşılaştırmada ayrı `rejected_unsupported_review_items=3` olarak tutulur.

| Metrik | V1 | V2 | V3 |
|---|---:|---:|---:|
| `schema_failures` | 14 | 0 | 0 |
| `raw_relationships` | 48 | 21 | 19 |
| `accepted_relationships` | 0 | 4 | 2 |
| `wrong_accepted_relationships` | 0 | 1 | 0 |
| `evidence_failures` | 14 | 7 | 9 |
| `deterministic_same_chapter_duplicates` | 17 | 0 | 4 |
| `same_chapter_existing_proposals` | 10 | 11 | 8 |
| `unsupported_state_keys` | 10 | 0 | 0 |
| `new_entity_candidates` | 0 | 2 | 1 |
| `identity_revelations` | 2 | 2 | 2 |
| `unnecessary_identity_reviews` | 0 | 2 | 0 |
| `epistemic_non_confirmed` | 1 | 0 | 0 |
| `review_items` | 0 | 9 | 2 |
| `unsupported_review_items` | 0 | 5 | 0 |
| `future_knowledge_violations` | 0 | 0 | 0 |
| `direction_errors` | 0 | 1 | 0 |
| `high_impact_evidence_failures` | 0 | 2 | 3 |
| `expected_items` | 16 | 16 | 16 |
| `model_found` | 8 | 6 | 7 |
| `validator_accepted` | 0 | 2 | 8 |
| `missing_expected_items` | 13 | 11 | 3 |
| `precision_proxy` | N/A | 0.5000 | 1.0000 |
| `recall_proxy` | 0.1875 | 0.3125 | 0.8125 |
| `cost_usd_estimate` | 0.3119 | 0.3847 | 0.3493 |

V1’in 14 bölümü şemadan düştü; precision N/A, 0/0’ı başarı saymıyoruz. V1 tekrar/unsupported key/same-N değerleri v2 raporunun retrospektif eşlemesidir; özgün şema sonucu değiştirilmedi. Expected-delta karşılaştırması da bu tur oluşturulan küçük fixture’a retrospektif eşlemedir, eski koşularda ölçülmüş metrik gibi sunulmaz.
Precision proxy yeni kabul edilen ilişkilerde doğru yön **ve yeterli kanıt** oranıdır: V2 **2/4** (670 yanlış yön, 162 bıçaklama kanıtı yetersiz); V3 **2/2** (691 iki unvan). İki örnek yüksek güvenli genel doğruluk iddiası değildir. V2’nin 313 dead kanıtı da yetersizdi; toplam high-impact failure 2 kabulden geçti. V3’ün 3 high-impact yetersiz önerisi reddedildi, kabul edilen 0.
V3 aynı-delta kopyaları **4** ayrı sayılır; aynı bölüm rün tekrarları **4**. Aynı-N eski model/elle bağ tekrarları **8**, N−1 tekrarı **0**. İki sayaç birbirine karıştırılmadı. V3 tekrar sayacı yeni parser alanlarının yazmasız planını da kapsar; V1/V2 rün tekrarları eski kayıt kapsamıyla ölçüldüğünden 0→4 doğrudan gürültü artışı olarak yorumlanamaz. Rün tekrarları kalıcıya yazılmadı fakat “yaklaşık sıfır raw tekrar” kapısı geçmedi.

## Ana setin bölüm sonuçları

| Bölüm | Schema hatası | Ham ilişki | Planlanan ilişki | Planlanan state | Kanıt reddi | Review | Bağlam token | Kesilen |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0 | 0 | 0 | 0 | 0 | 0 | 596 | 0 |
| 15 | 0 | 5 | 0 | 0 | 3 | 0 | 1470 | 0 |
| 24 | 0 | 1 | 0 | 0 | 1 | 0 | 1262 | 0 |
| 61 | 0 | 0 | 0 | 0 | 0 | 0 | 1222 | 0 |
| 106 | 0 | 0 | 0 | 0 | 0 | 0 | 2211 | 0 |
| 162 | 0 | 0 | 0 | 0 | 0 | 0 | 1898 | 0 |
| 273 | 0 | 0 | 0 | 0 | 0 | 0 | 3487 | 0 |
| 313 | 0 | 1 | 0 | 0 | 1 | 0 | 3983 | 0 |
| 352 | 0 | 0 | 0 | 0 | 0 | 0 | 3985 | 12 |
| 360 | 0 | 1 | 0 | 0 | 2 | 0 | 3424 | 0 |
| 381 | 0 | 2 | 0 | 0 | 0 | 0 | 3984 | 1 |
| 394 | 0 | 0 | 0 | 0 | 0 | 0 | 2984 | 0 |
| 479 | 0 | 0 | 0 | 0 | 0 | 0 | 3993 | 59 |
| 555 | 0 | 0 | 0 | 0 | 0 | 0 | 3195 | 0 |
| 670 | 0 | 1 | 0 | 0 | 0 | 0 | 3987 | 78 |
| 691 | 0 | 3 | 2 | 0 | 2 | 0 | 3989 | 13 |
| 822 | 0 | 3 | 0 | 0 | 0 | 0 | 3985 | 122 |
| 848 | 0 | 0 | 0 | 0 | 0 | 0 | 3994 | 414 |
| 923 | 0 | 2 | 0 | 0 | 0 | 2 | 3998 | 280 |

## Küçük expected-delta fixture ve recall

Fixture çağrılardan önce oluşturuldu: `expected-delta.json`. Toplam 16 öğe: 9 deterministik, 7 model/review. Exhaustive lore gold değildir. `model_found` raw alanlarda doğru triple; şemadan düşmüş veya kanıtı zayıf raw içerik bulunmuş sayılabilir, kabul sayılmaz. `validator_accepted` işle ya da aynı-N kayıtla doğrulanmış skip; needs_review/ret ve aynı-delta kopyaları sayılmaz. Effective coverage = deterministik parser + validator kabulü.

| Bölüm | Beklenen | Model buldu | Validator kabul | Deterministik kapsadı | Eksik |
|---|---:|---:|---:|---:|---:|
| 15 | 6 | 4 | 4 | 6 | 0 |
| 106 | 3 | 0 | 0 | 3 | 0 |
| 360 | 1 | 0 | 0 | 0 | 1 |
| 670 | 1 | 1 | 1 | 0 | 0 |
| 691 | 3 | 2 | 3 | 0 | 0 |
| 848 | 2 | 0 | 0 | 0 | 2 |

Toplam effective recall **13/16 = 81.2%**. Düzyazı/review recall **4/7 = 57.1%**; raw model doğru triple **3/7**. Rün kazanımı düzyazı kaybını örtmüyor.
- **15:** Sunny Aspect Shadow Slave, Shadow Slave rank Divine, Shadow Bond, Dreamer, True Name ve Shroud award deterministik olmalı. Önce Aspect Rank sonra Aspect Name, standalone Aspect ve Innate Ability, Memory award çözüldü. Shroud’un Awakened rank’ı prose inference: **SHOULD REMAIN MODEL-EXTRACTED**; mevcut quote Shroud’u isimle anmadığından ret, fixture’a kesin kabul beklentisi eklenmedi.
- **106:** Stone Saint Shadow type/rank/class/attributes/fragments: **SHOULD BE DETERMINISTIC**. Battle Master/Stalwart önce bilindiğinden fixture yeni Spark of Divinity, Shadow type ve 0/200’e odaklanıyor. Shadow-specific continuation parent korunur; anlatımdan sonra genel Rank satırı önceki özneye bağlanmaz.
- **360:** Cassie’nin Sunny’ye ihanetinin ilişki çatışması insan review adayı; “kim ne öğrendi” character-knowledge graph değil. V2’nin verdiği kısa kanıt bütün açıklamayı desteklemiyordu. V3 onu tekrarlamadı ama gerekli friendship conflict’i de bulmadı. Sunny/Harper kill ve Harper dead için verdiği zamirli quote’lar reddedildi. Hastane/duygu özeti eklenmedi.
- **670:** model **Sunny → ogretmeni → Effie** buldu. N−1’de teacher bağı yok; mevcut aynı-N eski model kaydıyla doğrulanmış skip. Effie’nin Sunny’yi tanıması okur identity revelation değil. Yanlış Effie→Sunny negative control reddedildi.
- **691:** Nether→Demon of Destiny ve Nether→Prince of the Underworld unvan; Hope→Demon of Desire unvan. Model sonuncuyu Demon→takma_adi→Hope çıkardı; genel naming/title kuralı doğru unvan rolüne çevirdi. Relationship/alias/identity üçlü kopyası tek öneriye indi. Prince→gercek_adi→Nether negative control reddedildi. İki ham identity tekrarının critical review’i **0**.
- **848:** N−1’de Rain↔Soul Serpent bağı ve Serpent state yok. Context/rune planında sadece Sunny→Soul Serpent sahipliği görülüyor; bu, Rain’e gifting bilgisini temsil etmez. Kaynak ownership gift ve alive bilgilerini açıkça içeriyor, fakat V3 raw delta yine boş. Validator ret değil **model recall kaybı**. Aynı kaynak span’ı ile pozitif kontrol gift=verified, alive=True; bu elle hazırlanan kontrol model_found’a eklenmedi. Kesin içsel model nedeni gözlenemez; rün suppression/boş delta önceliği olası açıklama, doğrulanmış neden gibi sunulmaz.

## Ayrı epistemik mini-test

| Epistemik durum | Ham öğe |
|---|---:|
| `confirmed` | 5 |
| `strongly_implied` | 0 |
| `believed` | 1 |
| `rumor` | 0 |
| `uncertain` | 0 |
| `disproven` | 0 |
| `deception` | 0 |

Çeşitlilik zorlanmadı. Ana 19’da 0 non-confirmed; mini-testte 1 gerçek **believed**. Model yalnız character-specific bilgi iddiası değil, okur/anlatının kesinleşmemiş önermesini etiketledi.

| Bölüm / konu | TEXT ESTABLISHES | MODEL CLASS | İnsan değerlendirmesi |
|---|---|---|---|
| 412 yanlış monster yorumu | Awakened topluluğunun görsel bozulma yorumu anlatı tarafından yanlışlanır; fiili copy ayrı gerçek | Delta boş | **QUESTIONABLE**: disproven sinyali kaçıyor; adı olmayan yanlış event önerisini yeni graph türüne zorlamak doğru değil |
| 431 Ivory Tower/Tear | Some people believed geçmiş konumunu; kesin coğrafya bilgisi değil | Bu önerme yok; diğer iki öneri confirmed | **WRONG (recall)**: mevcut bulundugu_yer ile believed temsil edilebilir bilgi kaçtı; mevcut doğru confirmed konum önerilerinin epistemik sınıfı doğru |
| 685 Sun Prince/Sevirax | “supposed to be a brother”: doğrulanmamış akrabalık aktarımı | believed | **CORRECT**: kesin akrabalık gibi kabul edilmedi; eski NULL model bağına yeni epistemik destek planlandı |
| 685 metal colossus soul/sentience | Kolektif inanç + anlatıcıdaki belirsizlik; adı olmayan colossus | Öneri yok | **CORRECT abstention / QUESTIONABLE coverage**: yeni event/soul-inside state türü icat edilmedi; uncertain sinyali graph çıktısında gösterilmedi |
| 686 fog/disappearances | Önce rumors, sonra gerçekten geri dönmeyen ekip; aynı önermeler değil | Night Temple konumu confirmed; rumor öğesi yok | **CORRECT** konum sınıfı, **QUESTIONABLE** epistemik kapsam: adsız event söylentisi graph’a zorlanmadı |

Mini-test: schema **0**, raw relationship **4**, planlanan ilişki **2**, alias **1**, review **2**, future **0**, unsupported review claim accepted **0**. Seven-status coverage kanıtlanmadı; yalnız doğal believed davranışı gösterildi. Mini sonuçları ana tabloda sayılmadı.

## İlişki metadata denetimi

Tüm mevcut türler denetlendi; ters etiketler yalnız görünüm metadata’sı, çoğu için yeni inverse ilişki oluşturulmadı. Symmetric türlerde killer/owner gibi yön rolleri aranmaz; named endpoints ve ilişkinin açık lexical kanıtı hâlâ gerekir.

| Tür | Özne rolü → nesne rolü | Simetrik | Ters etiket | Yüksek etkili kanıt |
|---|---|---|---|---|
| `takma_adi` | bearer → alias | hayır | kimin takma adı | hayır |
| `gercek_adi` | bearer → true_name | hayır | kimin Gerçek Adı | hayır |
| `unvani` | bearer → title | hayır | kimin unvanı | hayır |
| `anisi` | owner → memory | hayır | sahibi | hayır |
| `golgesi` | master → shadow | hayır | efendisi | hayır |
| `kendi_golgesi` | owner → shadow | hayır | kimin kendi gölgesi | hayır |
| `yanki` | owner → echo | hayır | efendisi | hayır |
| `yetenegi` | bearer → ability | hayır | kimin yeteneği | hayır |
| `efsunu` | memory → enchantment | hayır | hangi Anının efsunu | hayır |
| `niteligi` | bearer → attribute | hayır | kimin niteliği | hayır |
| `gorunusu` | bearer → aspect | hayır | kimin Görünüşü | hayır |
| `klani` | member → clan | hayır | üyesi | hayır |
| `lideri` | group → leader | hayır | yönettiği | hayır |
| `yoldasi` | companion → companion | evet | yoldaşı | hayır |
| `akrabasi` | relative → relative | evet | akrabası | hayır |
| `dusmani` | enemy → enemy | evet | düşmanı | hayır |
| `ogretmeni` | student → teacher | hayır | ogrencisi | hayır |
| `bulundugu_yer` | occupant → place | hayır | orada bulunan | hayır |
| `parcasi` | part → whole | hayır | içerdiği | hayır |
| `turu` | instance → type | hayır | örneği | hayır |
| `rutbesi` | bearer → rank | hayır | bu rütbede | hayır |
| `sinifi` | bearer → class | hayır | bu sınıfta | hayır |
| `ust_basamak` | lower_rank → higher_rank | hayır | bir alt basamak | hayır |
| `esya_turu` | item → item_type | hayır | bu türde eşya | hayır |
| `bicimi` | entity → form | hayır | kimin biçimi | hayır |
| `donustu` | previous_form → new_form | hayır | önceki biçimi | evet |
| `oldurdu` | killer → victim | hayır | öldüreni | evet |
| `grubu` | member → group | hayır | üyesi | hayır |
| `kusuru` | bearer → flaw | hayır | kimin Kusuru | hayır |
| `ruya_capasi` | dreamer → anchor | hayır | kimin Rüya Çapası | hayır |

## Hard gate sonucu

| Kapı | Sonuç |
|---|---|
| schema / future / destructive merge = 0 | PASS |
| Yanlış yönlü kabul = 0 | PASS; gerçek 670 ve negative control |
| Yüksek etkili unsupported kabul = 0 | PASS; 3 zayıf öneri ret |
| Unsupported review claim kabul = 0 | PASS; ham noise korunup reddedildi |
| Sistematik True Name/unvan karışması yok | PASS; ordinary-name negative control engellendi |
| Rün tekrarları yaklaşık sıfır | FAIL; 4 ham tekrar, yazımda 0 |
| Doğal non-confirmed mini davranışı | KISMİ PASS; believed gerçek, 431 kaçtı |
| Açık düzyazı bilgisi sistematik kaçmıyor | FAIL; 848 gift/alive ve 360 çatışma kaçtı |

## Maliyet, testler ve karar

Başarılı token usage’tan repo fiyatıyla tahmin: ana **$0.349252**, mini **$0.072714**, toplam **$0.421966**. Girdi $0.75/M, çıktı+düşünme $3.75/M. Fatura değildir; ayrı v2 preflight/maliyetleri dahil değildir. Bu turda başarısız/retry sağlayıcı denemesi kaydedilmedi. Offline replay maliyet 0.
Testler: tam suite **994 passed / 3 mevcut deprecation warning**; son canonical/alias düzeltmelerinden sonra hedefli **38 passed**. Kökte bare pytest, mevcut scratch/test_user_models.py’nin API key isteyen top-level SystemExit’i nedeniyle collect edemedi; uygulama testi `pytest tests -q` ile tamamlandı.
**Öneri: REPEAT VALIDATION.** Bir sonraki tur rün raw suppression ve prose recall’a odaklanmalı; 848 ownership-transfer/alive, 360 bounded relationship-conflict kanıtı, 431 collective believed konumu için bu fixture regresyon kapısı olarak kullanılmalı. 1–100 chronological backfill için hazır değil. Bu rapordan sonra yeni model koşusu/backfill/deploy başlatılmadı.

Kanıt dosyaları: `comparison.json`, `expected-delta*.json`, `deterministic-plans.json`, `negative-controls.json`, `recall-positive-controls.json`, `relation-audit.json`, `v3*.json`, `mini*.json`.
