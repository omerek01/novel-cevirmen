# Faz 2A v5.2 — Genellik temizliği + kör holdout (Vertex Gemini 3.8 Flash)

**Karar: HOLDOUT FAIL**

Temizlik geçti. Holdout'ta güvenlik kapılarının hepsi temiz (yanlış kabul 0), ama kalite kapısı geçmedi:
- Düzyazı (model) recall_proxy **0,06** (eşik 0,80).
- Effective coverage **0,36–0,40** (eşik 0,80).
- Birden fazla kategoride sistematik kayıp var.

1–100 önerilmiyor. `CIKARICI_MODELI` değiştirilmedi.

## A. Genellik temizliği

- `stood in its middle` kaldırıldı. Konum doğrulaması artık `konum_kaniti()` ile yapılıyor:
  - İpuçları tam kelime olarak aranıyor (`in, inside, into, at, within, on, entered, reached, arrived at/in, remained/stayed/stood/lived/located/situated in|at…`).
  - İpucu yerin hemen önünde olmalı; araya yalnız belirteç girebilir.
  - Özne ile ipucu aynı cümlecikte olmalı: virgül ya da cümle sonu yok; `who/which/and/but/while…` yok; konum dışı `in` (believed/interest/faith/trust…) yok; araya giren başka büyük harfli ad yok.
  - Ek kalıplar: "X, where Y" / "home of" ve önceki cümlenin konusuna `its/their (middle|center|heart…)` ile genel artgönderim.
  - Kurulamayan konum kabul edilmez, "yön doğrulanamadı" olarak incelemeye düşer.
- `parcasi` ipucuna kelime sınırı eklendi.
- `walked in, alive` kaldırıldı. Yerine genel kalıplar: `is/was/were/remained/stayed/still alive`, `survived`, `was not dead` ve "alive"ın açıkça söylendiği yüklem biçimi (`<ad> …, still alive`). walked/spoke/moved/appeared/stood tek başına canlılık kanıtı değil.
- Ölüm kuralları değişmedi.
- `CIKARICI_SURUMU` 5 → **6** (doğrulayıcı davranışı değişti). İstem metni aynı olduğu için `ISTEM_SURUMU=5`, şema `delta-3-v4-final` aynı kaldı.
- Testler: `tests/test_genellik_v6.py` (47 test; olumlu/olumsuz konum ve canlılık, ölüm güvenliği, kalıntı tel tuzağı).

## B. Temizlik sonrası yeniden oynatma (model çağrısı yok)

13 dondurulmuş ham yanıt (V4 final 7 + v5/3.6 3 + v5.1/3.8 3) yeni doğrulayıcıdan geçirildi.

- **12'si birebir aynı.** 431 inanç-konum gold'u genel artgönderim kuralıyla korunuyor; 848 canlılık gold'u `was alive` ile geçiyor.
- **Tek fark:** v5.1/3.8'deki `Sunny bulundugu_yer Altar Island` artık `işle` değil, `inceleme:yön doğrulanamadı`. Eski `remained`→"in" hatasına dayanıyordu ve gold öğesi değildi. Beklenen sonuç.
- Gold kaybı yok; yeni yanlış kabul, Gerçek Ad karışıklığı ya da öğretmen yönü değişikliği yok.
- Ayrıntı: `v6-cleanup-replay.json`.

## C. Dondurulmuş sistem

`frozen-system-v6.json`, SHA-256 `9eddec36…628a8f`.

| | |
|---|---|
| bilgi_delta.py | `2da92f5d…` |
| bilgi_kanit.py | `8bf3a628…` |
| varlik_grafigi.py | `6f6dca81…` |
| translate.py | `b5152949…` |
| validation_v5.py | `6c6ae42c…` |
| istem | `15453c39…99bc2` (v5 ile aynı) |
| şema | `a3ee7cac…` |
| sürümler | çıkarıcı 6, istem 5, şema `delta-3-v4-final` |
| bağlam bütçesi | 4000 |

Sunucuda açılan kod aynı hash'leri verdi.

## D. Holdout listesi

`8f57363c855dec513786c3201e051191373140bbe27a2e7d6984dd23c15ef4b7` (değişmedi): 83, 187, 343, 374, 542, 590, 681, 744, 782, 887.

## E. Gold

`holdout-gold.json`, SHA-256 **`5bef4de11349c237d10ef494783ddef7f72cacaede969e247f8183082c9efcd5`**.

- Kaynak metin elle okundu. Her aday N−1 grafiğine ve durumuna karşı salt-okunur denetlendi; zaten bilinenler alınmadı. Çıkarım modeli kullanılmadı.
- 25 öğe: 8 deterministik, 16 model, 1 inceleme.
- 187 ve 542 için yeni ve güvenilir bilgi bulunmadı; boş gold olarak gerekçeleriyle kaydedildi.
- **Model öncesi düzeltme (açık kayıt):** ilk dondurmada (`32b7b9ea…`) 744 Master of Shadows öğesine yanlış kanıt satırı kopyalanmıştı. Herhangi bir model çağrısından önce düzeltildi ve dosyada `pre_model_revision` alanıyla kayıtlı.
- **FIXTURE_CORRECTION (model sonrası keşif, gold dosyası DEĞİŞTİRİLMEDİ):** 83 `Sunny niteligi Blood Weave` "model" diye işaretlenmişti. Oysa bu, grafikte aynı bölüme ait kalıcı bir rün bağı (`b83 sistem`) ve istemin "ALREADY EXTRACTED" listesinde yer alıyor. Gerçek temsili deterministik; model onu doğru biçimde tekrarlamadı. Metrikler hem dondurulmuş hâle göre hem düzeltilmiş hâle göre verildi.

## F. Sağlayıcı

10 mantıksal çağrı, 10 deneme, hepsi `vertex/gemini-3.8-flash` ve HTTP 200, tekrar 0. İstenen zincir yalnız 3.8. **Ücretsiz Gemini 0**, başka sağlayıcı 0, PROVIDER_BLOCKED 0. Korunan tablolar (chapters, glossary, sozluk_yazim, varlik_bag, varlik_deger, bilgi_*) önce ve sonra hash eşit.

## G. Bölüm sonuçları

| Bölüm | Beklenen | Deterministik | Model buldu | Kabul | İnceleme doğru | Kapasite boşluğu | Yanlış | Eksik | Sonuç |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 83 | 5 | 4/4 | 0 | 0 | – | – | 0 | 0* | GOLD_ISSUE (*Blood Weave deterministik) |
| 187 | 0 | – | – | 0 | – | – | 0 | 0 | PASS (boş delta doğru) |
| 343 | 4 | – | 1 | 0 | – | – | 0 | 4 | MODEL_FAIL + VALIDATOR_FAIL |
| 374 | 3 | – | 2 | 0 | – | – | 0 | 3 | VALIDATOR_FAIL + MODEL_FAIL |
| 542 | 0 | – | – | 0 | – | – | 0 | 0 | PASS (boş delta doğru) |
| 590 | 1 | – | 0 | 0 | – | – | 0 | 1 | MODEL_FAIL |
| 681 | 3 | – | 2 | 1 | – | – | 0 | 2 | MODEL_FAIL + VALIDATOR_FAIL |
| 744 | 5 | 2/2 | 2 | 0 | 0/1 | – | 0 | 3 | VALIDATOR_FAIL + MODEL_FAIL |
| 782 | 1 | – | 1 | 0 | – | – | 0 | 1 | VALIDATOR_FAIL |
| 887 | 3 | 2/2 | 0 | 0 | – | – | 0 | 1 | MODEL_FAIL |

Öğe öğe sonuç `holdout-results.json` içinde. Model bulup doğrulayıcının reddettiği 7 öğe:

| Öğe | Red sebebi |
|---|---|
| Crimson Terror dead | "corpse of the Crimson Terror", ölüm kalıbında yok |
| Kai gercek_adi Nightingale | kanıtta "True Names" çoğul; `\btrue name\b` eşleşmiyor |
| Nephis alive (374) | zamir ("she") |
| Nephis alive (782) | zamir ("She") |
| Solvane oldurdu Elyas | zamir ("She") |
| Master of Shadows, Shadow Manifestation (744) | rün listesi biçimli sahiplik kalıbı yok |

Modelin hiç üretmediği 8 öğe: Hope → Demon of Desire, Nephis oldurdu Crimson Terror, Sunny oldurdu Caster, Soul Conduit, Rock rolü, Mordret–War God soyu, Shadow Manifestation (887), Child of Shadows bitişi.

## H. Hassasiyet / hatırlama

| | Dondurulmuş gold | FIXTURE_CORRECTION sonrası |
|---|---:|---:|
| model+inceleme beklenen | 17 | 16 |
| model buldu (anlamca doğru) | 8 | 8 (%50) |
| doğru temsil (kabul/eşdeğer atlama/inceleme) | 1 | 1 |
| **prose recall_proxy** | **0,059** | **0,062** |
| deterministik kapsama (ayrı) | 8/8 | 9/9 |
| **effective_fixture_coverage** | **0,36** | **0,40** |
| **precision_proxy** (bütün kabuller elle) | 1/1 = 1,00 | 1/1 = 1,00 |

Kabul edilen tek öğe `Elyas life_status dead` ve doğru. Hassasiyet 1,00 ama payda 1, yani anlamlı değil.

Reddedilen ya da incelemeye düşen ham öğeler anlamca doğru ya da zararsız: Silver Bell Dormant/tier I, Gateway `parcasi` Crimson Spire, Obel `unvani` Professor. Kabul edilen yanlış öğe 0.

## I. Kategoriler (yalnız model öğeleri)

| Kategori | Beklenen | Buldu | Doğru |
|---|---:|---:|---:|
| identity/title | 2 | 1 | 0 |
| life_status | 4 | 4 | 1 |
| kill/death (ilişki) | 3 | 1 | 0 |
| relationship (nitelik/yetenek/soy) | 5 | 2 | 0 |
| other state (rol) | 1 | 0 | 0 |
| conflict/update (inceleme) | 1 | 0 | 0 |
| epistemic / capability_gap | 0 | – | – |

**Sistematik kayıplar:**
1. **Zamirle bağlanan kanıt:** 3 öğe doğru bulundu ama adsız zamir yüzünden reddedildi. Doğrulayıcı "kanıtta iki ad" kuralı gereği bunları kuramıyor.
2. **Rün listesi biçimli sahiplik** (nitelik/yetenek): 0/5 doğru.
3. **İlişki olarak öldürme:** 0/3.
4. **Unvan ve Gerçek Ad:** 0/2. Hope unvanı hiç üretilmedi; Kai'nin Gerçek Adı çoğul "True Names" yüzünden reddedildi.

Bilinen regresyon setinin (313/670/691) 1,00 sonucu bu dağılımı temsil etmiyormuş. O set, mevcut kalıplara uyan kanıt cümlelerinden oluşuyordu.

Hata sınıfları:
- **VALIDATOR:** 7 öğe; temsil gücü dar, gevşetilmedi.
- **MODEL CAPABILITY / PROMPT:** 8 öğe.
- **GOLD ISSUE:** 1 öğe.
- **CONTEXT RETRIEVAL:** kanıtlanmadı (kesilen satır 0–158).
- DETERMINISTIC PARSER: 0. RELATION VOCABULARY: kesin değil (soy ilişkisi `akrabasi` ile sınırda).

## J. Güvenlik

schema_failures 0 · future_knowledge_violations 0 (bağlam N−1, en fazla 3995 token) · wrong_direction_accepted 0 · wrong_semantic_relation_accepted 0 · high_impact_unsupported_accepted 0 (2 yüksek etkili öneri reddedildi) · unsupported_review_accepted 0 · true_name_confusions 0 · destructive_identity_merges 0 · unnecessary_identity_reviews 0 · deterministic_duplicates_raw 0 / written 0 · invalid_evidence_accepted 0.

## K. Maliyet / gecikme

Giriş 149.877 · çıkış 2.346 · düşünme 45.150 token → **~0,29 $** (≈0,029 $/bölüm, tanıtım fiyatı; fatura değil). Gecikme 19–71 sn, ortalama 40,9 sn, toplam 409 sn.

## L. Testler

`pytest tests -q`: **1092 passed** (3 mevcut uyarı). `git diff --check` temiz.

## M. Öneri

**HOLDOUT FAIL**

Yeni istem turu, doğrulayıcı değişikliği, model kıyası ve 1–100 başlatılmadı. `CIKARICI_MODELI` 3.6'da kaldı. Holdout sonucu görüldükten sonra hiçbir kural değiştirilmedi.

Karar için not (uygulanmadı): kayıpların yarısı doğrulayıcının **temsil gücü** sınırından geliyor (zamir bağlantısı, rün listesi sahipliği, "corpse", çoğul "True Names"), yarısı model recall'ından. Herhangi bir doğrulayıcı genişletmesi yeni bir kanıt kuralı kararıdır ve ancak YENİ bir kör holdout ile ölçülebilir. Bu holdout artık kullanılmış sayılmalı.
