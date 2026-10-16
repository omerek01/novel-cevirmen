# Sözlük ön taraması — iki kollu çeviri ölçümü (2026-10-17)

Soru: yeni bir kitapta, ilk bölümler çevrilmeden önce sözlük ön taraması
(`sozluk_tarama.on_tara`, `SOZLUK_ON_TARAMA=1`) çeviriyi iyileştiriyor mu?

## Düzen

- Kitap: RSSG (`reincarnation-of-the-strongest-sword-god`), önbellekteki ilk 10 bölüm
  (1710–1719). Soğuk başlangıç: canlı DB'nin sunucudaki geçici kopyasında RSSG sözlüğü
  boşaltıldı, diğer bölümler ve canlı çeviriler silindi. Canlı veriye yazılmadı.
- Akış: canlı çeviri yolu (`pipeline._do_fetch_translate_save`) — bekleyen terim
  doğrulaması, sözlük, önceki bölüm bağlamı, algılanan terimin sözlüğe işlenmesi. Canlı
  bayraklar (`CEVIRI_CILALA`, `CEVIRI_GRAFIK`, `SOZLUK_SIRADAN`…), zincir
  `vertex/gemini-3.8-flash` önde. Defter ve otomatik profil kapalı.
- Kollar sırayla: **A** taramasız, **B** çeviriden önce ön tarama, **A2** taramasız tekrar
  (gürültü tabanı). Her kol ~31–34 dk; hata yok, hizalama 30/30.
- Referans: RSSG'nin canlıdaki oturmuş sözlüğü (285 etkin kayıt, 137'si korunan ad).
  Ölçüt: hizalı paragrafta kaynakta kayıtlı terim geçiyorsa çeviride kayıtlı karşılık
  (Türkçe çekimleriyle, `turkce_eslesme`) var mı.
- Kör hakem: `scripts/anlam_kiyas.py yargila-bolum`, `gemini-2.5-pro`, çiftler B:A ve A2:A,
  bölüm düzeyi, iki yön.

## Sonuç

| Ölçüt | A | B | A2 |
|---|---:|---:|---:|
| Referansa terim uyumu (geçiş ağırlıklı) | %56,9 | **%68,1** | %46,7 |
| Aynısı, ilk 3 bölüm | %45,8 | **%75,4** | %41,2 |
| Terim başına ortalama uyum (47 terim) | %49,8 | **%58,9** | %46,7 |
| Referansla tam tutarlı terim | 21 | **24** | 21 |
| Korunan ad uyumu | %95,0 | %95,0 | %94,8 |
| Kolun KENDİ sözlüğüyle tutarlılık | %99,5 | %99,6 | %99,1 |
| İlk bölümde etkin sözlük kaydı | 0 | 14 | 0 |
| Sızıntı / karşılık sapması | 0 / 0 | 0 / 0 | 0 / 0 |

Ön tarama: 25 öneri → 15 yazıldı, 10 elendi, 33 sn, `gemini-3.6-flash`.

Kör hakem (10 bölüm):

| Çift | Boyut | a | b | eşit | p |
|---|---|---:|---:|---:|---:|
| B:A | anlam | 0 | 0 | 10 | 1,00 |
| B:A | akış | 1 | 0 | 9 | 1,00 |
| A2:A | anlam | 0 | 0 | 10 | 1,00 |
| A2:A | akış | 1 | 1 | 8 | 1,00 |

## Yorum

- Ön tarama sözlüğü ilk bölümden kurar (0 yerine 14 etkin kayıt) ve kitabın SONRADAN
  oturan karşılıklarına erken yaklaşır: ilk 3 bölümde referans uyumu %46 → %75.
- Gürültü büyük: aynı kolun tekrarı (A2) A'dan 10 puan aşağıda. Geçiş ağırlıklı farkın
  %89'u (B–A) ve %95'i (A2–A) en sık 5 terimden geliyor; terim başına ortalama ölçütte
  B'nin farkı +9 puan, A2'nin −3 puan.
- Kalite farkı yok: hakem anlamda 10/10 eşit; akış farkı gürültü tabanı içinde.
- Her kol kendi sözlüğüne zaten tutarlı (%99+). Ön tarama tutarlılığı değil, karşılığın
  ilk seçimini değiştiriyor: kullanıcının sonradan düzelteceği karşılık sayısını azaltma
  ihtimali var (eski bölüm onarımı, K6), bu tek koşuyla kanıtlanmadı.

Sınırlar: tek kitap, tek koşu, 10 bölüm; referans sözlük sonradan elle düzeltilmiş
olduğundan "doğru" değil "kitabın oturmuş hâli"dir. Ölçüm çıktısı (roman metni içerir)
yerelde tutuldu, depoya konmadı; sunucudaki iş dosyaları ve geçici DB'ler silindi.
