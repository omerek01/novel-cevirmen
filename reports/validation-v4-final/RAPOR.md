# Faz 2A — V4 FINAL GATE COMPLETION

**Karar: STOP — V4 FINAL GATE FAIL. READY FOR 1–100 değil.**

Altı yeni model çağrısı tamamlandı; 431 önceki V4 PASS sonucu taşındı. Sağlayıcı engeli yok. 360 structured review ve 848 transfer/canlılık geçti. 313, 670 ve 691’de model kaynaklı eksik veya hatalı temsil kaldı. Yeni Validation v5 tasarlanmadı; 1–100 başlatılmadı.

## Bölüm sonuçları

| chapter | provider_status | expected_items | model_found | validator_accepted | review_correct | capability_gap | wrong_items | missing_items | result |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 360 | SUCCESS | 1 | 1 | 1 | 1 | 0 | 0 | 0 | PASS |
| 431 | CARRIED_V4_SUCCESS | 1 | 1 | 1 | 0 | 0 | 0 | 0 | PASS |
| 848 | SUCCESS | 2 | 2 | 2 | 0 | 1 | 0 | 0 | PASS |
| 162 | SUCCESS | 2 | 0 | 0 | 0 | 0 | 0 | 0 | PASS |
| 313 | SUCCESS | 1 | 0 | 0 | 0 | 0 | 2 | 1 | MODEL_FAIL |
| 670 | SUCCESS | 1 | 0 | 0 | 0 | 0 | 0 | 1 | MODEL_FAIL |
| 691 | SUCCESS | 3 | 2 | 1 | 0 | 0 | 2 | 2 | MODEL_FAIL |

162’nin iki beklentisi deterministik parser ile kapsandı; model_found/validator_accepted prose sayısına eklenmedi. validator_accepted burada modelin gold öğelerinin geçerli temsilini (review/gap ve aynı-N doğrulanmış skip dahil) sayar; gerçek DB yazımı değildir. wrong_items ham çıktının yanlış semantik temsil sayısıdır, kabul edilen yanlış öğe değildir. 691’de iki gereksiz identity item; ayrıca Prince kanıtı kaynak dışı kısaltılmıştır.

## Bulgular ve sınıflandırma

- **360 PASS:** Sunny/yoldasi/Cassie canonical resolve edildi, N−1’de b48 mevcut edge bulundu. Kanıt contiguous, 6 cümle/900 karakter sınırı içinde. Açıklama validator tarafından dar kanıttan yeniden üretildi; model aciklama authoritative değil. Auto-close/dusmani/betrayal relation yok.
- **431 PASS (taşınan):** Ivory Tower/bulundugu_yer/Tear believed; temporal alanlar NULL. Yeni model çağrısı yok. Aynı ham yanıt validator-only replay edildi; gold başarı korunuyor. Mevcut edge olmayan genel yön belirsizliği artık relationship_conflict kuyruğu oluşturmaz.
- **848 PASS:** Rain/Soul Serpent transferi structured relation_capability_gap review ile fark edildi. MISSING_RELATION_CAPABILITY doğru abstention olarak başarı sayıldı. Soul Serpent life_status=alive/confirmed explicit bounded prose ile kabul edildi. Rain için golgesi/anisi/yoldasi üretilmedi; eski master edge kapatılmadı.
- **162 PASS — DETERMINISTIC PARSER:** `[You have slain Dreamer Harper.]` Sunny/oldurdu/Harper ve Harper/dead kapsıyor. Model boş delta; parser başarısı model recall diye sayılmadı. Stabbing-only negatif kontrol korunuyor.
- **313 MODEL_FAIL — MODEL CAPABILITY / PROMPT:** Kido dead state eksik. Lord of the Dead için parasite ölümünden host kill/dead çıkarımı ham çıktıda iki kez önerildi, ikisi de reddedildi; güvenlik PASS. N−1 bağlamında Tessai/oldurdu/Kido (b306) bulundu; bu önceki bilgi omission açıklaması olabilir, fakat ayrı life_status state beklentisini değiştirmez. Gold sonuca göre düzeltilmedi; fixture yorumunda bu cross-representation suppression belirsizliği ayrıca görünür tutuldu.
- **670 MODEL_FAIL — MODEL CAPABILITY:** Yanıt tamamen boş; açık Sunny/ogretmeni/Effie öğesi yok. N−1 bağlamında teacher edge yok. Validator doğru öğeyi reddetmedi; model üretmedi. Ters yön kabulü 0, ters yön negatif kontrol geçiyor.
- **691 MODEL_FAIL — MODEL CAPABILITY / PROMPT:** Nether/Demon of Destiny doğru bulundu ve aynı-N eski graph nedeniyle güvenli skip edildi. Prince of the Underworld typed title bulundu ama kanıt düşünce paragrafını kısaltıp erken kapatan bir quote ekliyor; kaynak span/semantic role kontrolünde reddedildi. Hope/Demon of Desire title yerine identity_revelations önerildi; ikinci gereksiz identity item Nether/Prince. İkisi de reddedildi, identity merge/review kuyruğu 0. Ordinary-name→gercek_adi 0. Eksikler: Prince kabulü ve Hope title. Bu yanıt validator kusurunu kanıtlamıyor; model kanıt/temsil sözleşmesine uymadı.

PROMPT sınıflandırması kontrol edilebilir çıktı sözleşmesini, MODEL CAPABILITY bu koşuda gözlenen uyum/recall başarısızlığını belirtir; modelin içsel nedeni bilinmiyor. Doğrulanmış parser arızası yok. RELATION VOCABULARY eksikliği yalnız 848 transferinde var ve doğru gap nedeniyle gate blocker değil. VALIDATOR güvenlik kapıları hatalı death/identity/evidence öğelerini kabul etmedi.

## Metrikler

| Metrik | Değer |
|---|---:|
| schema_failures | 0 |
| future_knowledge_violations | 0 |
| wrong_direction_accepted | 0 |
| high_impact_unsupported_accepted | 0 |
| unsupported_review_accepted | 0 |
| true_name_confusions | 0 |
| unnecessary_identity_items_raw | 2 |
| unnecessary_identity_reviews_accepted | 0 |
| deterministic_duplicates_raw | 0 |
| deterministic_duplicates_written | 0 |
| expected_items_measured | 11 |
| expected_prose_items_measured | 9 |
| model_found | 6 |
| validator_accepted | 5 |
| correct_reviews | 1 |
| capability_gaps | 1 |
| deterministic_coverage | 2 |
| missing_expected_items | 4 |
| precision_proxy | 1.0 |
| precision_proxy_denominator | 3 |
| recall_proxy | 0.5555555555555556 |
| effective_fixture_coverage | 0.6363636363636364 |
| provider_success_rate | 1.0 |
| new_logical_calls | 6 |
| new_provider_attempts | 6 |
| new_cost_estimate_usd | 0.1524585 |
| carried_431_cost_estimate_usd | 0.01856775 |
| gate_cost_estimate_usd | 0.17102625 |
| max_context_tokens | 4000 |
| operational_response_coverage | 1.0 |
| operational_gate_pass_coverage | 0.5714285714285714 |

Kalite hesabı yalnız başarılı provider yanıtlarında: prose recall **5/9 = %55,56**, deterministik dahil fixture coverage **7/11 = %63,64**. Provider response coverage **7/7**, yeni çağrı başarısı **6/6**; operasyonel gate PASS **4/7**. Capability gap MISS değil. Provider yüzünden recall=0 atanan öğe yok. model_found **6** typed doğru gold keşif; bunların biri invalid evidence ile reddedildi. identity item semantik sinyali typed title başarısı diye sayılmadı.

Precision proxy, otomatik kabul planındaki kaynakla destekli öğelerin elle denetimidir; rejected/skipped/review/parser öğelerini denominatora eklemez. Küçük örnekten genel precision garantisi çıkarılmaz. Güvenlikte yanlış kabul 0, recall gate ise geçmedi. Cost USD tahmini token kullanımına dayanır (input $0,75/M, output+thinking $3,75/M); fatura doğrulaması değildir. Taşınan 431 maliyeti yeni ücret diye sayılmadı; eski V4 failed denemelerin bilinmeyen maliyeti bu koşunun tahminine eklenmedi.

## Sözleşme, sınırlar ve doğrulama

Graph mimarisi, relation vocabulary, temporal/epistemic model değişmedi. Yeni relation_capability_gap yalnız review kategorisidir, graph ilişkisi değildir. Model vertex/gemini-3.6-flash; çıkarıcı/istem 4/4, şema delta-3-v4-final; context <=4000. Review kanıtı en fazla 6 contiguous cümle ve 900 karakter, tercih 1–3. Dağınık pasaj birleştirme reddedilir. Fictional generic örnekler kullanıldı; production koduna chapter/kişi special-case eklenmedi.

Yeni çağrılar yalnız 360/848/162/313/670/691; 19 bölüm yeniden çalıştırılmadı. Mevcut retry/backoff sınırı değiştirilmedi; altı yeni çağrıda retry 0. Model kalite sorunları için yeni ücretli tekrar başlatılmadı.

Gold unchanged SHA-256: `0d2fbead465291f1f50269f1cf026299a50daad1e79ffb39981ebb3a4426610f`. Original expected-delta.json aynen kopyalandı, FIXTURE_CORRECTION yapılmadı. Remote final.audit.json ve yerel replay-audit.json korunan tabloların hash eşitliğini doğruluyor. 1213 kaynak, 1468 glossary, 1036 graph edge, 48 state; head/review/oneri/isleme boş kaldı. Ham yanıt hashleri replay boyunca aynı. Canlı deploy/restart/graph write yapılmadı.

Testler: sözleşme değişikliklerinden sonra full suite **1016 passed** (3 mevcut deprecation warning). Son genel relationship-conflict queue düzeltmesinden sonra hedefli testler **45 passed**. Mevcut negatif kontroller: stabbing-only, parasite→host death, reversed teacher, ordinary-name True Name, unsupported review; ayrıca required structured fields, mevcut N−1 edge ve bounded contiguous span kontrolü.

Rün duplication: yeni altı çağrıda raw 0, written 0. Eski chapter15 yeniden çağrılmadı; onun önceki raw davranışının modelde düzeldiği iddia edilmiyor. Final semantic gate eksikleri nedeniyle pilot configuration/komutu aktive edilmedi. Kullanıcının IF FAIL kuralına göre burada STOP.

## Artefaktlar

- final.initial.json: remote değerlendirmesi ve değişmeyen ham yanıtlar.
- final.json: aynı yanıtların güncel validator-only replay sonucu.
- final.audit.json / replay-audit.json: korunan tablolar ve ham yanıt hashleri.
- chapter-results.json / expected-delta-results.json / metrics.json: ölçülebilir sonuçlar.
- manual-audit.json: kabul/skip/review ve kaynak span kontrolleri.
- expected-delta.json / expected-delta.sha256: değişmeyen V4 gold.

Son kodla `pytest tests -q`: **1016 passed, 3 warnings, 88,57 saniye**. Kökteki `pytest -q`, scratch/test_user_models.py import sırasında OPENROUTER_API_KEY olmadığı için collection aşamasında durdu; bu ad hoc script suite sonucuna dahil edilmedi. Ek model çağrısı yapılmadı.
