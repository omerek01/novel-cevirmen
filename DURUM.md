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
| 8 | **Manga çevirisi** | 🔨 **KODLANDI** (dal `dilim-8-manga`) | Gemini-vision ile balon OCR+çeviri+görsele yazma. Telefon QA bekliyor. |

**Ayrıca:** Çeviri modeli yalnız `gemini-3.1-flash-lite` (2.5 yedekleri kaldırıldı, kullanıcı kararı).

## Son eklenen: Manga çevirisi (dal `dilim-8-manga`, telefon QA bekliyor)
Yaklaşım (kullanıcı seçimi): comic-translate gibi ağır ML araçları yerine **mevcut Gemini'nin
görü (multimodal) yeteneği**. Akış: manga sayfasını Gemini'ye gönder → balon metinleri + konumları
+ Türkçe çevirileri al → PIL ile orijinali kapat, Türkçe'yi kutuya sığdırarak yaz → PNG.
- İçe aktarım: **CBZ/ZIP** (sayfa görselleri) ya da tek görsel → `manga://slug/N`, her sayfa=1 bölüm.
- Çeviri okudukça (on-demand); Dilim 7'nin görsel-içerik altyapısını aynen kullanır.
- Prototip + gerçek Gemini e2e ile görsel doğrulandı (3 balon doğru bulundu/çevrildi, glifler tam).
- **Bilinen sınır:** balon beyaz kutuyla kapatılıyor (çoğu balon beyaz → doğal); renkli balon/SFX/
  sanat üstü yazıda kutu göze batabilir. İyileştirme (bg-renk örnekleme, yuvarlak balon) sonraya.

## Bilinçle ertelenenler (ihtiyaç olunca)
- Okuma geçmişi listesi ekranı · Ayarlar'da "sistem" bloğu (son kontrol, bekleyen iş, cache boyutu)
- Kapak görseli çekme (og:image) · Tek "İçe Aktar" sihirbazı (otomatik tür algılama)
- EPUB/PDF **arayüz geliştirmeleri** (kullanıcı: "belki sonra") · LAN erişim koruması (token)
- Yerleşik TTS · Manga tam entegrasyonu · library/glossary'yi `db.connect()`'e taşıma

## Referans dokümanlar
- Onaylı plan + tasarım kararları: `~/.gstack/projects/novel-cevirmen/OMEREK-faz-sonraki-plan-design-20260718-000427.md`
- Mimari + kritik kararlar/tuzaklar: `CLAUDE.md`
- Tasarım gerekçesi: `TASARIM.md` · Eski TODO listesi: `TODOS.md` (bu dosya onun yerini alır)
