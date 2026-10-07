# Faz 2A v5.1 — Vertex çıkarıcı model kıyası (3.6 Flash ve 3.8 Flash)

**Karar: MODEL COMPARISON PASS — GEMINI 3.8 RECOMMENDED**

Sistem dondurulmuş v5'tir: istem, doğrulayıcı, şema, bağlam ve gold değişmedi. Holdout, 1–100 ve üretim ayarı değişikliği YAPILMADI.

## Kıyaslanabilirlik

- 3.6 için v5 ham sonuçları yeniden kullanıldı. 3.6 yeniden çağrılmadı, yeni Vertex çağrısı yalnız 3.8 için 3 adet.
- Sunucudaki `bilgi_delta.py`, `bilgi_kanit.py`, `translate.py` ve `varlik_grafigi.py` SHA-256'ları yereldeki v5 koduyla birebir aynı.
- Talimat SHA-256: `15453c39…99bc2`.
- Her bölümde N−1 bağlam satırlarının ve aynı bölüm deterministik satırlarının hash'leri v5 baseline ile eşit. Sürümler eşit (5/5/`delta-3-v4-final`). Doğrulama DB'si aynı ve korunan tablo parmak izi v5'in "before" değeriyle eşit.
- Giriş tokenları üç bölümde de iki model için bayt düzeyinde aynı: 15.979 / 15.552 / 15.581.
- Sıcaklık 0,3 ve düşünme ayarı tek yardımcıdan gelir (`_gemini_yapilandirmasi`), yani iki model için aynı.
- Gold SHA-256 `0d2fbead…610f` değişmedi.

## Sağlayıcı

| | 3.6 (v5) | 3.8 (yeni) |
|---|---|---|
| deneme | 3 × HTTP 200, tekrar 0 | 3 × HTTP 200, tekrar 0 |
| zincir | yalnız `vertex/gemini-3.6-flash` | yalnız `vertex/gemini-3.8-flash` |
| ücretsiz Gemini / başka sağlayıcı | 0 / 0 | 0 / 0 |
| PROVIDER_BLOCKED | 0 | 0 |

## Ana tablo

| Metrik | Gemini 3.6 Flash | Gemini 3.8 Flash |
|---|---:|---:|
| Expected items | 5 | 5 |
| Model found | 5 | 5 |
| Correctly represented | 4 | **5** |
| Validator accepted (yeni) | 2 | 4 |
| Equivalent skips | 2 | 2 |
| Invalid evidence | 2 (Prince, Lord of the Dead dead) | **0** |
| Wrong semantic items (ham, hepsi reddedildi) | 2 (Lord of the Dead oldurdu + dead) | 1 (Lord of the Dead `sinifi` Tyrant) |
| Unsupported high-impact (ham) | 2 | **0** |
| Missing | 1 | **0** |
| Precision proxy (kabul edilenlerin elle denetimi) | 2/2 = 1,00 | 4/4 = 1,00 |
| Recall proxy | 0,80 | **1,00** |
| Avg latency | 32,1 sn | 42,9 sn |
| Avg input tokens | 15.704 | 15.704 |
| Avg output tokens | 292 | 462 |
| Avg thinking tokens | 3.875 | 5.515 |
| Estimated cost/chapter | 0,0274 $ | 0,0342 $ |
| Total estimated cost | 0,0822 $ | 0,1026 $ |

Her iki modelde de aşağıdakilerin tamamı **0**: schema_failures, true_name_confusions, unnecessary_identity_items, wrong_direction_items, future_knowledge_violations, deterministic_duplicates_raw/written, kabul edilen yanlış öğe. Korunan tablo hash'leri önce ve sonra eşit.

3.8'in kabul ettiği ek öğe `Sunny bulundugu_yer Altar Island` doğru: bölüm adada geçiyor, 690'da oraya yöneliyorlar. Gözlem: doğrulayıcının `bulundugu_yer` kalıbı bunu `remained` içindeki "in" alt dizgisiyle eşledi. Kalıp kelime sınırı denetlemiyor; bu turda dokunulmadı.

3.8'in reddedilen ya da incelemeye düşen ham öğeleri:
- `Lord of the Dead sinifi Tyrant`: Tyrant sınıf değil rütbe, yani yanlış ilişki türü. "said to" ifadesi yüzünden epistemik kapıda reddedildi.
- `Nether turu daemon` ve `Demon of Oblivion turu daemon`: yön doğrulanamadı, NEEDS_REVIEW önerisi olarak kaldı ve kabul edilmedi.

## Bölüm bazında

| Bölüm | 3.6 | 3.8 | Kazanan / not |
|---|---|---|---|
| 313 | PASS. Kido dead kabul. Lord of the Dead oldurdu/dead önerdi, ikisi de reddedildi. | PASS. Kido dead kabul. Lord of the Dead ölümü hiç ÖNERİLMEDİ. | 3.8: daha temiz, güvenlik yükü yok |
| 670 | PASS (doğru yön, aynı-N eşdeğer atlama) | PASS (aynısı) | eşit |
| 691 | FAIL. Prince kanıtına kaynakta olmayan `’` eklendi. | PASS. Üç unvan da doğru kanıtla. | 3.8 |

## 691 özel denetim

| Öğe | 3.6 | 3.8 |
|---|---|---|
| Nether → Demon of Destiny | bulundu, `unvani`, birebir kanıt, aynı-N eşdeğer atlama | aynısı |
| Nether → Prince of the Underworld | bulundu, `unvani`; kanıt **birebir değil** (sona `’` eklendi) → reddedildi | bulundu, `unvani`; kanıt **birebir** → kabul |
| Hope → Demon of Desire | bulundu, `unvani`, birebir, kimlik karışıklığı yok → kabul | aynısı → kabul |

Prince kanıtının sonu, yan yana:

```
kaynak : …and he was also the Demon of Destiny, it seems. Wait, aren’t fate…
3.6    : …and he was also the Demon of Destiny, it seems.’     ← kaynakta olmayan ’
3.8    : …and he was also the Demon of Destiny, it seems.      ← birebir
```

İki model de baştaki açılış `’` karakterini kaynakta OLDUĞU için doğru kopyaladı.

## Maliyet projeksiyonu (yalnız çıkarıcı, 3.8)

Ortalama 0,0342 $/bölüm. Gözlenen aralık 0,020 $ (670) ile 0,050 $ (313); fark düşünme tokenlarından geliyor.

| Kapsam | Ortalama | Aralık |
|---|---:|---:|
| 1–100 pilot | ~3,4 $ | 2,0–5,0 $ |
| 1–946 geçmiş doldurma | ~32 $ | 19–47 $ |

Uyarılar:
- Örneklem 3 geç bölüm ve bağlam dolu (4000). Erken bölümlerde bağlam küçük olduğu için giriş biraz daha az olur, yani tahmin yukarı yönlü.
- Fiyat tanıtım fiyatıdır (0,75/3,75 $). 2027'den itibaren 3.6 için 1,50/7,50 $ bekleniyor; 3.8 de aynı olursa rakamlar iki katına çıkar.
- 3.8 her bölümde ~10 sn daha yavaş.
- Tahmin fatura değildir.

## Sınırlar

- Her model her bölümde **tek koşu**. 3.6'nın tırnak kayması rastgele de olabilir; tek bir 691 koşusu bunu ayırt edemez.
- 3.8 yalnız bu 3 bölümde ölçüldü. Kör holdout hâlâ şart.
- Testler: `pytest tests -q` **1045 passed**. Yeni test: kıyas betiğinin yalnız Vertex modeli kabul etmesi. `git diff --check` temiz. Değişen tek kod `scripts/validation_v5.py` (`--model` seçeneği ve girdi hash'leri).

## POST-COMPARISON GENERICITY CLEANUP REQUIRED

`bilgi_kanit.py` içinde iki ifade kalıntısı duruyor: `stood in its middle` (bulundugu_yer) ve `walked in, alive` (alive). Bunlar holdout'tan ÖNCE genel kurallarla değiştirilmeli. Aynı temizlikte `bulundugu_yer` kalıbına kelime sınırı eklenmesi de ele alınabilir (yukarıdaki `remained` gözlemi).

## Öneri

Kör holdout'un `vertex/gemini-3.8-flash` ile çalıştırılması. Önce yukarıdaki temizlik yapılmalı, sonra dondurulmuş liste (`holdout-chapters.json`, SHA-256 `8f57363c…`) kullanılmalı. Çıkarıcının varsayılan modeli (`CIKARICI_MODELI`) DEĞİŞTİRİLMEDİ.
