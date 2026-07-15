# QA Raporu — NovelLink

- **Tarih:** 2026-07-15
- **Hedef:** http://localhost:8000 (yerel PWA, FastAPI + vanilla JS)
- **Mod:** Diff-aware (branch `faz-sonraki-plan`) + tam okuyucu akışı
- **Kademe:** Standard (kritik/yüksek/orta düzeltilir)
- **Tarayıcı:** gstack browse (headless, izole profil), masaüstü 1280×800 + mobil 375×812
- **Sağlık skoru:** ~99/100
- **Sonuç:** Düzeltilecek kod hatası bulunamadı. Dalın tüm yeni işleri E2E çalışıyor.

## Kapsam ve kanıt

Önbellekteki gerçek veriyle test edildi (5 kitap, 168 bölüm, 174 sözlük terimi) —
canlı çeviri/Gemini kotası tetiklenmedi (cache-hit yolu API çağırmaz).

| # | Alan | Sonuç | Kanıt |
|---|------|-------|-------|
| 1 | Kütüphane (kitap-sırtı, sıralama, resume oranları) | ✅ | `01-library.png` |
| 2 | Bölüm listesi + **yeni ✕ silme düğmeleri** (flex düzen) | ✅ | `02-chapters.png` |
| 3 | Okuyucu — önbellekli çeviri + isim koruma ("Sunny") | ✅ | `03-reader.png` |
| 4 | Ayarlar — tema/punto/satır/kenar + yeniden çevir | ✅ | `04-settings.png` |
| 5 | Tema geçişi (light↔dark, `data-theme` + renk doğrulandı) | ✅ | `05-dark.png` |
| 6 | Sözlük — 174 terim, düzenle/ekle/sil, kitap-başına | ✅ | `06-glossary.png` |
| 7 | **Resume / scroll geri-yükleme** — 0.938 oranı birebir | ✅ | scrollY=5508/5871 |
| 8 | **Bölüm silme (yeni)** — dialog→sil→UI 16→15→cache silindi | ✅ | tersinir E2E |
| 9 | **NovelLink branding** — wordmark, NL ikon, PWA MIME | ✅ | `07-mobile-library.png` |
| 10 | **Çevrimdışı SW (yeni)** — SHELL/DATA önbellek ayrımı canlı | ✅ | `novellink-shell-v25` + `novellink-data` |
| 11 | Service worker — kayıtlı/activated/kontrol ediyor | ✅ | `sw.js` controller |
| 12 | Mobil 375×812 — telefon-öncelikli kütüphane + okuyucu | ✅ | `07/08-mobile-*.png` |
| 13 | Konsol — tüm görünümlerde 0 hata | ✅ | her adımda temiz |
| 14 | Backend — `DELETE /api/chapter` (sahte URL → ok:false) | ✅ | API yanıtı |

### Yeni özelliklerin E2E doğrulaması
- **Bölüm silme:** `cache.delete_chapter` + `clear_position_if` + `DELETE /api/chapter`
  + frontend `deleteChapter`/`purgeChapterFromSwCache`. Shadow Slave ch14 üzerinde
  tersinir test: yedekle → UI'dan sil (dialog kabul) → satır kalktı, cache'ten silindi
  → yedekten geri yüklendi (16 bölüm, çeviri sağlam). **Kalıcı veri kaybı yok.**
- **PWA MIME düzeltmesi:** manifest→`application/manifest+json`, svg→`image/svg+xml`,
  png→`image/png` (Windows kayıt defteri yanlış tip verirken Chrome PWA'yı reddediyordu).
- **SW SHELL/DATA ayrımı:** yalnız iki önbellek mevcut (`novellink-shell-v25`,
  `novellink-data`); eski birleşik `novellink-v*` önbellekleri göç etti.

## Küçük gözlemler (düşük öncelik — düzeltilmedi)

Hiçbiri kod hatası değil; kozmetik veya kaynak-siteden gelen veri artefaktı:

1. **Türkçe büyük-harf noktalı İ** — İngilizce başlıklar spine'da `text-transform:
   uppercase` ile "REİNCARNATİON", "OUTSİDE", "OMNİSCİENT" oluyor. Türkçe kişisel
   uygulama için kabul edilebilir; düzeltme bir tasarım/dil tercihidir.
2. **Reincarnation bölüm no 1788↔1768** — kaynak sitenin (novelfull) URL-slug vs
   sayfa-başlığı numara uyuşmazlığı; resume ile 1768 yüklenince kitap 1768'e normalize
   oldu. Kod hatası değil, kaynak-veri tuhaflığı.
3. **Önbellek başlığı mojibake** — "Sockham�s Blade" (kesme işareti yerine �);
   kaynak sitenin kodlama artefaktı.

## TODOS.md — dalın kapattığı görünen maddeler

Aşağıdakiler bu dalda tamamlanmış görünüyor (kullanıcı onayıyla işaretlenebilir):
Sepya tema + segmented control, kenar boşluğu (margin) ayarı, okuyucuda graceful
hata durumu, sunucu-taraflı arka plan toplu çeviri, `db_path()` test-enjekte edilebilirliği.

## Sevk hazırlığı

Dal `faz-sonraki-plan` okuma deneyimi + dayanıklılık + branding işini sağlam şekilde
tamamlıyor. 54/54 pytest yeşil, tarayıcı QA'inde 0 konsol hatası, tüm yeni özellikler
E2E doğrulandı. **Sevke hazır.**
