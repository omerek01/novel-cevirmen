# DURUM — ne yapıldı, ne kaldı

> Bu dosya projenin **tek durum panosu**. Her dilim bitip main'e girince buradan
> güncellenir. "Nerede kaldık?" sorusunun cevabı hep burada.
> Son güncelleme: 2026-07-19 · Ana dal (`main`) sürümü: SW kabuk **v49** · Testler: **151 geçiyor**

## Proje ne
Kişisel web roman + kitap çeviri okuyucusu. İngilizce içeriği (web siteleri, yapıştırılan
metin, EPUB/PDF dosyaları) özel isimleri bozmadan Gemini ile Türkçe'ye çevirip telefon-öncelikli
bir PWA'da sunar. Backend Windows PC'de; telefondan Tailscale/LAN ile `:8000`.

## Faz: Kaynak Çeşitliliği (onaylı plan 2026-07-18, /autoplan)

Amaç: içeriği yalnız 4 siteden değil; **yapıştırılan metin, web'den devam, EPUB, PDF**'ten de
okuyabilmek + okuma deneyimini (yaşayan raf, sonsuz okuma) güçlendirmek.

| # | Dilim | Durum | Özet |
|---|-------|-------|------|
| 1 | Okuma deneyimi + dayanıklılık | ✅ main'de | Swipe, bölüm-içi arama, tema/punto/kenar, toplu çeviri işi, çevrimdışı "kaldığın yer" |
| 2 | Yaşayan raf | ✅ main'de | Büyük "devam et" fişi, okuma istatistikleri, durum etiketi (okunuyor/bitti/beklemede) + raf filtresi |
| 3 | İş tipi altyapısı | ✅ main'de | `jobs` tip+params, tek-uçuş (single-flight), okuyucu önceliği, kota kapısı (budget) |
| 4 | Yapıştır / web'den devam | ✅ main'de | METİN sekmesi, takılan bölümü URL'ye yapıştır, web URL'sini kitaba çek, bölüm ekle modalı |
| 5 | ~~Yeni bölüm kontrolü (check-updates)~~ | ❌ **İPTAL** | Kullanıcı kararı (2026-07-19). Bir kez kodlanıp geri alınmıştı; değeri belirsiz bulundu, tümden düşürüldü. |
| 6 | Sonsuz okuma v2 + prefetch | ✅ main'de | Bölüm akışı (`article` başına), otomatik ekleme, konum {url, oran}, sonrakini ısıtma. Fix'ler: konum-track, geri'de scrollRestoration |
| 7 | EPUB/PDF görsel çeviri | ✅ main'de | PDF = çevrilmiş **sayfa görselleri** (resim/düzen korunur), EPUB = yerinde HTML çeviri; okudukça çevirir. Fix'ler: metin binmesi (dikey akış), kısa sayfa kaydırma |
| 8 | **Manga çevirisi (yerel motor)** | 🔨 **KODLANDI** (dal `dilim-8-manga`) | Yerel manga-image-translator: inpaint ile temiz silme + düzgün dizgi, KOTASIZ. Telefon QA bekliyor. |

**Ayrıca:** Çeviri modeli yalnız `gemini-3.1-flash-lite` (2.5 yedekleri kaldırıldı, kullanıcı kararı).

## Son eklenen: Manga çevirisi — YEREL MOTOR (dal `dilim-8-manga`, telefon QA bekliyor)
İlk deneme (Gemini-vision + PIL kutu bindirme) kullanıcı tarafından "aşırı kötü" bulundu (uzun
webtoon'da sayfa başına 4-5 vision çağrısı = kota; kutu bindirme yaklaşık). Kullanıcı **yerel motoru**
seçti (planın orijinal önerisi). Vision-yedek kod hâlâ duruyor (motor yoksa devreye girer).

**Motor:** `manga-image-translator` (app'in KARDEŞ dizini `../manga-image-translator`, AYRI venv).
Ağır görü işi YEREL: balon algılama + OCR + **LaMa inpaint** (orijinali temiz siler) + düzgün dizgi.
Bulut vision çağrısı YOK; yalnız metin çevirisi Gemini'ye (sayfa başına **1 ucuz** çağrı, batch).
`manga_engine.py` subprocess köprüsü (CPU, `--translator gemini`, `GEMINI_MODEL=gemini-3.1-flash-lite`).

**Kurulum (kullanıcının PC'sinde yapıldı, `../manga-image-translator`):** `git clone` + `py -3.12 -m
venv venv` + `venv/Scripts/python -m pip install -r requirements.txt`. Windows'ta **pydensecrf**
derlenmiyor → requirements'tan çıkarıldı + `manga_translator/mask_refinement/text_mask_utils.py`
import'u opsiyonel yamalandı (CRF iyileştirme atlanır). İlk çalıştırma modelleri indirir (~1-2GB).

**İki giriş yolu:** DOSYA (CBZ/ZIP/görsel) + URL (asurascans → sayfalar çekilir, reklam/öneri gridi
elenir). Reader: **kesintisiz** (webtoon, ayraçsız).

**Gerçek e2e (Swordmaster 15000px webtoon) GÖRSEL doğrulandı:** orijinal İngilizce temiz inpaint,
Türkçe balona düzgün dizildi ("TEMEL KILIÇ USTALIĞI TEORİSİ Mİ?") — sanki baştan Türkçe basılmış.

**Hız (2. tur — "çok yavaş yüklüyor" geri bildirimi):** iki kaldıraç.
1. **Tüm bölüm TEK batch (`translate_chapter_engine`):** bölümün tüm sayfaları TEK subprocess'te
   çevrilir → modeller **bir kez** yüklenir (sayfa başına ~49s → steady-state düşer). Her sayfa
   bittikçe cache'e yazılır; okuyucu "çevriliyor N/total" gösterip poll eder, hazır olan akarak gelir.
2. **Uzun şerit dilimleme (`_expand_tall_pages`, import'ta):** asurascans bölümü ~15000px devasa
   şeritler verir; motor bunu CPU'da ~26s'de çevirir. Şeridi **boşluk/gutter satırında** (saf-PIL
   satır-düzlüğü; app venv'de numpy yok) ~3600px parçalara böleriz → parça başına **~6-11s** ve
   içerik okuyucuya **her ~9s'de bir** akar (tam şeridi 26s beklemek yerine). Kesim yüksek-kontrast
   balonlardan kaçınır → konuşma balonu bölünmez (görsel doğrulandı). Kısa görsel (CBZ/normal manga)
   dokunulmaz.
- **Config ayarı:** motorun "çeviri orijinaliyle aynı" post-check retry'ı SFX'te (URK.../PFFT!) yanlış
  tetikleniyordu → sayfa başına 4 gereksiz Gemini çağrısı; `enable_post_translation_check:false` ile kapatıldı.
- **Sınırlar/sonraya:** CPU-only makine (GPU yok — en büyük kaldıraç kapalı); ilk sayfa model yükleme
  nedeniyle ~25-35s bekler (sonrası akar); SFX çevrilmez (doğru); motor kurulu değilse Gemini-vision
  yedeğine düşer. Daha da hızlı için "server modu" (modeller kalıcı yüklü) ileride.

## Bilinçle ertelenenler (ihtiyaç olunca)
- Okuma geçmişi listesi ekranı · Ayarlar'da "sistem" bloğu (son kontrol, bekleyen iş, cache boyutu)
- Kapak görseli çekme (og:image) · Tek "İçe Aktar" sihirbazı (otomatik tür algılama)
- EPUB/PDF **arayüz geliştirmeleri** (kullanıcı: "belki sonra") · LAN erişim koruması (token)
- Yerleşik TTS · Manga tam entegrasyonu · library/glossary'yi `db.connect()`'e taşıma

## Referans dokümanlar
- Onaylı plan + tasarım kararları: `~/.gstack/projects/novel-cevirmen/OMEREK-faz-sonraki-plan-design-20260718-000427.md`
- Mimari + kritik kararlar/tuzaklar: `CLAUDE.md`
- Tasarım gerekçesi: `TASARIM.md` · Eski TODO listesi: `TODOS.md` (bu dosya onun yerini alır)
