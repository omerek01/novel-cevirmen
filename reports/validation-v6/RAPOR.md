# Faz 2A v6 — Kapsama ipuçları + kanıt çözümleme + yeni kör holdout

**Karar: HOLDOUT FAIL**

Güvenlik kapısı tamamen temiz. Kalite kapılarının üçü de geçmedi:

| Kapı | Sonuç | Eşik |
|---|---:|---:|
| model_discovery_recall | **0,70** | 0,80 |
| validator_conversion_rate | **0,29** | 0,85 |
| effective_fixture_coverage | **0,38** | 0,80 |

Asıl darboğaz artık **doğrulayıcının dönüşüm oranı**: model 10 öğenin 7'sini anlamca doğru buldu, ama yalnız 2'si doğru temsil edildi. 1–100 başlatılmadı, `CIKARICI_MODELI` 3.6'da kaldı.

## A. Yeni holdout ön-dondurma

Holdout, kod değişikliğinden ÖNCE ve kaynak okunmadan seçildi.
- Bölümler: **33, 141, 199, 322, 460, 556, 659, 740, 769, 888**.
- Yöntem: 1–946 aralığı 10 dilime bölündü. Her dilimde kaynak metni olan, 1000–2500 kelimelik ve önceki 33 doğrulama/holdout bölümünden olmayan adaylar arasından `random.Random(20261007).choice` ile seçim yapıldı. Yalnız bölüm no ve kelime sayısı kullanıldı.
- Dosya: `holdout-v6-chapters.json`, SHA-256 **`87be1b88…8aab52`**.

## B. Kayıp sahipliği denetimi (eski holdout = görülen set)

| Öğe | Sahip |
|---|---|
| 83 Blood Weave | GOLD ISSUE (aynı bölüm kalıcı rün bağı) |
| 343 Crimson Terror dead | VALIDATOR → **düzeltildi** (`corpse of`) |
| 343 Nephis/Caster öldürme | MODEL + VALIDATOR (birinci şahıs diyalog "I killed him" desteklenmez) |
| 343 Soul Conduit | MODEL (diyalog) |
| 374 Kai True Name | VALIDATOR → artık incelemeye düşüyor (çoğul + birden çok ad) |
| 374 / 782 Nephis alive, 681 Solvane→Elyas | VALIDATOR, **bilinçli olarak çözülmüyor** (öncül paragraf dışında ya da birden çok aday) |
| 374 Rock rolü | MODEL (doğrulayıcı artık "Instructor X" biçimini destekliyor) |
| 590 Mordret soyu | **RELATION VOCABULARY**: `akrabasi` simetrik "akraba", yönlü soyu temsil edemez → RELATION_CAPABILITY_GAP |
| 681 Hope → Demon of Desire | MODEL → kapsama ipucuyla görülen sette **bulundu ve kabul edildi** |
| 744 Master of Shadows, Shadow Manifestation | **SHOULD BE DETERMINISTIC** → rün çözücüsü artık kapsıyor |
| 744 Child of Shadows bitişi, 887 Shadow Manifestation | MODEL |

## C. Doğrulayıcı temsil değişiklikleri (`bilgi_kanit.py`)

- **Sınırlı zamir çözümü** (`zamir_baglami`). Bütün koşullar birlikte aranır:
  - aynı paragraf;
  - hemen önceki TEK cümle;
  - cümle başındaki özne zamiri (he/she/it/they);
  - önceki cümlede TEK adlandırılmış aday, ve bu aday beklenen uç noktayla aynı.

  İyelik zamirleri çözülmez; cinsiyet tahmini yapılmaz. Kanıt değişmez, yalnız iç bağlam kurulur. Belirsiz durumda kabul yok.
- **Ceset:** `corpse of X`, `X's corpse`, `body of the dead X` yalnız ölüm DURUMU kurar; öldüren ilişkisi kurmaz. Benzetme ve bileşik biçimler (corpse-like / puppet / eater / like a corpse) dışarıda.
- **True Name / True Names:** tekil ve çoğul ikisi de tanınır. Çoğulda başka ad varsa sıraya bakarak eşleme yapılmaz; öğe incelemeye düşer.
- **Rol:** "X was/served as (the) V" ve unvan biçimi "V X".

## D. Deterministik çözücü (`varlik_grafigi.py`)

- `[...Aspect Ability Name: X.]`: baştaki üç nokta artık engel değil.
- `Aspect Ability: [X]`.
- Spell'in "Ability acquired" duyurusu özneyi rünleri okuyana bağlar.
- `[X] Attribute/Ability Description:` satırı YALNIZ etkin bir durum bloğu varken (ya da kapanmış bloğun 12 paragraflık penceresinde) o bloğun öznesine bağlanır.
- Düzyazı rün öznesini miras ALMAZ.

## E. Kapsama ipucu tarayıcısı (`kapsama_ipuclari.py`)

- Yalnız kaynak metne bakar; N−1'i bilmez ve olgu üretmez.
- Kategoriler (öncelik sırasıyla): identity · death_life · change · teaching/lineage · epistemic · title_alias · structured.
- Sınırlar: en çok 12 ipucu, kategori başına 4, ≤800 token. Aynı span tekilleştirilir; deterministik planın satırları dışarıda kalır.
- İstemde ayrı bölüm olarak girer: `COVERAGE CUES — THESE ARE NOT FACTS`.
- 4000'lik bilgi bütçesine girmez. Holdout'ta 1–6 ipucu, 34–228 token.
- İkinci model çağrısı yok.

## F. Görülen regresyon (4 çağrı: 343 model kaybı ağır, 374 True Name/rol, 681 zamir+unvan, 744 rün)

- Yeni yanlış kabul **0**.
- Kabul edilen 3 öğenin üçü de doğru: Crimson Terror dead (ceset), Hope → Demon of Desire (ipucuyla bulundu), Elyas dead.
- Kai'nin Gerçek Adı incelemeye düştü.
- Çıktı: `seen-3.8.json`.

Ayrıca ham v5.2 yanıtlarının doğrulayıcı-yalnız yeniden oynatması (`seen-replay.json`): kabuller 10 → 10, yeni yanlış kabul 0, yeni doğru kabul 1 (ceset). Altar Island'ın kabul dışı kalması önceden beklenen sonuçtu.

## G. Dondurulmuş v7 sistemi

`frozen-system-v7.json`, SHA-256 `62eec40d…`.
- Sürümler: çıkarıcı 7, istem 6, şema `delta-3-v4-final`.
- İstem `d23b2687…`, bilgi_delta `3baa296a…`, bilgi_kanit `d232e551…`, varlik_grafigi `8de8b7d7…`, kapsama_ipuclari `21188919…`.
- Sunucudaki kodun hash'leri aynı.

## H. Yeni gold

`holdout-v6-gold.json`, SHA-256 **`dfd7d35fa18353a38ab16b1b72c23b2fa26017fd3bb119edfc2a875b83d10fc1`**.
- Kaynak, sistem dondurulduktan sonra ilk kez okundu. Her aday N−1'e ve aynı-N planına karşı denetlendi; LLM kullanılmadı.
- 13 öğe: 3 deterministik, 8 model, 1 inceleme, 1 temsil boşluğu.
- 4 boş-gold bölüm (199, 322, 769, 888); gerekçeleri dosyada.
- Model sonrası gold değişikliği YOK.

## I. Kör holdout — bölüm sonuçları

| Bölüm | Beklenen | Det. | Model buldu | Dönüştü | Eksik | Sonuç |
|---|---:|---:|---:|---:|---:|---|
| 33 | 3 | 3/3 | – | – | 0 | PASS (model tekrar etmedi) |
| 141 | 4 | – | 3 | 0 | 4 | VALIDATOR_FAIL + MODEL_FAIL |
| 199 | 0 | – | – | – | 0 | PASS |
| 322 | 0 | – | – | – | 0 | PASS |
| 460 | 2 | – | 1 | 1 (eşdeğer atlama) | 1 | MODEL_FAIL (soy boşluğu üretilmedi) |
| 556 | 2 | – | 1 | 0 | 2 | VALIDATOR_FAIL + MODEL_FAIL |
| 659 | 1 | – | 1 | 0 | 1 | VALIDATOR_FAIL |
| 740 | 1 | – | 1 | 1 (kabul) | 0 | PASS |
| 769 | 0 | – | – | – | 0 | PASS |
| 888 | 0 | – | – | – | 0 | PASS |

Model bulup doğrulayıcının dönüştüremediği 5 öğe:

| Öğe | Sebep |
|---|---|
| Castle Guard → Tessai | kanıtta "perhaps the oldest Sleeper" yan cümlesi epistemik kapıyı tetikledi |
| Hunters/Pathfinders → Gemma | edilgen "were led by X" kalıbı `lideri`de yok |
| Night Temple → Northern Island | cümle ortası "it's" zamiri; kural yalnız cümle başı zamiri çözüyor |
| Elyas dead | "the young man's death" adlaştırması |

Zamir çözümü kör sette hiç tetiklenmedi.

## J. Üç katmanlı kalite

| Katman | Değer |
|---|---:|
| model_discovery_recall | 7/10 = **0,70** |
| validator_conversion_rate | 2/7 = **0,29** |
| effective_fixture_coverage | (3 det + 2)/13 = **0,38** |
| deterministik kapsama (ayrı) | 3/3 |

## K. Hassasiyet ve güvenlik

- Bütün kabuller elle denetlendi: tek kabul `Ivory Dragon dead` ve doğru → **1/1** (n=1, anlamlı değil).
- Kabul edilmeyen ham ekstraların çoğu anlamca doğru: Host lideri Gunlaug, Gunlaug unvani Bright Lord (strongly_implied), Tessai rutbesi Sleeper, Seishan–Sunlight Shard (strongly_implied).
- Gürültü: "Professor" için düşük önemli bir `new_entity_candidate` incelemesi açıldı (unvan, varlık değil). Temple of the Moon adayı ise geçerli.
- Güvenlik metriklerinin hepsi **0**: future_knowledge_violation, wrong_semantic_accepted, wrong_direction_accepted, unsupported_high_impact_accepted, invalid_evidence_accepted, destructive_identity_merge, unsupported_review_accepted (yukarıdaki düşük önemli aday gürültüsü hariç), deterministic_duplicate_written. Korunan tablolar önce/sonra hash eşit.

## L. Kategori analizi

| Kategori | Beklenen | Buldu | Dönüştü |
|---|---:|---:|---:|
| relationship (liderlik) | 3 | 3 | **0** |
| life_status | 2 | 2 | 1 |
| identity/title | 2 | 1 | 1 |
| location | 1 | 1 | 0 |
| role | 1 | 0 | 0 |
| lineage (boşluk) | 1 | 0 | 0 |

**Sistematik kayıplar:**
1. Liderlik ilişkileri 0/3 dönüştü: doğrulayıcıda edilgen kalıp yok, epistemik kapı kanıttaki yan cümleye takılıyor.
2. Model kimlik açığa çıkmasını (Effie=Athena), rolü ve soy boşluğunu hiç üretmedi.

Hata sınıfları:
- **VALIDATOR CONVERSION:** 5 öğe (baskın sınıf).
- **MODEL DISCOVERY:** 3 öğe.
- **RELATION VOCABULARY:** 1 (soy).
- **DETERMINISTIC:** kayıp yok.
- **CONTEXT:** kanıt yok.

## M. Sağlayıcı ve maliyet

- Görülen regresyon: 4 çağrı, 4 deneme.
- Holdout: 10 mantıksal çağrı, 12 deneme. Bir 429 ve bir 504, sınırlı geri-çekilmeyle aynı Vertex modelinde başarılı oldu.
- Hepsi `vertex/gemini-3.8-flash`; **ücretsiz Gemini 0**, başka sağlayıcı 0, PROVIDER_BLOCKED 0.
- Holdout tokenları: giriş 149.446 · çıkış 2.628 · düşünme 62.153 → **~0,36 $**. Görülen regresyonla birlikte bu turun toplamı ~0,50 $.
- Gecikme 17–176 sn, ortalama 65 sn.

## N. Testler

- `pytest tests -q`: **1141 passed**. `git diff --check` temiz.
- Yeni dosya `tests/test_v6_temsil.py` (49 test). Kapsadığı vakalar:
  - zamir olumlu/olumsuz: iki aday, üç aday, paragraf sınırı, iki cümle geri, iyelik;
  - ceset ve benzetmeler;
  - True Names tekil/çoğul ve belirsiz eşleme;
  - rol;
  - rün alt satırı mirası ve sızıntı olumsuzları;
  - ipucu çıkarımı, tekilleştirme, sınır, olgu olmaması;
  - değiştirilemezlik.
- Beş mutasyon sınaması (zamir kapalı, tek aday şartı gevşek, True Names, rün sızıntısı, kategori sınırı) ve ceset benzetme mutasyonu her biri en az bir testi düşürdü.

## O. Öneri

**HOLDOUT FAIL**

Yeni tur, model kıyası, ilişki yeniden tasarımı, üretim modeli değişikliği ve 1–100 başlatılmadı. Bu holdout artık görülmüş sayılmalı.
