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
| 8 | **Manga çevirisi** | 🔜 **SIRADAKİ** | Planda "tracer bullet" (Scope 10) — fazın en büyük/riskli parçası, bilinçle ertelenmişti. Balon algılama + OCR + çeviri + görsele geri yazma. Yaklaşım kullanıcıyla seçilecek. |

**Ayrıca:** Çeviri modeli yalnız `gemini-3.1-flash-lite` (2.5 yedekleri kaldırıldı, kullanıcı kararı).

## Sıradaki iş: Manga çevirisi (planda Scope 10 — "tracer bullet")
Manga sayfaları resimdir; metin **balonların içine gömülüdür** (PDF gibi çıkarılabilir metin yok).
Bu yüzden akış: **balon algıla → OCR (resimden metin oku) → Türkçe'ye çevir → orijinali kapatıp
Türkçe'yi görselin üstüne yaz**. Plan bunu fazın "en büyük ve en riskli parçası" sayıp ayrı bir
tracer bullet'a (tek bölüm ≈20 sayfa uçtan uca) bırakmıştı; tam akış (CBZ/klasör, seri takibi)
Faz N+1'e ertelenmişti.

**İyi haber:** Dilim 7'de kurduğum altyapı (media sunumu, `content_type`, sayfa-görseli okuyucusu,
yerinde metin değiştirme) manga'nın gösterme/servis tarafını zaten karşılıyor. Eksik olan tek şey:
resimden metni ÇIKARMAK (OCR + balon). İki yol var — kullanıcıyla seçiliyor (bkz. sohbet).

## Bilinçle ertelenenler (ihtiyaç olunca)
- Okuma geçmişi listesi ekranı · Ayarlar'da "sistem" bloğu (son kontrol, bekleyen iş, cache boyutu)
- Kapak görseli çekme (og:image) · Tek "İçe Aktar" sihirbazı (otomatik tür algılama)
- EPUB/PDF **arayüz geliştirmeleri** (kullanıcı: "belki sonra") · LAN erişim koruması (token)
- Yerleşik TTS · Manga tam entegrasyonu · library/glossary'yi `db.connect()`'e taşıma

## Referans dokümanlar
- Onaylı plan + tasarım kararları: `~/.gstack/projects/novel-cevirmen/OMEREK-faz-sonraki-plan-design-20260718-000427.md`
- Mimari + kritik kararlar/tuzaklar: `CLAUDE.md`
- Tasarım gerekçesi: `TASARIM.md` · Eski TODO listesi: `TODOS.md` (bu dosya onun yerini alır)
