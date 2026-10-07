# Faz 2A v7 — Aday-öncelikli çıkarım + span kimlikli kanıt

**Karar: HOLDOUT FAIL**

Güvenlik temiz. Kalite kapılarının hiçbiri geçmedi:

| Katman | Sonuç | Eşik |
|---|---:|---:|
| L1 aday recall | 0,67 | 0,90 |
| L2 model sınıflandırma | 0,83 | 0,80 |
| L3 doğrulayıcı dönüşümü | 0,60 | 0,85 |
| L4 toplam kapsama | 0,50 | 0,80 |

L2 eşiği tek başına aştı. **Gold yalnız 6 öğeden oluşuyor; metrikler gürültülü.** 1–100 başlatılmadı, `CIKARICI_MODELI` değişmedi.

## Mimari (yeni: `app/core/bilgi_aday.py`)

- **Span'lar:** `span_ayir` kaynağı cümle span'larına böler. Kimlik biçimi `ch{N}:p{satır}:s{cümle}`, kararlıdır; `kaynak[start:end] == text` her zaman doğrudur.
- **Kanıt:** model kanıt METNİ yazmaz, yalnız `evidence_span_ids` döndürür (en çok 3, bitişik, aynı paragraf). Kanıt metni uygulama tarafından kaynaktan alınır.
- **Şema:** `delta-4-span-evidence` (çıkarıcı 8, istem 7). Eski v7 yolu aynen duruyor.
- **Aday üretici:** yalnız kaynak metne bakar; N−1 grafiğini kullanmaz.
  - 15 kategori.
  - Her adayda ad anmaları (sözlük, yazımlar, N−1'e kadar onaylı takma adlar, yeni özel adlar) ve zamir öncül adayları bulunur. Öncül adayları en çok 2 cümle geriden alınır; paragraf dışından gelen öncül işaretlenir.
  - Rün satırları aday olmaz.
  - Sınırlar: en çok 24 aday, 1600 token tavanı. Holdout'ta 9–17 aday, ortalama ~520 token.
- **Serbest keşif:** en çok 3; o da span kimliği vermek zorunda.
- **Doğrulayıcı:**
  - Yapısal denetimler: aday/span kimliği geçerli mi, span'lar bitişik mi, uçlar izinli küme içinde mi, kelime dağarcığına uyuyor mu, yön ters mi.
  - Anlamsal denetim yalnız iki katmanda yapılır:
    - yüksek etki: `oldurdu`, `donustu`, `gercek_adi`, yaşam durumu, kimlik, güncelleme;
    - sahte birliktelik riski: simetrik ve sahiplik ilişkileri.
  - Epistemik denetim ve yüksek etkili anlamsal denetim, iddianın uçlarını içeren cümleye uygulanır (yerellik).
  - Belirsiz öncül ya da doğrulanamayan yüksek etkili iddia ret değil, incelemeye düşer.
  - Kimlik açığa çıkması önce incelemeye gider; birleştirme yapılmaz.
- **Ek genel kalıplar:** edilgen liderlik/öğretme ("Y was led by X"), "X's death / death of X".

## Holdout ön-dondurma

10 bölüm, kod değişikliğinden ve kaynak okunmadan önce seçildi: 45, 102, 256, 318, 414, 491, 583, 707, 816, 938.
- Tohum 20261008, SHA-256 `db5e06a5…2730`.
- Dışlama kümesi bilinçli olarak geniş tutuldu: raporlarda geçen her bölüm no dışarıda.

## Görülen regresyon (141, 374, 460, 556, 659, 681; 6 Vertex çağrısı)

- L1 aday recall: 15/15.
- L2: 10/15.
- L3: 8/10 = 0,80. İddia yerelliği düzeltmesinden sonra, model çağrısı olmadan yeniden oynatmada 10/10.
- Kabuller 6/6 doğru; yanlış kabul 0.
- Bu, holdout'a geçiş şartını sağladı.

## Dondurma

- Sistem: `frozen-system-v8.json`, SHA-256 `1438eafe…`.
- Gold: `holdout-v7-gold.json`, SHA-256 `dd32333c…`.
  - 6 öğe, span kimlikli.
  - Kaynak tam metin okundu; aday süzgeci kullanılmadı.
  - 5 bölüm boş gold (102, 256, 491, 707, 816).
- Model sonrası değişiklik yok.

## Kör holdout

| Öğe | Aday | Model | Sonuç | Sahip |
|---|---|---|---|---|
| 45 Sunny ogretmeni Nephis | ✓ | ✓ | ret: entity_not_allowed | ADAY PAKETİ: cümle ortasındaki "he" zamiri öncül listesine alınmadı |
| 45 Sunny role scout | ✓ | ✓ | ret: role_value_not_in_claim | DOĞRULAYICI: iddia penceresi ", who" sınırında kesildi |
| 318 Kai anisi Blood Arrow | ✓ | ✓ | doğru inceleme | – |
| 414 Mirror Beast dead | ✓ | ✗ | eksik | MODEL |
| 583 Sunny dusmani Mordret | ✗ | ✓ (serbest) | doğru inceleme | ADAY ÜRETİCİ: "enmity" ipucu yok |
| 938 Luster role pilot | ✗ | ✓ (serbest) | **kabul** | ADAY ÜRETİCİ: "pilot" ipucu yok |

- **Hassasiyet:** 1/1. Tek kabul Luster role pilot ve doğru.
- **İnceleme/boşluk doğruluğu:** 6/6 makul (ayrıntı `holdout-v8-results.json`).
- **Güvenlik:** yanlış kabul, ters yön, gelecek sızıntısı, geçersiz span kabulü, kanıtsız yüksek etkili kabul, yıkıcı birleştirme ve deterministik kopya yazımı **0**. Korunan tablolar önce/sonra eşit.
- **Sağlayıcı:**
  - 10 mantıksal çağrı, 14 deneme; hepsi `vertex/gemini-3.8-flash`, ücretsiz Gemini 0.
  - 707'de beş 429 sınırlı yeniden denemeyi tüketti → **PROVIDER_BLOCKED**. Operasyonel kapsam 9/10. Bu bölümün gold'u boş olduğu için kalite paydası etkilenmedi.
- **Maliyet:** ~0,17 $ (giriş 93.817 · çıkış 1.238 · düşünme 24.703). Görülen regresyon dahil bu tur ~0,40 $.

## Değerlendirme

- **Span mimarisi hedeflediği sorunu çözdü:** geçersiz/uydurma kanıt sayısı 0, tırnak ve kopyalama hatası yok. Giriş tokenları v6'ya göre yaklaşık %25 düştü.
- **Kalan kayıplar katmanlara dağılmış durumda:**
  - aday üretici: dar ipucu sözlüğü (enmity, pilot);
  - aday paketi: yalnız cümle başı/bağlaç sonrası zamirlere öncül veriyor;
  - doğrulayıcı: iddia penceresi yan cümledeki iddiayı kesiyor;
  - model: 1 eksik.
- Bunların hiçbiri güvenlik ihlali değil. Görülen sette ölçülen 0,80–1,00 dönüşüm kör sette 0,60'a düştü; sette genelleşme açığı var.

## Testler

- `pytest tests -q`: **1171 passed**; `git diff --check` temiz.
- Yeni dosya `tests/test_aday_v8.py` (30 test). Kapsadığı konular: span kararlılığı, geçersiz/çapraz bölüm/bitişik olmayan span, izinli/belirsiz/paragraf dışı öncül, etken/edilgen liderlik, epistemik yerellik, adlaştırılmış ve ceset ölümü, parazit, True Names, rol, soy boşluğu, kimlik incelemesi, aday tekilleştirme/sınırı, rün ayrımı, serbest keşif sınırı ve geçerli span, sağlayıcı ve değiştirilemezlik.
- Dört mutasyon sınaması (yön, öncül, bitişiklik, paragraf) testleri düşürdü.

## Öneri

**HOLDOUT FAIL**

Yeni tur, model kıyası, ilişki yeniden tasarımı, üretim modeli değişikliği ve 1–100 başlatılmadı.
