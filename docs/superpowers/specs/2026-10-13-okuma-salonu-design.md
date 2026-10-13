# Okuma Salonu — arayüz yeniden tasarımı

Tarih: 2026-10-13 · Durum: kullanıcı onaylı tasarım ("değişiklik yok devam edelim")

## Amaç

PWA'nın bütün ekranlarını tek bir özgün tasarım diline taşımak: eski bir halk kütüphanesinin
okuma salonu (kâğıt, meşe raf, pirinç etiketlik, ödünç kartı; gece: lamba ışığında ceviz).
Kullanıcı istekleri: kitaplık rafı düzeni ve büyük "Kütüphane" başlığı kalır; "yapay zekâ
görünümü" (genel geçer kartlar, mor geçiş, cam, Inter) olmaz; animasyonlar sade ve işlevsel;
okuyucudaki alt çubuk açılıp kapanır ve küçüktür.

Onaylı görseller ve taslak kaynakları (depoya girmez):
`novel-cevirmen/.stitch/designs/2026-10-13-okuma-salonu/` (`*.png`, `kaynak/*.html|css`).

## Kapsam

Kütüphane, kitap (bölüm listesi), okuyucu (+ künye, alt çubuk), sözlük (+ incelenecekler),
terim paneli, ayarlar paneli, alt gezinme. Pencereler (kitap ekle, toplu çevir, ePub,
birleştir, bölüm ekle) ve API durumu ekranı yeni belirteçlerle kendiliğinden uyar; yerleşimleri
değişmez. Davranış değişmez; yalnız görünüm, birkaç yeni işaretleme ve okuyucu alt çubuğu.

## Tasarım dili

**Yazı tipleri** (hepsi `app/web/fonts/` altına woff2 olarak yerelleştirilir; latin + latin-ext,
Türkçe karakterler doğrulanır; çevrimdışı açılış Google Fonts'a gitmez):
- Libre Caslon Display 400: büyük başlıklar (Kütüphane, Sözlük, kitap adı, bölüm başlığı, ilk harf).
- Libre Caslon Text 400/400i/700: kitap ve bölüm adları, terimin İngilizcesi (italik).
- Alegreya Sans 400/500/700: arayüz metni. Alegreya Sans SC 500/700: gerçek küçük büyük harf
  etiketler (raf etiketi, "BÖLÜM 381", bölüm ayırıcıları).
- Literata (mevcut): okuma metni. Inter kullanımdan kalkar (dosyaları silinir).

**Temalar** (mevcut `data-theme` değerleri korunur: `light`, `sepia`, `dark`):
- `sepia` = taslaktaki "Gündüz" kâğıdı (#f2ede2), `light` = daha beyaz kâğıt (#fbfaf6),
  `dark` = "Gece" (#14110e, lamba ışığı geçişi). Ortak vurgu: kütüphane yeşili (#2f5141 /
  gece #8cbaa0), pirinç (#94702f / #d3aa62), mühür kırmızısı (#a23a2a / #d97a5f), meşe/ceviz raf.
- Belirteçler `style.css` başındaki mevcut değişken adlarına eşlenir (`--bg`, `--surface`,
  `--ink`, `--accent`…); yeni adlar yalnız gerekince eklenir (`--brass`, `--stamp`,
  `--shelf-top/-front/-bottom`). Metin kontrastı her temada AA (4.5:1) ölçülüp yanına yazılır.
- Kâğıt dokusu: tek SVG gürültüsü, %5-8 örtücülük, `pointer-events: none`.

**Bileşenler** (taslaktaki adlarla): dev başlık + pirinç alt satır; ödünç kartı (devam fişi:
çizgili kart, kapak, tarih damgası, cetvel ilerlemesi, yeşil "Devam et"); katalog sekmeleri
(durum süzgeci, sayılı); pirinç raf etiketliği; raf tahtası (kaydırmayla giden tek bant);
kapaksız kitap = bez cilt + yaldız baş harf; toplu çeviri ayracı ("3/10"); içindekiler listesi
(kaldığın bölümde kırmızı şerit); inceleme kartı (büyük sayı); alt çizgili form alanları;
süzgeç çipleri; küçük büyük harf etiketler; alttan açılan panel; parçalı seçim; tema örnekleri.

## Okuyucu alt çubuğu

İki hâl: **kapalı** (okurken varsayılan) = ilerleme halkası + kalan süre + yukarı ok olan küçük
hap; **açık** = 56 px tek sıra (Önceki · Bölümler · Sözlük · Sonraki + kapat). Hap dokununca
açılır, ⌄ ile kapanır, aşağı kaydırınca kendiliğinden kapanır. Seçim → "Sözlüğe ekle"
davranışı değişmez. Hâl `localStorage`'da tutulmaz (her bölüm kapalı başlar).

## Hareket (prompt-motion ilkelerinden: nesne şekil değiştirir, soluklaşma/bulanıklık yok)

- Kütüphane ilk açılış: kitaplar rafa sırayla oturur (opacity + 12px yükselme, 220 ms, 30 ms aralık).
- Ödünç kartı cebinden yükselir (260 ms). Sekme göstergesi kayar (200 ms).
- Okuyucu alt çubuğu: hap ↔ çubuk genişlik/yükseklik dönüşümü (260 ms, `cubic-bezier(.2,0,0,1)`).
- Bölüm başlığı bir çizginin arkasından yükselir (320 ms); ilerleme çizgisi çizilir.
- Kapaktan kitap ekranına geçiş: View Transitions API varsa kapak paylaşılan öğe olarak
  dönüşür, yoksa animasyonsuz geçilir.
- Hepsi `transform`/`opacity` üzerinden; `prefers-reduced-motion: reduce` hepsini kapatır.

## Uygulama ilkeleri

- `index.html` kimlikleri ve JS'in/testlerin kullandığı sınıflar korunur; yeni işaretleme
  eklenir, var olanın adı değişmez. Davranış kodu (`js/*.js`) yalnız yeni öğeleri doldurmak
  için değişir (ödünç kartı, raf etiketi sayısı, alt hap).
- Ekran ekran ilerlenir; her ekran ayrı commit, her commit'te `sw.js` `SHELL_CACHE` artar ve
  yeni font dosyaları SHELL listesine girer.
- Doğrulama: çevrimdışı testler, tarayıcı testleri (`NOVEL_TARAYICI_TEST=1`), JS testleri;
  her ekranın telefon boyutunda (390×844) üç temada ekran görüntüsü kullanıcıya gösterilir.
- Push ve canlıya alma kullanıcı onayıyla.

## Kapsam dışı

Çeviri, sözlük mantığı, sunucu uçları; pencerelerin yeniden düzenlenmesi; masaüstü yerleşimi
(mevcut geniş ekran kuralları korunur, ayrıca tasarlanmaz).
