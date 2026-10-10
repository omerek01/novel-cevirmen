# Roman bağlamı (bölüm analizi + N-1 özet) — ölçüm raporu, 2026-10-10

Model: vertex/gemini-3.6-flash, tek model, yedeksiz. Girdi: salt-okunur DB yedeği
kopyasından Shadow Slave 961/957, RSSG 1766; sözlük/koşul tek snapshot. Canlı DB'ye yazılmadı.

## 1. İlk koşu: analiz açık kolların hepsi düştü (`kiyas.jsonl`)

Analiz açık 3/3 deneme `KaliteKontrolHatasi` ile çeviriye geçmeden durdu. Kayıtlı
yanıtların çevrimdışı tekrar oynatılması ve ücretli yoklama:

- 957 ve 1766: önceki bölüm özeti `MAX_TOKENS` ile 4092 tokenda kesildi (düşünme
  tokenları bütçeyi yedi). Kodda böyle bir tavan yok (32768 isteniyor); aynı çağrı
  tekrarında 4840 tokenla normal bitti. Geçici model davranışı.
- 961: kayıtlı yanıt yerelde geçiyor, sunucudaki tekrar koşuda da baştan sona tamamlandı.
  İlk koşudaki hata mesajı kaydedilmediği için kesin neden belirlenemedi.

## 2. Güvenilirlik ölçümü (`analiz-guvenilirlik.jsonl`, 3 tekrar × 3 bölüm)

| Çağrı | Geçen | Hata | Süre (ort.) |
|---|---:|---|---:|
| Önceki bölüm özeti, analiz talimatı + "terim üretme" | 2/9 | 5 tutmayan alıntı, 2 istenmeyen terim | ~21 sn |
| Önceki bölüm özeti, kısa özet talimatı | 8/9 | 1 tutmayan alıntı | ~10 sn |
| Bölüm analizi | 9/9 | — | ~22 sn |

Kök neden özet talimatıydı. Düzeltme (`a828141`): özet kendi kısa talimatıyla
istenir; kaynağa bağlanamayan madde/terim tek başına atılıp gerekçesiyle izde
kalır (kullanılan her madde yine birebir alıntılı); özette gelen terim yok sayılır.

## 3. Düzeltme sonrası açık/kapalı kıyas (`kiyas-v2.jsonl`)

| Bölüm | Analiz | Süre | Uzunluk oranı | Denetim bulgusu | Onarılan paragraf | Onarım |
|---|---|---:|---:|---:|---|---|
| 961 | kapalı | 56 sn | 0,987 | 1 | 1 | kabul |
| 961 | açık (6 özet, 24 terim) | 179 sn | 1,006 | 2 | 2 | kabul |
| 957 | kapalı | 58 sn | 0,947 | 0 | 0 | — |
| 957 | açık (6 özet, 10 terim) | 105 sn | 0,929 | — | — | reddedildi (`KaliteHatasi`) |
| 1766 | kapalı | 86 sn | 0,966 | 1 | 1 | kabul |
| 1766 | açık (6 özet, 4 terim) | 120 sn | 1,005 | 5 | 5 | kabul |

Bulgular:
- Analiz açık yol artık 3/3 bölümü çeviriyor; hiçbir özet maddesi/terim atılmadı.
- Süre analiz açıkken 1,4–3,2 kat uzun (ek analiz + özet çağrıları).
- Analiz açık kolda kalite denetimi DAHA ÇOK hata buldu (961: 2'ye 1, 1766: 5'e 1).
  Her kol tek üretimdir; bu bir kalite düşüşü kanıtı değildir ama **analizin kaliteyi
  artırdığı da gösterilemedi**. Hataların insan tarafından okunması gerekir.
- Kalite denetimi bu deneyde aynı modelle yapıldı; tek koşu, üç bölüm.

## Sonuç

Analiz/özet yolu artık güvenilir çalışıyor. Kalite kazancı kanıtlanmadığı için canlıya
almadan önce analiz açık/kapalı çevirilerin (özellikle 1766'daki 5 bulgu) okunarak
karşılaştırılması ve daha fazla bölümde tekrar ölçülmesi önerilir. Push/dağıtım yapılmadı.
