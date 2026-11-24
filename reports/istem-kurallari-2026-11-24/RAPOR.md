# CEVIRI_ISTEM_KURALLARI ölçümü (2026-11-24)

**Sonuç: ölçülebilir iyileşme yok; bayrak kapalı kalır.**

## Kurulum

- Bölümler: Shadow Slave 1812, 1814, 1828, 1833, 1834, 1835, 1839, 1851, 1859, 1863, 1864, 1865
  (diyalog, ünlem ve `[ ]` sistem bloğu yoğun olanlar), canlı DB'den salt okunur, defter kartlarıyla
  (`hazirla --db`).
- Kollar (`scripts/anlam_kiyas.py`): L = canlı yol (H + kart + `SOZLUK_TERIM_OLCUTU`),
  L2 = L'nin tekrarı (gürültü tabanı), M = L + `CEVIRI_ISTEM_KURALLARI=1`.
- Çeviri modeli `vertex/gemini-3.8-flash`. Canlıda seçili `vertex/gemini-4-argon` kullanılamadı:
  bu deneme hesabında Gemini 4 ailesi o saatlerde her çağrıda 429 veriyordu (bkz. `CLAUDE.md`
  `defter_modeli`). 36/36 çeviri hatasız.
- Hakem `gemini-2.5-pro`, kör, X/Y sırası rastgele; paragraf ve bölüm düzeyi.

## Kuralların doğrudan hedefleri (belirlenimci sayım)

| Kol | İngilizce kalan ünlem (kaynakta 7) | `[ ]` satırı korunan | Uzunluk oranı |
|---|---:|---:|---:|
| L | 0 | 30/30 | 0,977 |
| L2 | 0 | 30/30 | 0,981 |
| M | 0 | 30/30 | 0,984 |

Hedeflenen hatalar taban yolda da yok. Ret geri bildirimi (`_ret_notu`) çıktıda iz bırakmadığı
için tetiklenip tetiklenmediği ölçülmedi.

## Hakem

Paragraf (a kazandı / b kazandı / eşit, işaret testi p):

| Çift | Anlam | Akıcılık | Tutarlılık |
|---|---|---|---|
| M:L | 101 / 108 / 252 (0,68) | 43 / 59 / 359 (0,14) | 6 / 15 / 440 (0,08) |
| L2:L | 110 / 94 / 250 (0,29) | 62 / 65 / 327 (0,86) | 8 / 16 / 430 (0,15) |

Bölüm (12 bölüm):

| Çift | Akış | Anlam | Kopukluk/bölüm a – b |
|---|---|---|---|
| M:L | 3 / 4 / 5 | 0 / 1 / 11 | 1,33 – 1,21 |
| L2:L | 2 / 2 / 8 | 1 / 0 / 11 | 1,17 – 1,29 |

M:L farkları L2:L gürültüsüyle aynı büyüklükte; hiçbiri anlamlı değil. M akıcılık ve tutarlılıkta
hafifçe geride, ama gürültü tabanı da tutarlılıkta aynı 1:2 oranını veriyor.

## Sınırlar

Tek kitap, 12 bölüm, tek koşu, tek çeviri modeli (canlıdaki Argon değil), tek hakem. Argon ile
kuralların etkisi farklı olabilir; Argon kullanılabilir olunca aynı veriyle (`ham/ornekler.json`)
L/M kolları tekrar koşulabilir. Ham veri (`ham/`) roman metni içerir, git'e eklenmez.
