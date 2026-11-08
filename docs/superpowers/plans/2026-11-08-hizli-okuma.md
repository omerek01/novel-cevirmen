<!-- /autoplan restore point: "C:\\Users\\OMEREK\\Desktop\\PROJELER\\gstack\\novel-cevirmen\\.worktrees\\roman-baglam\\.gstack\\tmp\\autoplan\\roman-baglam-autoplan-restore-20261108-201918.md" -->
# Hızlı okuma ve okuma hızını geliştirme — plan

**Durum: ONAYLANDI (2026-11-08, kullanıcı: "Onayla, Adım A'dan başla"). Gemini anlama soruları ertelendi (TODOS.md).**

Tarih: 2026-11-08. Dal: `roman-baglam`. Kullanıcı isteği: "Bölümleri okurken hızlı okuma
yapabilmek ve okuma hızımı geliştirmek istiyorum. Bununla ilgili araştırma yap."

## Implementation plan

### Araştırma özeti (karar dayanağı)

| Yöntem | Kanıt | Karar |
|---|---|---|
| Göz hareketini kaldıran sözcük sözcük gösterim (RSVP, Spritz tarzı) | Rayner ve ark. 2016 (Psychological Science in the Public Interest 17/1): geri dönüş (regresyon) engellenince anlama düşer; hız-anlama takası aşılamaz. | Yapılmaz |
| Sözcük başlarını kalın yazma (Bionic Reading) | Snell 2024, "No, Bionic Reading does not work" (Acta Psychologica): hıza da anlamaya da etkisi yok. | Yapılmaz |
| İç sesi bastırma alıştırmaları | Rayner 2016: iç ses anlamaya katkı verir, bastırmak anlamayı düşürür. | Yapılmaz |
| Okuma hızlandırma (metnin, okurun kendi hızından biraz hızlı ilerleyen bir dayatmayla okunması) | Breznitz çalışmaları; Zamfira ve ark. 2024 (Frontiers in Psychology, PMC11322054): yetişkinler hızlandırma sırasında ~%40 hızlı okudu, doğruluk %88-91 kaldı; sonrasındaki serbest okumada da hız arttı ve artış yalnız pratik yapan denetim grubundan büyüktü. Hız, kişinin kendi serbest hızından başlatılıp anlama doğruluğuna göre küçük adımlarla ayarlandı. | **Yapılır (Tempo modu)** |
| Çok okumak, akıcılık, kendi hızını izlemek | Rayner 2016: kalıcı hız artışının asıl yolu pratik ve sözcük bilgisi. Brysbaert 2019 (Journal of Memory and Language): İngilizce sessiz okuma ortalaması kurguda ~260 sözcük/dk; diller arası karşılaştırmada harf/dk sözcük/dk'dan daha adil. | **Yapılır (ölçüm + ilerleme)** |

REA kullanılmadı: kullanılacak teknikler yayımlanmış çalışmalarda yöntemiyle anlatılıyor;
kapalı bir uygulamanın paketinden öğrenilecek bir algoritma yok.

### Mevcut durum (kodda)

- `app/web/js/oto-kaydir.js` + `oto-kaydir-yardimci.js`: 12 seviyeli otomatik kaydırma,
  hız piksel/saniye (`HIZLAR`), ayarda `kaydirmaSeviyesi`. Seviye ile sözcük/dk arasındaki
  bağ yorumdaki kaba tahmin; yazı boyutu değişince gerçek hız da değişir.
- `app/web/js/alt-cubuk.js` `kalanDakika`: herkes için sabit 230 sözcük/dk.
- `app/core/reading_log.py`: günde bölüm başına bir satır (`day, slug, url, ts`); süre ve
  hız tutulmuyor. `POST /api/reading-log` (server.py:707), `GET /api/stats?day=`
  (server.py:717) → `{today, total}`; kitap silmede `library.py:411` satırları siler.
- Ayarlar `localStorage` `novellink:settings` (ayarlar.js:12): `fontPx` 19, `lineHeight`
  sik/normal/seyrek, `kaydirmaSeviyesi`.
- Okuyucu tek kaydırma girişi `onReaderScroll` (okuyucu.js): ikinci `scroll` dinleyicisi
  açılmaz kuralı var.

### Yapılacaklar

Teslim İKİ ADIMDA (CEO incelemesi, 2026-11-08):
- **Adım A** (§1 ölçüm, §2 kalan süre, §3'ün yalnız birim/kumanda kısmı, §5'in ilgili
  testleri): hemen faydalı, düşük risk. Tempo henüz hızlanmaz; okur 1-2 hafta
  serbest okur, `ilk_hafta` tempo karışmamış gerçek başlangıç çizgisi olur.
- **Adım B** (§3 yoklama + okuma çizgisi + uyarlama, §4 kart, ölçüm bölümü önerisi):
  Adım A canlıdayken en az 5 geçerli serbest oturum biriktikten sonra.
- **Adım C** (§7 öbek modu, kullanıcı kararı 2026-11-08 "Deneme modu, Gemini
  öbekleri"): Adım B'den bağımsız; Adım A'nın ölçümü üstüne kurulur.

Birim kuralı: içeride her hız **harf/dk** tutulur (harf = boşluk dışı karakter;
noktalama dahil). Ekranda sözcük/dk gösterilir: sözcük/dk = harf/dk ÷ o bölümün
ortalama sözcük uzunluğu (bölümün harf ÷ sözcük sayısı); birden çok oturumun özetinde
Σharf ÷ Σsözcük. Bütün sınırlar harf/dk'dır. Sözcük karşılığı verilen yerlerde sabit
`HARF_SOZCUK = 6,5` kullanılır (tek sabit, `okuma-hizi-yardimci.js`).

### 1. Okuma hızını sessizce ölçme

- Yeni saf modül `app/web/js/okuma-hizi-yardimci.js` (DOM'suz, `node --test`):
  - Ölçüm birimi BÖLÜMDÜR (kaydırma örneği değil). Her bölüm için bir oturum, url
    anahtarlı: bölüm aktif olunca (`setActiveChapter`) süre işler; okur önceki bölüme
    geri kaydırınca bu oturum DURAKLAR, o bölüm yeniden aktif olunca SÜRER (aynı url).
    Bölüm, altı ekranın altına ulaşınca (`el.getBoundingClientRect().bottom <=
    innerHeight`; `currentRatio` reader-bar çizgisini ölçtüğü için kitabın son
    bölümünde 0,95'e hiç ulaşmayabilir, okuyucu.js:57) ya da sonraki bölüm aktif
    olunca biter. Bitmeden bırakılan oturum (okuyucudan çıkış: `readerView` `hidden`
    MutationObserver, oto-kaydir.js:171 kalıbı; başka kitaba geçiş; `pagehide`,
    okuyucu.js:1820) `gecerli=false` olarak `keepalive` ile gönderilir: hıza girmez,
    pratik dakikasına girer. Sekme gizlenince (`visibilitychange: hidden`,
    okuyucu.js:1821; Android PWA'da `pagehide` çoğu zaman gelmez) o anki durum aynı
    `oturum_id` ile gönderilir, oturum kapanmaz. Oturumun günü bitiş günüdür. Biten url aynı
    okuyucu ziyaretinde yeniden oturum açmaz (geri dönüp bakmak yeni ölçüm değildir).
    Atlama: tek kaydırma olayında oran 0,2'den fazla ilerlerse ya da
    `scrollToChapterRatio` / bölüm içi arama gezintisi `okumaHiziAtlama()` çağırırsa
    oturum geçersiz olur (süresi pratik dakikasına yine girer).
  - `sureEkle(oturum, simdi, etkin)`: etkin süreyi biriktirir. Sekme gizli ya da bir
    `<dialog>` açıkken geçen süre sayılmaz. Tempo AKARKEN (`durum === "akiyor"`) geçen
    süre etkin sayılır, ama masaya bırakılan telefon için bir sınır var: dokunma akışı
    yalnız parmak ekrandayken bekletir (oto-kaydir.js:162) ve sonsuz akışta sayfa
    sonu beklemesi bölüm yüklendikçe sürer, yani akış tek başına okurun ekranda
    olduğunu kanıtlamaz. Kural bölüm başınadır (geriye dönük değil; gönderilmiş satır
    düzeltilmez): bir tempo bölümü boyunca hiç etkinlik (dokunma ya da yoklama yanıtı)
    olmadıysa o bölüm `active_ms = 0`, `gecerli=false` gönderilir. Adım A'da akış
    DURDURULMAZ (bugünkü kaydırma davranışı korunur). Adım B'de art arda ÜÇ etkinliksiz
    bölüm sonunda, yoklamanın 20 sn zaman aşımı geçtikten sonra, akış duraklatılır ve
    ekran kilidi bırakılır (yoklama ile duraklatma aynı ana denk gelmez). Serbest okumada ve tempo duraklatılmışken etkinlik = kaydırma ya
    da dokunma; iki etkinlik arası 90 sn'den uzunsa fazlası sayılmaz.
  - `oturumSonucu(oturum)`: `{gecerli, harf, sozcuk, aktif_ms, hiz_hdk}` döner.
    Geçersiz sayılır: bölüm 1500 harften kısa, etkin süre 60 sn'den az, açılış oranı
    > 0,10 (ortadan başladı), hız 400-5000 harf/dk dışında (6,5 ile ≈ 60-770
    sözcük/dk; üstü göz gezdirme ya da bölüm atlama). HTML içerikli (PDF/EPUB)
    bölümlerde harf 0'dır: ölçüm geçersiz, tempo yedek hıza düşer.
    Geçersiz oturumun da süresi döner (pratik dakikası için).
  - Kip: oturum boyunca otomatik kaydırma bir an bile açıldıysa `tempo`, hiç
    açılmadıysa `serbest` (karışık bölüm `tempo` sayılır, kişisel hıza girmez).
- `app/web/js/okuma-hizi.js`: `setActiveChapter` ve `onReaderScroll` içinden
  çağrılır (yeni `scroll` dinleyicisi yok). Dokunma, `oto-kaydir.js:162`'deki mevcut
  `pointerdown` dinleyicisinden `okumaHiziEtkinlik()` çağrısıyla alınır (ikinci
  dinleyici açılmaz). Kişisel hız istemcide hesaplanmaz; sunucunun `kisisel_hiz`
  değeri (önbellekten) kullanılır. Oturum
  bitince sonucu, geçerli olsun olmasın, `POST /api/reading-speed` ile gönderir
  (`gecerli` bayrağıyla; best-effort, okuma bozulmaz).
- Sunucu: `app/core/reading_log.py` içine `reading_speed` tablosu (`oturum_id, day,
  book_slug, url, mode, chars, words, active_ms, valid, ts`; `oturum_id` istemcinin
  oturum başına ürettiği rastgele kimlik, `UNIQUE(oturum_id)`, aynı oturumun tekrar
  gönderimi o satırı günceller; aynı gün aynı bölümün ikinci okuması ayrı satırdır;
  `idx_reading_speed_day` dizini; `book_slug` POST'ta `library.resolve_slug` ile
  çözülür). Sunucu `valid`'i istemciye güvenmeden yeniden hesaplar (hız bandı,
  harf ≥ 1500, etkin süre ≥ 60 sn) ve istemcinin `gecerli=false` dediğini geçerli
  yapmaz ve `log_speed`,
  `speed_stats(day)`. `speed_stats` döner:
  - `kisisel_hiz`: son 10 geçerli serbest oturumun ortancası alınır, onun 2 katından
    hızlı olanlar atılır, kalanların ortancası (`hdk`, `sdk`); n < 3 ise süzgeç yok.
  - `ilk_hafta`: `{hdk, sdk, n, bas_gun}`: İLK 5 geçerli serbest oturumun ortancası
    (takvim penceresi değil, ara verilince kilitlenmesin); `n` < 5 ise `null`.
  - `degisim`: `kisisel_hiz.hdk ÷ ilk_hafta.hdk − 1`; `ilk_hafta` `null` ise ya da
    toplam geçerli serbest oturum 10'dan azsa (başlangıç çizgisiyle aynı küme
    olmasın) `null`.
  - `gunluk`: son 30 gün, gün başına `{gun, hdk, sdk}` ortanca (yalnız geçerli serbest)
    ve `tempo_hdk` (o günün geçerli tempo oturumlarının ortancası; yoksa `null`).
  - `bugun_dk`: bugünkü bütün oturumların (geçersizler dahil) etkin dakikası.
  - `oturum_sayisi`: geçerli serbest oturum sayısı.
  Kitap silme: elle satır gerekmez; library.py:421'deki şema döngüsü `book_slug`
  sütunu olan her tabloyu siler (testle doğrulanır).
- `server.py`: `POST /api/reading-speed` (pydantic: `oturum_id` 8-64 karakter
  `[A-Za-z0-9-]`, gün `YYYY-MM-DD`, `mode` serbest|tempo, `chars` 0-2.000.000,
  `words` 0..`chars` (sözcük/dk yalnız `words ≥ 1` ise hesaplanır), `active_ms`
  0-86.400.000, `slug`/`url` boş değil ve en çok 2000 karakter), `GET /api/reading-speed/stats?day=`. `sw.js`: GET ucu önbellek dışı
  (POST zaten SW'den geçmez, sw.js:220); `SHELL_CACHE` artırılır.
- İstemci önbelleği: stats yanıtı `localStorage` `novellink:okuma-hizi`
  anahtarında tutulur (okuyucu açılışında ve her gönderimden sonra tazelenir;
  çevrimdışıyken son değer kullanılır).

### 2. Kişisel kalan süre

- `kalanDakika(oran, harf, hizHdk)`: tempo akarken `hizHdk = kaydirmaHizi`, değilse
  kişisel hız; ikisi de yoksa `hizHdk = 230 × 6,5 = 1495` (bugünkü 230 sözcük/dk'nın
  harf karşılığı). Sonuç `kalan harf ÷ hizHdk`, en az 1 dk. Çağıran `altCubukGuncelle` (okuyucu.js:168)
  bölümün harf sayısını da hesaplar (bölüm başına bir kez, `e.harf` olarak saklanır).

### 3. Tempo modu (okuma hızlandırma)

- Tempo, mevcut otomatik kaydırmanın kendisidir (alt çubukta "Kaydır" düğmesi aynı
  kalır); yalnız hız birimi değişir. Yeni ayar `kaydirmaHizi` (harf/dk), sınır
  700-4500 harf/dk (~6,5 harfli sözcükle ≈ 110-690 sözcük/dk; Türkçe eklemeli
  olduğundan sözcük/dk İngilizceden düşük çıkar, alt sınır bilerek düşük; ekranda o
  bölümün sözcük uzunluğuyla gösterilir). Her değişiklik (− / + %5, yoklama ±%4) sınırlanıp `saveSettings` ile
  kaydedilir.
- Başlangıç değeri: `kaydirmaHizi` varsa o. Yoksa ve eski `kaydirmaSeviyesi` varsa
  ilk tempo başlangıcında tarayıcıda GERÇEK ölçüyle bir kez çevrilir:
  `kaydirmaHizi = eskiPxSn × 60 × (aktif bölümün harfi ÷ çizilmiş yüksekliği px)`,
  sonra sınırlanır; böylece o andaki kaydırma hızı birebir korunur (yorumdaki
  "satırda 10 sözcük" varsayımı telefonda yaklaşık %50-75 yanlış; eski px/sn tablosu
  `ESKI_HIZLAR` adıyla yalnız bu çevrim için kalır). İkisi de yoksa kişisel hız × 1,10; o da yoksa 1600 harf/dk.
- px/sn çevrimi: `pxSn = hizHdk ÷ 60 × (bölümün çizilmiş yüksekliği px ÷ bölümün
  harfi)`; yükseklik `ResizeObserver` ile YALNIZ aktif bölümde izlenir (sonsuz akışta
  onlarca bölüm olabilir), yazı boyutu / satır aralığı / kenar değişince kendiliğinden
  yeniden hesaplanır. Yükseklik ya da harf 0 ise (henüz çizilmemiş bölüm) hesap NaN /
  Infinity üretmez, son geçerli px/sn'yi korur; o da yoksa 1495 harf/dk yedeği. Saf hesap `oto-kaydir-yardimci.js`'e
  (`HIZLAR` dizisi ve seviye işlevleri kalkar; `seviyeSinirla` kullanan her yer —
  oto-kaydir.js ve mevcut testler — güncellenir).
- Kumanda: "Hız 4" yerine "260 kel/dk"; çentik göstergesi sınırlar arasındaki konumu
  gösterir.
- Okuma çizgisi: ekranın üstten ~%35'inde ince bir yatay çizgi; çizginin üstünde kalan
  satırlar hafifçe soluklaşır (çalışmadaki "kayan örtü"nün okumayı bozmayan hali).
  Örtü `pointer-events: none` (terim dokunuşu ve metin seçimi bozulmasın).
  Yalnız tempo akarken görünür; ayar `okumaCizgisi` (varsayılan `true`, okuma
  ayarları sayfasında Açık/Kapalı); `prefers-reduced-motion`
  açıksa soluklaştırma geçişsizdir.
- Bölüm sonu yoklaması: bölüm bittiği anda tempo AKIYOR ya da DURAKLATILMIŞSA
  (kumanda görünürken; kapatılmışsa sorulmaz)
  tempo kumandasının hemen üstünde, ekrana sabit küçük bir şerit (diyalog DEĞİL,
  akışı durdurmaz; metnin içine eklenmez): "Takip edebildin mi? Rahattı · İdare eder ·
  Zorlandım". İki tempo bölümünde bir sorulur (dırdıra dönmesin). Zorlandım hemen
  −%4; Rahattı yalnız art arda İKİNCİ "Rahattı"da +%4 (öz bildirim anladığını fazla
  sanmaya yatkın; tek yöne itmesin); İdare eder aynı ve "Rahattı" sayacını sıfırlar.
- Ölçüm bölümü önerisi: art arda 5 tempo bölümünden sonra şerit bir kez "Sıradaki
  bölümü kendi hızında oku (ölçüm için)" der ve tempoyu ÖNCEKİ bölümün bitişinde
  (sıradaki bölüm aktif olmadan) kapatır ki ölçüm bölümü `serbest` sayılsın; okur
  "Tempoda kal" diyebilir. Çalışmanın asıl iddiası (tempodan sonra serbest hızın
  artması) bu bölümlerle ölçülür.
  Yanıt verilmezse 20 sn sonra ya da sonraki bölümün yarısında kendiliğinden kapanır,
  hız değişmez. Şerit `aria-live="polite"`, düğmeler en az 44 px.

### 4. İlerleme kartı

- Ayarlar sayfasında "Okuma hızı" bölümü: kişisel hız (sözcük/dk, küçük harfle
  harf/dk), ilk haftaya göre değişim yüzdesi (sunucunun `degisim` değeri; `null`
  ise satır gösterilmez), son 30 günün küçük çizgi grafiği (satır içi SVG, kütüphane eklenmez),
  ölçülen oturum sayısı. Bugünkü okuma dakikası kartın EN ÜSTÜNDE ve en büyük sayıdır
  (kalıcı hızın asıl kaynağı pratik; hız sayısı ikincil, hedef haline gelmesin). Tempo
  hızının seyri ikinci çizgi olarak (`gunluk` içinde `tempo_hdk`, tempo oturumlarının
  ortancası). Veri yoksa "Birkaç bölüm okuyunca
  hızın burada görünecek." Yüklenemezse son önbellek değeri ve "güncel değil" notu.
- Kısa bilgi notu: neden hızlı okuma hileleri değil tempo modu (yukarıdaki tablo,
  iki cümle) ve açıkça: "Tempo, çalışmadaki silinen metnin yumuşatılmış hali; etkisi
  sende ölçülüyor. Anlama nesnel olarak ölçülmüyor, yalnız senin yanıtınla."

### 5. Testler

- `tests/js/okuma-hizi.test.mjs`: 90 sn boşta kesme; sekme gizli / diyalog süresi düşülür; geri kaydırmada
  duraklama ve aynı url'de sürme; biten url yeniden açılmaz; tempo akarken süre
  etkin, duraklatılmışken 90 sn kuralı; karışık bölüm `tempo`; alt sınırlar ve hız dışı
  `gecerli=false` ama süre korunur; ortanca; `kalanDakika` iki yolu; px/sn çevrimi;
  seviye→harf/dk çevrim formülü (verilen harf ve yükseklikle) ve sınırlama; masadaki
  telefon kuralı (etkinliksiz bölüm → süre 0; Adım A'da akış durmaz; Adım B'de üçüncü
  etkinliksiz bölüm sonunda, yoklama zaman aşımından sonra duraklar); son bölüm
  bitişi (`bottom <= innerHeight`); ileri atlama (oran +0,2 ve `okumaHiziAtlama`);
  HTML bölüm (harf 0) geçersiz ve yedek hız; ölçüm bölümünde tempo önceki bölüm
  sonunda kapanır; "Rahattı" sayacı (tek Rahattı artırmaz, ikincisi +%4, İdare eder
  sıfırlar); 5 tempo bölümünden sonra ölçüm bölümü önerisi; %5 ve %4 adımlarında sınır.
- `tests/test_reading_speed.py`: tablo oluşumu; doğrulama 422 (`words` > `chars`,
  uzun url, bozuk `oturum_id`); aynı `oturum_id` tekrarında güncelleme, farklı
  oturum ayrı satır; sunucu `valid`'i yeniden hesaplar; `kisisel_hiz` süzgeci (n < 3
  süzgeçsiz, 2× üstü atılır); `ilk_hafta` ilk 5 oturum ve `degisim` 10 oturumdan
  azsa `null`; `bugun_dk` geçersizleri de sayar; alias slug ile yazılıp kitap
  silinince satırlar gider.
- Güncellenecek mevcut testler: `tests/js/alt-cubuk.test.mjs` (`kalanDakika` imzası),
  `tests/js/oto-kaydir-yardimci.test.mjs` ve `tests/tarayici/test_oto_kaydir.py`
  (`HIZLAR`/seviye kalkıyor).
- `tests/tarayici/test_tempo_modu.py` (saat `page.clock` ile ilerletilir): tempo başlat
  → kumandada kel/dk görünür, + ile %5 artar ve ayara yazılır; bölüm sonu şeridi
  çıkar, "Zorlandım" hızı %4 düşürür; yanıtsız şerit 20 sn sonra kapanır; ayarlarda
  ilerleme kartı veriyle ve verisiz; eski `kaydirmaSeviyesi=4` ile tempo başlatınca
  px/sn çevrimden önce ve sonra aynı; sekme gizlenince gönderim (`keepalive`).

### 7. Öbek modu (deneme; kelimeleri blok blok görme)

Dayanak: hızlı okurların algı aralığı daha geniştir ama bu, sözcük işlemenin kolay
olmasının SONUCUDUR; göz egzersiziyle genişletildiğine dair kanıt yok (Rayner,
Slattery ve Bélanger 2010; Rayner 2016). Metni anlam öbeklerine bölüp göstermek
(phrase-cued text; visual-syntactic text formatting, Walker 2005, yöntemin
geliştiricilerinden) üniversite öğrencilerinde anlama ve verimi artırdı; akıcı
yetişkinde etkisi belirsiz. Bu yüzden DENEME modudur ve etkisi kişisel ölçümle sınanır.

- Öbek sınırlarını Gemini işaretler. Yeni modül `app/core/obekler.py`
  (`ozet_zinciri.py` kalıbı: üretim işlevi `uret` dışarıdan verilir,
  `translate.py:1460`'taki `_izli_uret` sarmalı ve `api_durum.baglam(asama="obek")`).
  İstem: Türkçe paragrafı HİÇBİR harfini değiştirmeden anlam öbeklerine `|` ile böl
  (öbek 2-5 sözcük; özne öbeği, eylem öbeği, yan cümle, -ken/-ınca/-ıp/-dığında
  ekli öbekler bir arada).
- Doğrulama (güven sınırı: model metni değiştirebilir): `|` çıkarılınca paragraf
  bayt bayt aynı değilse ya da bir öbek 8 sözcükten uzun / boşsa o paragraf için
  model çıktısı reddedilir ve KURAL TABANLI yedek kullanılır (noktalama, ve/ama/ki/
  çünkü/ile bağlaçları, -ken/-ınca/-ıp/-dığında ekleri; saf işlev
  `kural_obekleri(paragraf)`). Reddedilen paragraf sayısı satırda saklanır.
- Saklama: `obekler` tablosu (`url, book_slug, kaynak_sha256, sinirlar_json, model,
  reddedilen, ts`; `UNIQUE(url)`). `kaynak_sha256` çeviri metninin özeti: bölüm
  yeniden çevrilir ya da düzeltilirse öbekler bayatlar ve yeniden üretilir.
  `sinirlar_json` paragraf başına öbek bitiş konumları (karakter sırası) — metnin
  kopyası tutulmaz. `book_slug` sütunu sayesinde kitap silmede kendiliğinden silinir.
- Uç: `GET /api/chapter/obekler?url=` → `{sinirlar, kaynak: "model"|"kural"}`.
  Kayıt varsa ve özet tutuyorsa hemen döner; yoksa üretir (en çok 30 sn), hata ya da
  zaman aşımında `kaynak: "kural"` ile kural tabanlı sınırları döner (okuyucu asla
  öbeksiz kalmaz, hata sessiz değil: `api_durum` kaydına düşer). Yalnız öbek modu
  açıkken çağrılır; sıradaki bölüm için önden bir istek atılır. `content_type='html'`
  bölümlerde öbek yok. `sw.js`: ağ öncelikli, çevrimdışıyken önbellekteki son yanıt;
  `SHELL_CACHE` artırılır.
- Çizim tek noktadan: `renderParagraphs` (okuyucu.js:726) bölümün `entry.obekler`i
  varsa paragrafı öbek span'leriyle kurar; yoksa bugünkü gibi düz metin. Bölüm ÖNCE
  düz çizilir, öbekler gelince `renderParagraphs` yeniden çağrılır ve okuma konumu
  `currentRatio` ile korunur (öbek isteği bölüm açılışını asla bekletmez). Arama
  vurgusu (`appendHighlighted`, okuyucu.js:1671) öbek sınırlarını bilir: eşleşme bir
  öbek sınırını aşarsa `mark` iki span'e bölünür; `runFind` bugünkü gibi
  `querySelectorAll("mark")` ile sayar (bölünmüş eşleşme tek sayılsın diye
  `data-eslesme` kimliği).
- Gösterim: her öbek `<span class="obek">`; öbekler
  arasında hafif ek boşluk ve tek-çift öbekte çok hafif zemin farkı (koyu/sepya temada
  ayrı ton). Metin düğümleri bölünse de sözcük içinde bölme yapılmaz; terim dokunuşu,
  sözlük seçimi, bölüm içi arama vurgusu ve çift dokunmada İngilizce orijinal bugünkü
  gibi çalışmalı (bunlar span içinde sözcük arar; testle doğrulanır).
- Tempo ile birlikte (Adım B'nin okuma çizgisi varsa): çizginin üstüne gelen öbek
  vurgulanır, böylece göz sözcük sözcük değil öbek öbek ilerletilir (Outread tarzı
  kılavuz vurgu). Tempo yoksa yalnız görsel öbekler.
- Aç / kapa (kullanıcı isteği 2026-11-08: "bu bir mod gibi açılır ve kapatılır
  olmalı"): okuyucu alt çubuğunda "Kaydır"ın yanında "Öbek" düğmesi (index.html:331
  sırası); tek dokunuşla açılır / kapanır, açıkken basılı görünür (`aria-pressed`),
  durum `obekModu` ayarında saklanır (varsayılan `false`) ve okuma ayarlarında da
  aynı anahtar "Öbek modu (deneme)" olarak durur. Açınca aktif ve görünen bölümler
  öbekli yeniden çizilir (öbekler gelene dek düz), kapatınca düz metne döner; her
  iki geçişte okuma konumu korunur. Açıkken kısa bir bildirim: "Öbek modu açık".
  Oturum ortasında mod değişirse o bölümün oturumu `obek` bayrağıyla değil geçersiz
  (karışık) sayılır, kişisel hıza da öbek hızına da girmez.
- Ölçüm: oturuma `obek` bayrağı eklenir (`reading_speed.obek` sütunu, 0/1);
  `kisisel_hiz` yalnız `obek=0` serbest oturumlardan hesaplanır, `obek_hiz` ayrı döner.
  Kartta en az 5'er geçerli serbest oturum olunca "Öbek modunda X kel/dk, normalde
  Y kel/dk" satırı; daha azsa "karşılaştırma için N bölüm daha" notu.
- Maliyet: bölüm başına bir Gemini çağrısı (çıktı ≈ girdi uzunluğu), yalnız öbek modu
  açıkken okunan bölümlerde; varsayılan model, defterin ucuz modeliyle aynı ayar
  yolundan seçilir (ücretli çağrı onayı CLAUDE.md'de var). `kullanim` kaydına
  `asama="obek"` olarak düşer, ayarlardaki harcama göstergesinde görünür.
- Testler:
  - `tests/test_obekler.py`: model çıktısı harf değiştirirse reddedilir ve kural
    yedeği; 8 sözcükten uzun öbek reddi; `kaynak_sha256` değişince yeniden üretim;
    zaman aşımı / hata → `kaynak: "kural"`; kitap silinince satır gider; `kural_obekleri`
    tablo testleri (noktalama, bağlaç, -ken/-ınca/-ıp ekleri).
  - `tests/js/okuma-hizi.test.mjs`: `obek` bayraklı oturum kişisel hıza girmez.
  - `tests/tarayici/test_obek_modu.py`: alt çubuktaki "Öbek" düğmesi aç / kapa
    (aria-pressed, ayara yazılır, yeniden açılışta korunur, konum kaymaz); oturum
    ortasında mod değişince oturum karışık sayılır; öbek modu açıkken span'ler çizilir; terim
    dokunuşu, arama vurgusu (öbek sınırını aşan eşleşme tek sayılır) ve çift dokunma
    orijinali bozulmaz; öbekler geç gelince okuma konumu kaymaz; uç hata verince
    kural öbekleriyle çizim.

### NOT in scope

- RSVP, Bionic Reading, iç ses bastırma (kanıt yok ya da zararlı).
- Gemini ile üretilen anlama soruları (ücretli çağrı ve gecikme; kendi kendine bildirim
  ilk sürüm için yeterli; TODOS.md'ye ertelendi).
- Harf harf silinen metin (sonsuz akışta ve sözlük/terim paneliyle çakışır).
- `son_hafta` istatistiği (gösterildiği yer yok).
- Sesli eşlikle okuma (TTS ile birlikte okuma): ayrı değerlendirme.
- Okuma hacmini kısıtlayan çeviri bekleme süresinin ölçümü: TODOS.md'ye ertelendi.

### 6. Erteleme kaydı

- `TODOS.md`'ye bir satır: "Tempo yoklamasının nesnel karşılığı: Gemini ile bölüm sonu
  anlama soruları (ücretli; 2026-11-08 hızlı okuma planından ertelendi)."
- `TODOS.md`'ye ikinci satır: "Okuma hacmi kaldıracı: bölüm başına çeviri bekleme
  süresini ölç; hız mı hacim mi daha büyük kaldıraç, veriyle gör."



<!-- autoplan-accepted:ceo -->
- İki adımlı teslim: Adım A (ölçüm, kişisel kalan süre, kel/dk kumandası), Adım B (yoklama, okuma çizgisi, uyarlama, kart, ölçüm bölümü) en az 5 geçerli serbest oturumdan sonra.
- Bölüm bazlı ölçüm: url anahtarlı oturum, açılış oranı ≤ 0,10, bitiş ≥ 0,95 ya da sonraki bölüm aktif, biten url aynı ziyarette yeniden açılmaz; testleri okuma-hizi.test.mjs.
- Tempo masada telefon kuralı: son dokunma/yanıttan beri iki bölüm sonu geçerse akış duraklar, kilit bırakılır, o bölümlerin süresi 0; testli.
- Geçerlilik sınırları 400-5000 harf/dk; sunucu 2× kişisel ortancadan hızlı serbest oturumu kisisel_hiz dışında tutar; test_reading_speed.py.
- kaydirmaHizi sınırı 700-4500 harf/dk; seviye çevrimi sınır içinde eski hızdan %10'dan fazla sapmaz; testli.
- Yoklama iki tempo bölümünde bir; Zorlandım −%4 hemen, Rahattı +%4 yalnız art arda ikincide, İdare eder sayacı sıfırlar; testli.
- Ölçüm bölümü önerisi: art arda 5 tempo bölümünden sonra bir kez; testli.
- Kartta pratik dakikası en üstte, tempo_hdk ikinci çizgi; bilgi notunda yumuşatılmış yöntem ve öz bildirim uyarısı.
- px/sn çevriminde yükseklik ya da harf 0 ise yedek hıza düşülür (NaN/Infinity yok); testli.
- ResizeObserver yalnız aktif bölümde; reading_speed için gün dizini.
- TODOS.md'ye iki satır: Gemini anlama soruları; çeviri bekleme süresi ölçümü.
<!-- /autoplan-accepted:ceo -->

<!-- autoplan-accepted:eng -->
- CEO bloğundaki "iki bölüm sonu geçerse akış duraklar, o bölümlerin süresi 0" kuralının YERİNE: bölüm başına kural; etkinliksiz tempo bölümü active_ms=0, gecerli=false; Adım A'da akış durmaz; Adım B'de art arda üç etkinliksiz bölüm sonunda, yoklamanın 20 sn zaman aşımından sonra duraklar; testli.
- CEO bloğundaki "sunucu 2× kişisel ortancadan hızlı serbest oturumu dışlar" kuralının tanımı: son 10 geçerli serbest oturumun ortancası, 2 katı üstü atılır, kalanların ortancası; n < 3 süzgeçsiz; testli.
- CEO bloğundaki "seviye çevrimi sınır içinde eski hızdan %10'dan fazla sapmaz" testinin YERİNE: çevrim ilk tempo başlangıcında tarayıcıda gerçek ölçüyle (eskiPxSn × 60 × harf ÷ yükseklik), Playwright ile çevrim öncesi ve sonrası px/sn eşitliği testi.
- reading_speed: oturum_id (UNIQUE, tekrar gönderim günceller), book_slug sütunu (resolve_slug), sunucu valid'i yeniden hesaplar; pydantic: words 0..chars, slug/url ≤ 2000, oturum_id deseni; testli.
- Bitiş bottom <= innerHeight; atlama (+0,2 oran, scrollToChapterRatio ve bölüm içi arama kancası) oturumu geçersiz yapar; sekme gizlenince keepalive gönderim; oturum günü bitiş günü; testli.
- ilk_hafta = ilk 5 geçerli serbest oturum; degisim 10 oturumdan azsa null; testli.
- Ölçüm bölümünde tempo önceki bölüm sonunda kapanır; okuma çizgisi örtüsü pointer-events: none; HTML bölümde harf 0 → geçersiz + yedek hız; testli.
- Mevcut testler güncellenir: tests/js/alt-cubuk.test.mjs, tests/js/oto-kaydir-yardimci.test.mjs, tests/tarayici/test_oto_kaydir.py.
- §7 öbek modu (kullanıcı kararı): Gemini öbekleri, bayt eşitliği denetimi ve kural yedeği, obekler tablosu (kaynak_sha256), GET /api/chapter/obekler, renderParagraphs tek çizim noktası ve geç gelen öbekte konum korunur, arama vurgusu öbek sınırını aşabilir, alt çubukta "Öbek" aç / kapa düğmesi (aria-pressed, obekModu ayarına kalıcı, iki yönde konum korunur; oturum ortasında değişirse oturum karışık sayılır), obek bayraklı ölçüm ve kartta karşılaştırma; testli (test_obekler.py, okuma-hizi.test.mjs, tarayici/test_obek_modu.py).
- Öbek yeniden çizim bütçesi 50 ms, Playwright performance.now() ile ölçülür.
<!-- /autoplan-accepted:eng -->
## Review record

### Faz 1 — CEO incelemesi (SELECTIVE EXPANSION, /autoplan otomatik kararlarıyla)

**Sistem denetimi.** Dal `roman-baglam`, son commit `50841d3`; açık değişiklik yok; bir
eski stash (`faz-sonraki-plan`, ilgisiz). İlgili TODO: "Okuma geçmişi listesi UI"
(TODOS.md:43). Otomatik kaydırma 2026-11-01'de eklendi, 9ea99c9 ile kilit/sayfa sonu
düzeltildi: tempo bu kodun üstüne kurulur, yeniden yazılmaz. Tasarım belgesi yok
(/office-hours önerisi autoplan'da atlandı; araştırma planın içinde).

**0A Öncüller**

| Öncül | İddia | Dayanak | Hüküm |
|---|---|---|---|
| P1 | Okur daha hızlı okumak istiyor; asıl dert binlerce bölümlük romanı bitirmek | kullanıcı isteği | geçerli |
| P2 | RSVP / Bionic / iç ses bastırma işe yaramaz | Rayner 2016, Snell 2024 | geçerli |
| P3 | Kaydırarak hızlandırma, silinen metinle hızlandırmanın etkisini taşır | Zamfira 2024 yöntemi silme; kaydırma değil | DOĞRULANMADI — kişisel ölçümle sınanacak (ölçüm bölümü) |
| P4 | Öz bildirim, anlama doğruluğunun yerini tutar | kanıt yok; öz bildirim iyimser | ZAYIF — ara önlem: art arda iki Rahattı; nesnel ölçüm son kapıda |
| P5 | Türkçe için 230 sözcük/dk ve 6,5 harf/sözcük uygun | kaynak yok | DOĞRULANMADI — içeride harf/dk, kişisel ölçüm esas |

Bir şey yapmamanın bedeli: okur mevcut "Hız 1-12" kaydırmayı tahminle kullanır, hızını
ve ilerlemesini hiç göremez; kalan süre herkese 230 sözcük/dk varsayar.

REALITY: premise-table pass 5 öncül tablosu; unverified=2 (Türkçe ortalama hız, harf/sözcük sabiti) app/web/js/alt-cubuk.js:15
REALITY: already-done pass otomatik kaydırma var, birimi px/sn; hız ölçümü yok app/web/js/oto-kaydir-yardimci.js:6
REALITY: surface-check finding plan "/api/reading-log/stats" yazıyordu, gerçek uç "/api/stats"; düzeltildi app/server.py:717
REALITY: binding-decisions pass tek scroll dinleyicisi kuralı korunuyor; dal kararı kaydı yok app/web/js/okuyucu.js:215
REALITY: numbers pass seviye hızları px/sn dizisi koddan okundu app/web/js/oto-kaydir-yardimci.js:6 ; kalan süre sabiti koddan okundu app/web/js/alt-cubuk.js:18
REALITY: deferred-asks pass bağlı issue yok; ertelenenler TODOS satırlarına bağlandı TODOS.md:43
REALITY: pr-count pass ship-policy dosyası yok, varsayılan tek PR; Adım A ve B iki ayrı dağıtım, kullanıcıya dönük tek yüzey okuyucu app/web/index.html:338

PLAN_REALITY: phase=ceo rows=7/7 missing=none unverified=2 verdict=complete

**0B Var olan kod (What already exists)**

| Alt sorun | Var olan | Kullanım |
|---|---|---|
| Hızlandırılmış akış | `oto-kaydir.js` (rAF döngüsü, kilit, parmakla bekleme, sayfa sonu) | korunur; yalnız hız birimi değişir |
| Hız hesabı | `oto-kaydir-yardimci.js` `adim`, `seviyeSinirla` | `adim` kalır; `HIZLAR`/seviye işlevleri yerini harf/dk çevrimine bırakır |
| Bölüm etkinliği | `setActiveChapter`, `updateActiveChapter`, `currentRatio` (okuyucu.js:57-80) | ölçüm buraya bağlanır |
| Kalan süre | `kalanDakika` (alt-cubuk.js:15) | imzası genişler |
| Okuma günlüğü | `reading_log.py`, `POST /api/reading-log` | aynı modüle yeni tablo |
| Kitap silme temizliği | `library.py:411` listesi | yeni satır |
| Ayar saklama | `settings`/`saveSettings` (ayarlar.js:12-37) | `kaydirmaHizi`, `okumaCizgisi` |

**0C Rüya durumu**

```
  BUGÜN                          BU PLAN                         12 AY SONRA
  "Hız 4" (px/sn), herkese  ---> kişisel harf/dk ölçümü, kel/dk ---> okur hızını, pratiğini ve
  230 kel/dk kalan süre,         konuşan tempo, öz bildirimle       anlamasını (nesnel) tek yerde
  ilerleme görünmez              uyarlama, ölçüm bölümleri,         görür; tempo anlama skoruna
                                 pratik dakikası                    göre kendini ayarlar
```
Plan hedefe doğru gider; eksik kalan tek parça nesnel anlama ölçümü (son kapıda).

**0D Yaklaşımlar** — A) bu plan; B) yalnız kel/dk etiketi + kişisel kalan süre; C) RSVP
"sprint" modu. Otomatik karar A (P1 bütünlük), ama CEO sesinin önerisiyle iki adımlı
teslim: Adım A ≈ B seçeneği, Adım B tempo uyarlaması. C kanıtla reddedildi.

**0E Kip:** SELECTIVE EXPANSION (autoplan kuralı). Plan ~12 dosyaya dokunur [estimated]:
yeni yetenek, mevcut okuyucu üstüne.

**0F/0G Seçmeli genişleme** — 10x: ölç → biraz hızlı oku → yokla → ayarla döngüsü tek
yerde. Önerilen eklemeler ve kararları CEO planında (Scope Decisions):
`~/.gstack/projects/novel-cevirmen/ceo-plans/2026-11-08-hizli-okuma.md`.
HOLD denetimleri: dosya sayısı 8'i geçiyor; daha az parçayla aynı hedef = Adım A
(kabul edildi, iki adımlı teslim).

**0H Spec inceleme döngüsü:** 3 çalıştırma (6/10, 6/10, 7/10). 31 bulgu; ilk ikisinin 26'sı
düzeltildi ve sonraki turda doğrulandı; üçüncünün 5 bulgusu elle uygulandı (issues
verified: 5 of 5, spec not re-verified). Ölçümler `analytics/spec-review.jsonl`'a yazıldı.
Belge onayı: autoplan otomatik A.

**0I Zaman sorgusu**

```
  SAAT 1   : harf sayımı (boşluk dışı), bölüm oturumu url anahtarı, 6,5 sabiti
  SAAT 2-3 : geri kaydırma/duraklama, biten url, tempo masada-telefon kuralı
  SAAT 4-5 : ResizeObserver ile px/sn, eski seviye çevrimi, pagehide keepalive
  SAAT 6+  : page.clock ile tarayıcı testleri, kart SVG'si, ölçüm bölümü şeridi
```
Emek: insan ekip ~4-5 gün / CC+gstack ~3-4 saat (iki adım toplamı).

**CEO çift ses**

Claude CEO alt ajanı tamamlandı (INPUT ceo 2e20d7e7…). Codex: **unavailable** —
`gpt-6-astra` modeli bu ChatGPT hesabında desteklenmiyor (model_not_found); ayar
değiştirilmedi. Etiket: `[single-model]`.

```
CEO DUAL VOICES — CONSENSUS TABLE:
  Dimension                            Claude  Codex  Consensus
  1. Premises valid?                   kısmen  N/A    N/A
  2. Right problem to solve?           kısmen  N/A    N/A
  3. Scope calibration correct?        hayır   N/A    N/A
  4. Alternatives sufficiently explored? hayır N/A    N/A
  5. Competitive/market risks covered? evet    N/A    N/A
  6. 6-month trajectory sound?         kısmen  N/A    N/A
```
Claude bulguları ve kararları: #1 nesnel anlama (KRİTİK) → ara önlem kabul, Gemini soruları
TASTE, son kapıda; #2 yöntemin yumuşatılmış olduğu → bilgi notunda açıkça; #3 aktarım
ölçümü → ölçüm bölümü + tempo çizgisi kabul; #4 masadaki telefon → iki bölüm sonu
kuralı kabul; #5 alt sınır → 700 harf/dk kabul; #6 göz gezdirme → 5000 üst sınır ve 2×
ortanca dışlama, pratik dakikası birincil gösterge kabul; #7 hacim kaldıracı → TODO'ya;
#8 iki adımlı teslim ve iki bölümde bir yoklama kabul; #9 TTS → NOT in scope.

**Bölüm 1 — Mimari**

```
  okuyucu.js ──setActiveChapter/onReaderScroll──► okuma-hizi.js ──► okuma-hizi-yardimci.js (saf)
      │                                               │  ▲
      │ pagehide (1820)                                │  └─ oto-kaydir.js:162 pointerdown → okumaHiziEtkinlik()
      ▼                                               ▼
  alt-cubuk.js kalanDakika ◄── localStorage novellink:okuma-hizi ◄── GET /api/reading-speed/stats
                                                      │
                                       POST /api/reading-speed (keepalive)
                                                      ▼
                                 server.py ──► reading_log.py: reading_speed tablosu
  oto-kaydir.js ◄── kaydirmaHizi (harf/dk) ── oto-kaydir-yardimci.js px/sn çevrimi ◄── ResizeObserver
       └─► yoklama şeridi / ölçüm bölümü önerisi (Adım B)
```
Yeni bağımlılık: `oto-kaydir.js` → `okuma-hizi.js` (dokunma ve tempo durumu). Gerekçeli;
tersine bağımlılık yok. Veri akışı: mutlu yol (bölüm biter → POST → stats tazelenir);
boş yol (stats yok → 1495 harf/dk yedek); hata yolu (POST düşer → yalnız o ölçüm
kaybolur, okuma bozulmaz). Tek nokta arızası yok; ölçek sorunu yok (tek kullanıcı,
gün başına onlarca satır). Geri alma: Adım A ve B ayrı commit'ler; `git revert` + SW
sürümü, dakikalar. Yalnız iş üstüne eser kontrolü (Value test): ilerleme kartı kullanıcı
isteğinin doğrudan karşılığı. Bulgu: 1 (oto-kaydir ↔ okuma-hizi bağlantısı adlandırıldı).

**Bölüm 2 — Hata ve kurtarma haritası**

```
  KOD YOLU                     | NE TERS GİDER               | SINIF
  -----------------------------|-----------------------------|------------------
  okuma-hizi.js gönderim       | ağ yok / sunucu kapalı      | TypeError (fetch)
                               | 422 doğrulama               | HTTP 422
  POST /api/reading-speed      | DB kilitli                  | sqlite3.OperationalError
                               | bozuk gövde                 | pydantic ValidationError
  GET .../stats                | ağ yok                      | TypeError (fetch)
                               | localStorage erişilemez     | DOMException
  px/sn çevrimi                | bölüm yüksekliği 0 / harf 0 | sıfıra bölme (NaN/Infinity)
  ResizeObserver               | tarayıcıda yok              | ReferenceError

  SINIF                 | KURTARILIR? | EYLEM                               | OKUR GÖRÜR
  ----------------------|-------------|-------------------------------------|---------------
  fetch TypeError       | E           | catch; ölçüm düşer (best-effort)    | hiçbir şey
  HTTP 422              | E           | console.warn ile alanlar            | hiçbir şey
  OperationalError      | E           | log_read gibi False döner           | hiçbir şey
  ValidationError       | E           | FastAPI 422                         | hiçbir şey
  localStorage hatası   | E           | try/catch; yedek hız                | 230 kel/dk kalan süre
  NaN/Infinity          | E (plana EKLENDİ) | hesap önce yedek hıza düşer   | akış eski hızla sürer
  ResizeObserver yok    | E           | bölüm açılışında bir kez ölç        | fark yok
```
GAP: sıfıra bölme planda yoktu → kabul edildi (Görevler T4). Ölçüm kaybı bilerek sessiz:
okuma akışı her zaman önce gelir (mevcut `reading_log` sözleşmesi, reading_log.py:8).

**Bölüm 3 — Güvenlik.** Yeni iki uç kimlik doğrulamasız (sunucunun genel durumu; açık
karar listesinde zaten var). Tehdit: ağdaki biri sahte hız satırı yazar — olasılık düşük
(Tailscale ağı), etki düşük (yalnız istatistik). Girdi doğrulaması pydantic sınırlarıyla
var; SQL parametreli; `slug`/`url` yalnız saklanır, HTML'e basılmaz (kart sayı gösterir).
Yeni sır, bağımlılık yok. Bulgu yok; kimlik doğrulama bu planın kapsamı dışında.

**Bölüm 4 — Veri akışı ve etkileşim uç durumları**

```
  bölüm aktif ─► oturum aç (url) ─► süre biriktir ─► bitti? ─► sonuç ─► POST ─► UPSERT
     │ ortadan girdi(>0,10)         │ sekme gizli/diyalog: sayma         │ valid=1 korunur
     │ → gecerli=false              │ geri kaydırma: duraklat            │ tekrar: son değer
     │ biten url → açılmaz          │ tempo 2 bölüm etkinliksiz: 0       │ DB kilitli: düşer
```
| ETKİLEŞİM | UÇ DURUM | ELE ALINDI? | NASIL |
|---|---|---|---|
| Yoklama şeridi | çift dokunma | E | ilk yanıt şeridi kapatır |
| Yoklama | yanıtsız | E | 20 sn / sonraki bölüm yarısı |
| − / + | sınırda basma | E | düğme pasifleşir |
| Tempo | masada telefon | E | iki bölüm sonu kuralı |
| Okuyucudan çıkış | yarım bölüm | E | pagehide keepalive, gecerli=false |
| Aynı bölümü iki cihazda | iki satır | E | UNIQUE(day,url,mode), valid=1 korunur |
| Gece yarısı | gün değişimi | E | `day` istemcinin yerel günü (mevcut kural) |
Async sıra: tek paylaşılan durum sunucu satırı; iki gönderim yarışında UPSERT kuralı
(valid=1 ezilmez) sonucu sıradan bağımsız kılar. Bulgu yok.

**Bölüm 5 — Kod kalitesi.** Saf yardımcı + DOM modülü ayrımı projedeki kalıba uyar
(`oto-kaydir-yardimci.js`, `alt-cubuk.js`). `HIZLAR` kaldırılınca `seviyeSinirla`
kullanan her yer güncellenmeli (grep: oto-kaydir.js, testler). Bulgu: 1 (eski seviye
kodunun silinmesi görevlere eklendi).

**Bölüm 6 — Testler**

```
  YENİ ŞEY                         | TÜR     | TEST
  ---------------------------------|---------|------------------------------------------
  oturum süresi / boşta kesme      | unit    | okuma-hizi.test.mjs
  biten url, geri kaydırma         | unit    | okuma-hizi.test.mjs
  tempo masada telefon             | unit    | okuma-hizi.test.mjs
  geçerlilik sınırları             | unit    | okuma-hizi.test.mjs
  kalanDakika üç yol               | unit    | okuma-hizi.test.mjs
  px/sn + sıfıra bölme             | unit    | okuma-hizi.test.mjs (EKLENDİ)
  seviye çevrimi                   | unit    | okuma-hizi.test.mjs
  Rahattı sayacı, ölçüm bölümü     | unit    | okuma-hizi.test.mjs
  reading_speed tablo/UPSERT/stats | integ.  | test_reading_speed.py
  kitap silme temizliği            | integ.  | test_reading_speed.py
  tempo kumandası, şerit, kart     | E2E     | tarayici/test_tempo_modu.py (page.clock)
```
Cuma 02:00 testi: bir bölümü tempo ile bitir → satır `mode=tempo`, kart güncellenir.
Düşman QA: bölümü 0,96'ya zıplatıp geri dön → ölçüm geçersiz. Kaos: POST 500 dönerken
okumaya devam → okuyucu hiç takılmaz. Piramit dengeli; zaman bağımlılığı `page.clock`
ve enjekte saatle sabitlenir.

**Bölüm 7 — Performans.** `ResizeObserver` her yüklü bölümde değil, yalnız AKTİF
bölümde gözlenir (sonsuz akışta onlarca bölüm olabilir) — plana eklendi. Harf sayımı
bölüm başına bir kez (`e.harf`). `speed_stats` son 30 gün + ilk hafta: küçük tablo,
`idx_reading_speed_day` dizini eklenir. Bulgu: 2 (ResizeObserver kapsamı, dizin).

**Bölüm 8 — Gözlemlenebilirlik.** Tek kullanıcı; pano gerekmez. İstemci 422'yi
`console.warn` ile alanlarıyla yazar; sunucu yeni uçlarda mevcut günlük düzenini kullanır.
Ayarlar sayfasındaki kart aynı zamanda "çalışıyor mu" göstergesidir (oturum sayısı artar).
Bulgu yok.

**Bölüm 9 — Dağıtım.** Yeni tablo `CREATE TABLE IF NOT EXISTS` ile tembel oluşur (mevcut
kalıp, geriye uyumlu). Eski istemci yeni sunucuyla sorunsuz (uçları çağırmaz); yeni
istemci eski sunucuya karşı 404 alır ve ölçümü düşürür. Sıra: sunucu + kabuk aynı
`git pull`; SW `SHELL_CACHE` artırılır. Dağıtım öncesi yedek ve koşan iş kontrolü mevcut
yordam. Smoke: `GET /api/reading-speed/stats?day=` 200. Bulgu yok.

**Bölüm 10 — Uzun vade.** Geri alınabilirlik 4/5 (tablo kalır ama zararsız). Borç:
`kaydirmaSeviyesi` çevrimi bir kez çalışır; bir sürüm sonra kaldırılabilir. Sonraki
adım: nesnel anlama ölçümü, hacim kaldıracı ölçümü. Bulgu yok.

**Bölüm 11 — Tasarım:** SKIPPED (Faz 0 UI kapsamı tespit etmedi). Not: plan kullanıcıya
görünen şerit, kumanda ve kart ekliyor; uygulama sırasında frontend-design ve
ui-ux-pro-max becerileri çağrılacak (kalıcı kullanıcı kuralı).

**Hata ve kurtarma kaydı / Arıza kipleri kaydı**

```
  KOD YOLU             | ARIZA                | KURTARILIR? | TEST? | OKUR GÖRÜR?      | GÜNLÜK?
  ---------------------|----------------------|-------------|-------|------------------|--------
  hız gönderimi        | ağ yok               | E           | E     | sessiz (bilerek) | hayır
  hız gönderimi        | 422                  | E           | E     | sessiz           | console
  reading_speed yazımı | DB kilitli           | E           | E     | sessiz           | hayır
  stats okuma          | çevrimdışı           | E           | E     | eski değer       | hayır
  px/sn çevrimi        | yükseklik/harf 0     | E           | E     | eski hız         | hayır
  tempo                | masada telefon       | E           | E     | akış durur       | hayır
  yoklama              | yanıtsız             | E           | E     | şerit kapanır    | hayır
```
KRİTİK BOŞLUK: 0 (sessiz satırların hepsi test edilmiş ve okumayı bozmuyor).

**NOT in scope** — Ertelenen: Gemini anlama soruları (TASTE, son kapıda), çeviri bekleme
ölçümü (hacim kaldıracı), okuma geçmişi UI (mevcut TODO). Reddedilen: RSVP, Bionic, iç ses
bastırma, harf harf silme, klavye kısayolları, `son_hafta`, TTS (ayrı değerlendirme).

**Rüya durumu farkı:** Plan bittiğinde okur hızını, pratiğini ve tempo etkisini görür;
12 aylık hedefe kalan tek büyük parça nesnel anlama ölçümüdür.

```
  +====================================================================+
  |            MEGA PLAN REVIEW — COMPLETION SUMMARY                   |
  +====================================================================+
  | Mode selected        | SELECTIVE EXPANSION                         |
  | System Audit         | otomatik kaydırma var; uç adı hatası        |
  | Step 0               | A yaklaşımı, iki adımlı teslim              |
  | Section 1  (Arch)    | 1 issues found                              |
  | Section 2  (Errors)  | 7 error paths mapped, 1 GAPS (giderildi)    |
  | Section 3  (Security)| 0 issues found, 0 High severity             |
  | Section 4  (Data/UX) | 7 edge cases mapped, 0 unhandled            |
  | Section 5  (Quality) | 1 issues found                              |
  | Section 6  (Tests)   | Diagram produced, 1 gaps (giderildi)        |
  | Section 7  (Perf)    | 2 issues found                              |
  | Section 8  (Observ)  | 0 gaps found                                |
  | Section 9  (Deploy)  | 0 risks flagged                             |
  | Section 10 (Future)  | Reversibility: 4/5, debt items: 1           |
  | Section 11 (Design)  | SKIPPED (no UI scope)                       |
  +--------------------------------------------------------------------+
  | NOT in scope         | written (10 items)                          |
  | What already exists  | written                                     |
  | Dream state delta    | written                                     |
  | Error/rescue registry| 7 rows, 0 CRITICAL GAPS                     |
  | Failure modes        | 7 total, 0 CRITICAL GAPS                    |
  | TODOS.md updates     | 2 items proposed                            |
  | Scope proposals      | 6 proposed, 2 accepted (+7 CEO-ses kabulü)  |
  | CEO plan             | written                                     |
  | Outside voice        | codex unavailable (model_not_found)         |
  | Lake Score           | N/A                                         |
  | Diagrams produced    | 4 (mimari, veri akışı, hata, zaman)         |
  | Stale diagrams found | 0                                           |
  | Unresolved decisions | 1 (Gemini anlama soruları, son kapı)        |
  | Reality rows         | 7/7 rows (PLAN_REALITY complete), 2 unverified |
  +====================================================================+
```

<!-- autoplan-baseline-edits:ceo {"sourceSha256":"2e20d7e735e7969438f811995f482291c7ccd49876016037306daa4453372450","replacements":[{"oldText":"\nBirim kuralı: içeride her hız **harf/dk** tutulur (harf = boşluk dışı karakter;\n","newText":"\nTeslim İKİ ADIMDA (CEO incelemesi, 2026-11-08):\n- **Adım A** (§1 ölçüm, §2 kalan süre, §3'ün yalnız birim/kumanda kısmı, §5'in ilgili\n  testleri): hemen faydalı, düşük risk. Tempo henüz hızlanmaz; okur 1-2 hafta\n  serbest okur, `ilk_hafta` tempo karışmamış gerçek başlangıç çizgisi olur.\n- **Adım B** (§3 yoklama + okuma çizgisi + uyarlama, §4 kart, ölçüm bölümü önerisi):\n  Adım A canlıdayken en az 5 geçerli serbest oturum biriktikten sonra.\n\nBirim kuralı: içeride her hız **harf/dk** tutulur (harf = boşluk dışı karakter;\n"},{"oldText":"    süre doğrudan etkin sayılır: dokunma akışı zaten durdurur (oto-kaydir.js:162) ve\n    sayfa sonunda döngü 4 sn'de kendiliğinden duraklar, yani akış okurun ekranda\n    olduğunu gösterir. Serbest okumada ve tempo duraklatılmışken etkinlik = kaydırma ya\n","newText":"    süre etkin sayılır, ama masaya bırakılan telefon için bir sınır var: dokunma akışı\n    yalnız parmak ekrandayken bekletir (oto-kaydir.js:162) ve sonsuz akışta sayfa\n    sonu beklemesi bölüm yüklendikçe sürer, yani akış tek başına okurun ekranda\n    olduğunu kanıtlamaz. Kural: son etkinlikten (dokunma ya da yoklama yanıtı) bu yana\n    İKİ bölüm sonu geçtiyse akış duraklatılır (ekran kilidi bırakılır) ve etkinliksiz\n    geçen o iki bölümün süresi sayılmaz (`active_ms = 0`, `gecerli=false`). Serbest okumada ve tempo duraklatılmışken etkinlik = kaydırma ya\n"},{"oldText":"    > 0,10 (ortadan başladı), hız 400-7200 harf/dk dışında (6,5 ile ≈ 60-1100 sözcük/dk).\n","newText":"    > 0,10 (ortadan başladı), hız 400-5000 harf/dk dışında (6,5 ile ≈ 60-770\n    sözcük/dk; üstü göz gezdirme ya da bölüm atlama). Sunucu ayrıca kişisel ortancanın\n    2 katından hızlı serbest oturumu `kisisel_hiz` hesabına almaz.\n"},{"oldText":"  değer yazılır, ama `valid=1` satır `valid=0` ile ezilmez) ve `log_speed`,\n","newText":"  değer yazılır, ama `valid=1` satır `valid=0` ile ezilmez; `idx_reading_speed_day`\n  dizini) ve `log_speed`,\n"},{"oldText":"  - `gunluk`: son 30 gün, gün başına `{gun, hdk, sdk}` ortanca (yalnız geçerli serbest).\n","newText":"  - `gunluk`: son 30 gün, gün başına `{gun, hdk, sdk}` ortanca (yalnız geçerli serbest)\n    ve `tempo_hdk` (o günün geçerli tempo oturumlarının ortancası; yoksa `null`).\n"},{"oldText":"  1500-4500 harf/dk (Türkçede ortalama ~6,5 harfli sözcükle ≈ 230-690 sözcük/dk;\n  ekranda o bölümün sözcük uzunluğuyla gösterilir). Her değişiklik (− / + %5, yoklama ±%4) sınırlanıp `saveSettings` ile\n","newText":"  700-4500 harf/dk (~6,5 harfli sözcükle ≈ 110-690 sözcük/dk; Türkçe eklemeli\n  olduğundan sözcük/dk İngilizceden düşük çıkar, alt sınır bilerek düşük; ekranda o\n  bölümün sözcük uzunluğuyla gösterilir). Her değişiklik (− / + %5, yoklama ±%4) sınırlanıp `saveSettings` ile\n"},{"oldText":"  harfi)`; yükseklik `ResizeObserver` ile izlenir, yazı boyutu / satır aralığı / kenar\n  değişince kendiliğinden yeniden hesaplanır. Saf hesap `oto-kaydir-yardimci.js`'e\n  (`HIZLAR` dizisi ve seviye işlevleri kalkar).\n","newText":"  harfi)`; yükseklik `ResizeObserver` ile YALNIZ aktif bölümde izlenir (sonsuz akışta\n  onlarca bölüm olabilir), yazı boyutu / satır aralığı / kenar değişince kendiliğinden\n  yeniden hesaplanır. Yükseklik ya da harf 0 ise (henüz çizilmemiş bölüm) hesap NaN /\n  Infinity üretmez, son geçerli px/sn'yi korur; o da yoksa 1495 harf/dk yedeği. Saf hesap `oto-kaydir-yardimci.js`'e\n  (`HIZLAR` dizisi ve seviye işlevleri kalkar; `seviyeSinirla` kullanan her yer —\n  oto-kaydir.js ve mevcut testler — güncellenir).\n"},{"oldText":"  Zorlandım\". Her tempo bölümünün sonunda bir kez sorulur. Rahattı +%4, İdare eder\n  aynı, Zorlandım −%4.\n","newText":"  Zorlandım\". İki tempo bölümünde bir sorulur (dırdıra dönmesin). Zorlandım hemen\n  −%4; Rahattı yalnız art arda İKİNCİ \"Rahattı\"da +%4 (öz bildirim anladığını fazla\n  sanmaya yatkın; tek yöne itmesin); İdare eder aynı ve \"Rahattı\" sayacını sıfırlar.\n- Ölçüm bölümü önerisi: art arda 5 tempo bölümünden sonra şerit bir kez \"Sıradaki\n  bölümü kendi hızında oku (ölçüm için)\" der ve o bölümde tempoyu kapatır; okur\n  \"Tempoda kal\" diyebilir. Çalışmanın asıl iddiası (tempodan sonra serbest hızın\n  artması) bu bölümlerle ölçülür.\n"},{"oldText":"  ölçülen oturum sayısı, bugünkü okuma dakikası. Veri yoksa \"Birkaç bölüm okuyunca\n","newText":"  ölçülen oturum sayısı. Bugünkü okuma dakikası kartın EN ÜSTÜNDE ve en büyük sayıdır\n  (kalıcı hızın asıl kaynağı pratik; hız sayısı ikincil, hedef haline gelmesin). Tempo\n  hızının seyri ikinci çizgi olarak (`gunluk` içinde `tempo_hdk`, tempo oturumlarının\n  ortancası). Veri yoksa \"Birkaç bölüm okuyunca\n"},{"oldText":"  iki cümle).\n","newText":"  iki cümle) ve açıkça: \"Tempo, çalışmadaki silinen metnin yumuşatılmış hali; etkisi\n  sende ölçülüyor. Anlama nesnel olarak ölçülmüyor, yalnız senin yanıtınla.\"\n"},{"oldText":"  seviye→harf/dk çevrimi (seviye 1, 4, 12) ve sınırlama; %5 ve %4 adımlarında sınır.\n","newText":"  seviye→harf/dk çevrimi (seviye 1, 4, 12; sınır içindeyse eski hızdan %10'dan fazla\n  sapmaz) ve sınırlama; masadaki telefon kuralı (iki bölüm sonu etkinliksiz →\n  duraklat, süre 0); \"Rahattı\" sayacı (tek Rahattı artırmaz, ikincisi +%4, İdare eder\n  sıfırlar); 5 tempo bölümünden sonra ölçüm bölümü önerisi; %5 ve %4 adımlarında sınır.\n"},{"oldText":"- `son_hafta` istatistiği (gösterildiği yer yok).\n\n","newText":"- `son_hafta` istatistiği (gösterildiği yer yok).\n- Sesli eşlikle okuma (TTS ile birlikte okuma): ayrı değerlendirme.\n- Okuma hacmini kısıtlayan çeviri bekleme süresinin ölçümü: TODOS.md'ye ertelendi.\n\n"},{"oldText":"  anlama soruları (ücretli; 2026-11-08 hızlı okuma planından ertelendi).\"\n\n","newText":"  anlama soruları (ücretli; 2026-11-08 hızlı okuma planından ertelendi).\"\n- `TODOS.md`'ye ikinci satır: \"Okuma hacmi kaldıracı: bölüm başına çeviri bekleme\n  süresini ölç; hız mı hacim mi daha büyük kaldıraç, veriyle gör.\"\n\n"}]} -->

<!-- autoplan-accepted:ceo -->
- İki adımlı teslim: Adım A (ölçüm, kişisel kalan süre, kel/dk kumandası), Adım B (yoklama, okuma çizgisi, uyarlama, kart, ölçüm bölümü) en az 5 geçerli serbest oturumdan sonra.
- Bölüm bazlı ölçüm: url anahtarlı oturum, açılış oranı ≤ 0,10, bitiş ≥ 0,95 ya da sonraki bölüm aktif, biten url aynı ziyarette yeniden açılmaz; testleri okuma-hizi.test.mjs.
- Tempo masada telefon kuralı: son dokunma/yanıttan beri iki bölüm sonu geçerse akış duraklar, kilit bırakılır, o bölümlerin süresi 0; testli.
- Geçerlilik sınırları 400-5000 harf/dk; sunucu 2× kişisel ortancadan hızlı serbest oturumu kisisel_hiz dışında tutar; test_reading_speed.py.
- kaydirmaHizi sınırı 700-4500 harf/dk; seviye çevrimi sınır içinde eski hızdan %10'dan fazla sapmaz; testli.
- Yoklama iki tempo bölümünde bir; Zorlandım −%4 hemen, Rahattı +%4 yalnız art arda ikincide, İdare eder sayacı sıfırlar; testli.
- Ölçüm bölümü önerisi: art arda 5 tempo bölümünden sonra bir kez; testli.
- Kartta pratik dakikası en üstte, tempo_hdk ikinci çizgi; bilgi notunda yumuşatılmış yöntem ve öz bildirim uyarısı.
- px/sn çevriminde yükseklik ya da harf 0 ise yedek hıza düşülür (NaN/Infinity yok); testli.
- ResizeObserver yalnız aktif bölümde; reading_speed için gün dizini.
- TODOS.md'ye iki satır: Gemini anlama soruları; çeviri bekleme süresi ölçümü.
<!-- /autoplan-accepted:ceo -->


### Faz 2 — Tasarım: ATLANDI (Faz 0 kapsam taraması UI tespit etmedi). Not: plan şerit, kumanda, kart ve öbek çizimi ekliyor; uygulamada frontend-design ve ui-ux-pro-max çağrılacak.

### Faz 2.5 — DX: ATLANDI, kural dışı. Tarayıcı `dxRequired=true` dedi; eşleşmeler yanlış pozitif: `sdk` Türkçe "sözcük/dk" kısaltması, `API` uygulamanın kendi uçları. Geliştiriciye dönük ürün yok. Son kapıda belirtildi.

### Faz 3 — Mühendislik incelemesi

**Kapsam itirazı.** Mevcut kodun karşıladığı parçalar: otomatik kaydırma döngüsü (oto-kaydir.js), tek kaydırma girişi (okuyucu.js:215), `pagehide`/`visibilitychange` kancaları (okuyucu.js:1820-1821), kitap silmede şema döngüsü (library.py:421), bölüm özeti modülünün `uret` enjeksiyon kalıbı (ozet_zinciri.py, translate.py:1460), tek çizim noktası `renderParagraphs` (okuyucu.js:726). Karmaşıklık: ~15 dosya [estimated], yeni modüller `okuma-hizi-yardimci.js`, `okuma-hizi.js`, `obekler.py`. 8 dosya eşiği aşılıyor; autoplan kuralı "kapsamı asla küçültme" (P2). Yapı sorusu otomatik: özgün düzen korunur, üç adımlı teslim zaten daha küçük parçalar (Adım A ≈ 7 dosya). Sonuç: scope accepted as-is.

REALITY: premise-table pass yorumdaki satır başına sözcük öncülü telefonda yanlış bulundu, çevrim gerçek ölçüye alındı app/web/js/oto-kaydir-yardimci.js:3 ; unverified=1 (harf/sözcük sabiti)
REALITY: already-done pass kitap silmede şema döngüsü book_slug tablolarını zaten siliyor, elle satır gereksiz app/core/library.py:421
REALITY: surface-check pass var olan uçlar ve kancalar doğrulandı: reading-log POST, pagehide ve visibilitychange app/server.py:707 ; app/web/js/okuyucu.js:1821
REALITY: binding-decisions pass CEO kararları korunuyor; masadaki telefon kuralı Adım A'da akışı durdurmayacak biçimde inceltildi app/web/js/oto-kaydir.js:162
REALITY: numbers pass currentRatio formülü koddan okundu, son bölümde 0,95'e ulaşmayabilir app/web/js/okuyucu.js:62
REALITY: deferred-asks pass bağlı issue yok; ertelemeler TODOS'a yazılıyor TODOS.md:43
REALITY: pr-count pass tek dal, Adım A ve B iki dağıtım app/web/index.html:338

PLAN_REALITY: phase=eng rows=7/7 missing=none unverified=1 verdict=complete

**Eng çift ses.** Claude eng alt ajanı tamamlandı (INPUT eng d4d79b87…). Codex: unavailable (`gpt-6-astra` model_not_found, CEO ile aynı neden; yeniden denenmedi). `[single-model]`.

```
ENG DUAL VOICES — CONSENSUS TABLE:
  Dimension                           Claude  Codex  Consensus
  1. Architecture sound?               evet    N/A    N/A
  2. Test coverage sufficient?         hayır   N/A    N/A
  3. Perf risks + budget/bench named?  evet    N/A    N/A
  4. Security threats covered?         kısmen  N/A    N/A
  5. Error paths handled?              hayır   N/A    N/A
  6. Deployment risk manageable?       evet    N/A    N/A
```

Claude eng bulguları ve kararları (hepsi kabul, P1/P5): Y1 geriye dönük masada-telefon → bölüm başına kural; Y2 Adım A'da akış durmaz, Adım B'de üç bölüm + yoklama zaman aşımı; Y3 seviye çevrimi tarayıcıda gerçek ölçüyle; O1 `oturum_id`; O2 `visibilitychange` gönderimi; O3 `bottom <= innerHeight`; O4 atlama tespiti; O5 `book_slug` sütunu + `resolve_slug`; O6 ilk 5 oturum; O7 pydantic sınırları + sunucuda valid yeniden hesap; O8 süzgeç tanımı; O9 ölçüm bölümünde tempo önceki bölüm sonunda kapanır; L2 çıkış kancası; L3 HTML bölüm; L4 `pointer-events: none`; L5 gün = bitiş günü. L1 (büyük ekran boşta kesmesi) ve L6 (ayar/not kaldırma) reddedildi: telefon ağırlıklı kullanım, zararsız.

**Kullanıcı kararı (inceleme sırasında, 2026-11-08):** "okuma yaparken kelimeleri blok blok görme" → seçenek "Deneme modu, Gemini öbekleri" → §7 eklendi. §7 alt ajanın girdisinden SONRA eklendi; yalnız ana incelemeci inceledi (iki bulgu eklendi: öbekler bölüm açılışını bekletmez; arama vurgusu öbek sınırını aşabilir).

**Bölüm 1 — Mimari**

```
                 ┌──────────────── okuyucu.js ────────────────┐
  scroll ──► onReaderScroll ──┐   setActiveChapter   renderParagraphs ◄── entry.obekler
                              ▼          │                   ▲
                      okuma-hizi.js ◄────┘          GET /api/chapter/obekler
                       │   ▲    │                            │
   oto-kaydir.js:162 ──┘   │    └─ POST /api/reading-speed   ▼
   (pointerdown)           │       (keepalive, oturum_id)  obekler.py ──uret──► Gemini
                           │                 │               │  └─ kural_obekleri (yedek)
   okuma-hizi-yardimci.js ─┘                 ▼               ▼
   (saf: süre, geçerlilik, çevrim)   reading_log.py      obekler tablosu
                                     reading_speed  ◄─ library.py:421 şema döngüsü (silme)
   alt-cubuk.js kalanDakika ◄── localStorage novellink:okuma-hizi ◄── GET .../stats
```
İki şekil (design-twice): (A) ölçüm durumu istemcide `okuma-hizi.js`'te, sunucu yalnız satır + istatistik; (B) istemci ham olay akışı gönderir, sunucu oturumlaştırır. A seçildi: arayüz küçük (bir POST), politika tek yerde (saf yardımcı), çevrimdışı çalışır; B ağ ve depolamayı şişirir. Kırmızı bayraklar: "iki yerde aynı karar" riski kişisel hızda vardı (istemci `kisiselHiz` + sunucu) — spec incelemesinde istemci kopyası kaldırıldı; sunucu `valid`'i yeniden hesaplar, istemci yalnız ön filtre (bilinçli, tek doğru kaynak sunucu). Başka bayrak yok.

**Bölüm 2 — Kod kalitesi.** Saf yardımcı / DOM modülü ayrımı projeyle uyumlu. `HIZLAR` kaldırılırken `ESKI_HIZLAR` yalnız çevrim için kalır (bir sürüm sonra silinebilir, borç). `obekler.py` `ozet_zinciri.py` kalıbını tekrarlar; ortak yardımcıya çıkarmak iki çağıranla erken (rubrik: davranışlar farklı — biri özet üretir, öteki metni korumak zorunda). Karar: ayrı modül.

**Bölüm 3 — Testler**

```
CODE PATHS                                         USER FLOWS
[+] okuma-hizi-yardimci.js                         [+] Serbest okuma ölçümü
  ├── oturum aç/duraklat/sür (url)  [GAP→plan]       ├── [GAP→plan] bölümü bitir → kart
  ├── bitiş: bottom<=innerHeight    [GAP→plan]       ├── [GAP→plan] [→E2E] geri kaydırma
  ├── atlama (+0,2, kanca)          [GAP→plan]       └── [GAP→plan] sekme gizle → gönderim
  ├── boşta 90 sn / tempo etkinliği [GAP→plan]     [+] Tempo
  ├── geçerlilik bandı, HTML harf 0 [GAP→plan]       ├── [GAP→plan] [→E2E] kel/dk, +%5
  ├── seviye çevrim formülü         [GAP→plan]       ├── [GAP→plan] [→E2E] eski seviye eşitliği
  └── Rahattı sayacı, ölçüm bölümü  [GAP→plan]       └── [GAP→plan] [→E2E] yoklama, zaman aşımı
[+] reading_log.py speed                           [+] Öbek modu
  ├── oturum_id upsert              [GAP→plan]       ├── [GAP→plan] [→E2E] geç gelen öbek, konum
  ├── valid yeniden hesap           [GAP→plan]       ├── [GAP→plan] [→E2E] terim/arama/çift dokunma
  ├── süzgeç, ilk 5, değişim        [GAP→plan]       └── [GAP→plan] [→E2E] uç hatası → kural
  └── silme (alias)                 [GAP→plan]
[+] obekler.py
  ├── bayt eşitliği reddi           [GAP→plan]
  ├── kaynak_sha256 bayatlama       [GAP→plan]
  └── zaman aşımı → kural           [GAP→plan]
[+] alt-cubuk.js kalanDakika üç yol [★★ mevcut test güncellenir]
LLM: obekler istemi [→EVAL yok] — çıktı bayt eşitliğiyle denetlenir; kalite ölçümü elle
COVERAGE: yeni yolların hepsi planda testli; mevcut 3 test dosyası güncellenir
```
Test planı dosyası: `~/.gstack/projects/novel-cevirmen/OMEREK-roman-baglam-eng-review-test-plan-20261108-204628.md`. Eksik bulunanlar plana eklendi (Eng O1-O9 testleri, öbek testleri). LLM eval: öbek istemi için bayt eşitliği denetimi kalite garantisi değildir; ilk 20 bölümde reddedilen paragraf oranı elle izlenecek (`obekler.reddedilen`).

**Bölüm 4 — Performans.** Sıcak yol `onReaderScroll`: ölçüm işi O(1) (zaman damgası, oran farkı); ek DOM okuması yalnız aktif bölümde `getBoundingClientRect` (zaten yapılıyor). `ResizeObserver` yalnız aktif bölüm. `speed_stats` sınırlı sorgular (son 30 gün, son 10 / ilk 5 oturum), gün dizini. Öbek çizimi: bölüm başına bir yeniden çizim; ~15k harflik bölümde ~1500 span [estimated], telefonda ölçülmeli (bütçe: yeniden çizim 50 ms altı; uygulamada Playwright ile `performance.now()` ölçümü görevine eklendi). Gemini çağrısı yalnız öbek modunda, önden bir bölüm.

**Arıza kipleri kaydı**

```
  YOL                      | ARIZA                         | TEST? | HATA YÖNETİMİ        | OKUR GÖRÜR
  -------------------------|-------------------------------|-------|----------------------|-----------------
  hız gönderimi            | ağ yok / Android süreci öldü  | E     | keepalive + hidden   | sessiz (bilerek)
  reading_speed yazımı     | DB kilitli                    | E     | False döner          | sessiz
  stats                    | çevrimdışı                    | E     | önbellek             | eski değer
  px/sn                    | yükseklik/harf 0              | E     | yedek hız            | akış sürer
  seviye çevrimi           | bölüm çizilmemiş              | E     | yedek 1495 harf/dk   | hız biraz farklı
  öbek üretimi             | model harf değiştirdi         | E     | kural yedeği         | kural öbekleri
  öbek üretimi             | zaman aşımı / 429             | E     | kural yedeği + api_durum | kural öbekleri
  öbek çizimi              | geç geldi                     | E     | konum korunur        | kısa yeniden çizim
```
KRİTİK BOŞLUK: 0.

**What already exists:** yukarıdaki kapsam itirazı ve CEO 0B tablosu; ek olarak `ozet_zinciri.py` (öbek modülü kalıbı) ve `renderParagraphs` (tek çizim noktası).

**NOT in scope:** CEO listesi + L1 (büyük ekran boşta kesmesi) + öbekler için otomatik kalite değerlendirmesi (eval) — elle izleme yeterli.

**Paralelleştirme**

| Adım | Modüller | Bağımlı |
|---|---|---|
| A-sunucu | app/core, app/server | — |
| A-istemci | app/web/js (okuma-hizi, alt-cubuk, oto-kaydir) | A-sunucu (uç sözleşmesi) |
| B | app/web/js (oto-kaydir, ayarlar), style | A |
| C-sunucu | app/core/obekler, app/server | A-sunucu |
| C-istemci | app/web/js/okuyucu.js, ayarlar | C-sunucu, A-istemci |

Lane 1: A-sunucu → A-istemci → B. Lane 2: C-sunucu (A-sunucu birleşince). Çakışma: `server.py` ve `ayarlar.js` iki lane'de; sıralı birleştir.

**Completion summary**
- Step 0: Scope Challenge — scope accepted as-is
- Reality rows: 7/7 applicable rows emitted (PLAN_REALITY complete), 1 unverified premise
- Architecture Review: 1 issue found (çift karar riski, giderildi)
- Code Quality Review: 1 issue found (ESKI_HIZLAR borcu)
- Test Review: diagram produced, 20 gaps identified (hepsi plana test olarak eklendi)
- Performance Review: 1 issue found (öbek çizim bütçesi)
- NOT in scope: written
- What already exists: written
- TODOS.md updates: 2 items written
- Failure modes: 0 critical gaps flagged
- Unresolved decisions: 1 (Gemini anlama soruları, son kapı)
- Outside voice: codex unavailable (model_not_found)
- Parallelization: 2 lanes, 2 parallel / 3 sequential
- Lake Score: N/A



<!-- autoplan-baseline-edits:eng {"sourceSha256":"06dcd1d39dcaa441f6018c007a5301057d875fb17c8c5c564fe996216c88b744","replacements":[{"oldText":"  Adım A canlıdayken en az 5 geçerli serbest oturum biriktikten sonra.\n\n","newText":"  Adım A canlıdayken en az 5 geçerli serbest oturum biriktikten sonra.\n- **Adım C** (§7 öbek modu, kullanıcı kararı 2026-11-08 \"Deneme modu, Gemini\n  öbekleri\"): Adım B'den bağımsız; Adım A'nın ölçümü üstüne kurulur.\n\n"},{"oldText":"    Bölüm, oran ≥ 0,95'e ulaşınca ya da sonraki bölüm aktif olunca biter (kitabın son\n    bölümünde sonraki bölüm olmadığı için yalnız oran kuralı geçer). Bitmeden bırakılan\n    oturum (okuyucudan çıkış, başka kitaba geçiş, `pagehide` — okuyucu.js:1820'deki\n    mevcut kanca) `gecerli=false` olarak `keepalive` ile gönderilir: hıza girmez,\n    pratik dakikasına girer. Biten url aynı\n    okuyucu ziyaretinde yeniden oturum açmaz (geri dönüp bakmak yeni ölçüm değildir).\n  - `sureEkle(oturum, simdi, etkin)`: etkin süreyi biriktirir. Sekme gizli ya da bir\n","newText":"    Bölüm, altı ekranın altına ulaşınca (`el.getBoundingClientRect().bottom <=\n    innerHeight`; `currentRatio` reader-bar çizgisini ölçtüğü için kitabın son\n    bölümünde 0,95'e hiç ulaşmayabilir, okuyucu.js:57) ya da sonraki bölüm aktif\n    olunca biter. Bitmeden bırakılan oturum (okuyucudan çıkış: `readerView` `hidden`\n    MutationObserver, oto-kaydir.js:171 kalıbı; başka kitaba geçiş; `pagehide`,\n    okuyucu.js:1820) `gecerli=false` olarak `keepalive` ile gönderilir: hıza girmez,\n    pratik dakikasına girer. Sekme gizlenince (`visibilitychange: hidden`,\n    okuyucu.js:1821; Android PWA'da `pagehide` çoğu zaman gelmez) o anki durum aynı\n    `oturum_id` ile gönderilir, oturum kapanmaz. Oturumun günü bitiş günüdür. Biten url aynı\n    okuyucu ziyaretinde yeniden oturum açmaz (geri dönüp bakmak yeni ölçüm değildir).\n    Atlama: tek kaydırma olayında oran 0,2'den fazla ilerlerse ya da\n    `scrollToChapterRatio` / bölüm içi arama gezintisi `okumaHiziAtlama()` çağırırsa\n    oturum geçersiz olur (süresi pratik dakikasına yine girer).\n  - `sureEkle(oturum, simdi, etkin)`: etkin süreyi biriktirir. Sekme gizli ya da bir\n"},{"oldText":"    olduğunu kanıtlamaz. Kural: son etkinlikten (dokunma ya da yoklama yanıtı) bu yana\n    İKİ bölüm sonu geçtiyse akış duraklatılır (ekran kilidi bırakılır) ve etkinliksiz\n    geçen o iki bölümün süresi sayılmaz (`active_ms = 0`, `gecerli=false`). Serbest okumada ve tempo duraklatılmışken etkinlik = kaydırma ya\n","newText":"    olduğunu kanıtlamaz. Kural bölüm başınadır (geriye dönük değil; gönderilmiş satır\n    düzeltilmez): bir tempo bölümü boyunca hiç etkinlik (dokunma ya da yoklama yanıtı)\n    olmadıysa o bölüm `active_ms = 0`, `gecerli=false` gönderilir. Adım A'da akış\n    DURDURULMAZ (bugünkü kaydırma davranışı korunur). Adım B'de art arda ÜÇ etkinliksiz\n    bölüm sonunda, yoklamanın 20 sn zaman aşımı geçtikten sonra, akış duraklatılır ve\n    ekran kilidi bırakılır (yoklama ile duraklatma aynı ana denk gelmez). Serbest okumada ve tempo duraklatılmışken etkinlik = kaydırma ya\n"},{"oldText":"    sözcük/dk; üstü göz gezdirme ya da bölüm atlama). Sunucu ayrıca kişisel ortancanın\n    2 katından hızlı serbest oturumu `kisisel_hiz` hesabına almaz.\n","newText":"    sözcük/dk; üstü göz gezdirme ya da bölüm atlama). HTML içerikli (PDF/EPUB)\n    bölümlerde harf 0'dır: ölçüm geçersiz, tempo yedek hıza düşer.\n"},{"oldText":"- Sunucu: `app/core/reading_log.py` içine `reading_speed` tablosu (`day, slug, url,\n  mode, chars, words, active_ms, valid, ts`; `UNIQUE(day, url, mode)`, tekrarında son\n  değer yazılır, ama `valid=1` satır `valid=0` ile ezilmez; `idx_reading_speed_day`\n  dizini) ve `log_speed`,\n","newText":"- Sunucu: `app/core/reading_log.py` içine `reading_speed` tablosu (`oturum_id, day,\n  book_slug, url, mode, chars, words, active_ms, valid, ts`; `oturum_id` istemcinin\n  oturum başına ürettiği rastgele kimlik, `UNIQUE(oturum_id)`, aynı oturumun tekrar\n  gönderimi o satırı günceller; aynı gün aynı bölümün ikinci okuması ayrı satırdır;\n  `idx_reading_speed_day` dizini; `book_slug` POST'ta `library.resolve_slug` ile\n  çözülür). Sunucu `valid`'i istemciye güvenmeden yeniden hesaplar (hız bandı,\n  harf ≥ 1500, etkin süre ≥ 60 sn) ve istemcinin `gecerli=false` dediğini geçerli\n  yapmaz ve `log_speed`,\n"},{"oldText":"  - `kisisel_hiz`: son 10 geçerli serbest oturumun ortancası (`hdk`, `sdk`).\n  - `ilk_hafta`: `{hdk, sdk, n, bas_gun}` — ilk geçerli serbest ölçümün gününden\n    (`bas_gun`) başlayan 7 takvim gününün ortancası ve oturum sayısı.\n  - `degisim`: `kisisel_hiz.hdk ÷ ilk_hafta.hdk − 1`; 7 gün dolmadıysa (`day` <\n    `bas_gun` + 7) YA DA `ilk_hafta.n` < 5 ise `null`.\n","newText":"  - `kisisel_hiz`: son 10 geçerli serbest oturumun ortancası alınır, onun 2 katından\n    hızlı olanlar atılır, kalanların ortancası (`hdk`, `sdk`); n < 3 ise süzgeç yok.\n  - `ilk_hafta`: `{hdk, sdk, n, bas_gun}`: İLK 5 geçerli serbest oturumun ortancası\n    (takvim penceresi değil, ara verilince kilitlenmesin); `n` < 5 ise `null`.\n  - `degisim`: `kisisel_hiz.hdk ÷ ilk_hafta.hdk − 1`; `ilk_hafta` `null` ise ya da\n    toplam geçerli serbest oturum 10'dan azsa (başlangıç çizgisiyle aynı küme\n    olmasın) `null`.\n"},{"oldText":"  Kitap silinince bu tablo da temizlenir (`library.py:411` silme listesine satır).\n- `server.py`: `POST /api/reading-speed` (pydantic: gün `YYYY-MM-DD`, `mode`\n  serbest|tempo, `chars` 0-2.000.000, `active_ms` 0-86.400.000, `slug`/`url`\n  boş değil), `GET /api/reading-speed/stats?day=`. `sw.js`: GET ucu önbellek dışı\n","newText":"  Kitap silme: elle satır gerekmez; library.py:421'deki şema döngüsü `book_slug`\n  sütunu olan her tabloyu siler (testle doğrulanır).\n- `server.py`: `POST /api/reading-speed` (pydantic: `oturum_id` 8-64 karakter\n  `[A-Za-z0-9-]`, gün `YYYY-MM-DD`, `mode` serbest|tempo, `chars` 0-2.000.000,\n  `words` 0..`chars` (sözcük/dk yalnız `words ≥ 1` ise hesaplanır), `active_ms`\n  0-86.400.000, `slug`/`url` boş değil ve en çok 2000 karakter), `GET /api/reading-speed/stats?day=`. `sw.js`: GET ucu önbellek dışı\n"},{"oldText":"- Başlangıç değeri: `kaydirmaHizi` varsa o. Yoksa ve eski `kaydirmaSeviyesi` varsa bir\n  kez çevrilir: seviyenin px/sn'si × (60 ÷ 33 px satır) × 10 sözcük × 6,5 harf/sözcük\n  (yorumdaki 19 px / 1,75 satır ölçeği; seviye 4 = 16 px/sn ≈ 1890 harf/dk), sonra\n  sınırlanır. İkisi de yoksa kişisel hız × 1,10; o da yoksa 1600 harf/dk.\n","newText":"- Başlangıç değeri: `kaydirmaHizi` varsa o. Yoksa ve eski `kaydirmaSeviyesi` varsa\n  ilk tempo başlangıcında tarayıcıda GERÇEK ölçüyle bir kez çevrilir:\n  `kaydirmaHizi = eskiPxSn × 60 × (aktif bölümün harfi ÷ çizilmiş yüksekliği px)`,\n  sonra sınırlanır; böylece o andaki kaydırma hızı birebir korunur (yorumdaki\n  \"satırda 10 sözcük\" varsayımı telefonda yaklaşık %50-75 yanlış; eski px/sn tablosu\n  `ESKI_HIZLAR` adıyla yalnız bu çevrim için kalır). İkisi de yoksa kişisel hız × 1,10; o da yoksa 1600 harf/dk.\n"},{"oldText":"  satırlar hafifçe soluklaşır (çalışmadaki \"kayan örtü\"nün okumayı bozmayan hali).\n  Yalnız tempo akarken görünür; ayar `okumaCizgisi` (varsayılan `true`, okuma\n","newText":"  satırlar hafifçe soluklaşır (çalışmadaki \"kayan örtü\"nün okumayı bozmayan hali).\n  Örtü `pointer-events: none` (terim dokunuşu ve metin seçimi bozulmasın).\n  Yalnız tempo akarken görünür; ayar `okumaCizgisi` (varsayılan `true`, okuma\n"},{"oldText":"  bölümü kendi hızında oku (ölçüm için)\" der ve o bölümde tempoyu kapatır; okur\n","newText":"  bölümü kendi hızında oku (ölçüm için)\" der ve tempoyu ÖNCEKİ bölümün bitişinde\n  (sıradaki bölüm aktif olmadan) kapatır ki ölçüm bölümü `serbest` sayılsın; okur\n"},{"oldText":"  seviye→harf/dk çevrimi (seviye 1, 4, 12; sınır içindeyse eski hızdan %10'dan fazla\n  sapmaz) ve sınırlama; masadaki telefon kuralı (iki bölüm sonu etkinliksiz →\n  duraklat, süre 0); \"Rahattı\" sayacı (tek Rahattı artırmaz, ikincisi +%4, İdare eder\n","newText":"  seviye→harf/dk çevrim formülü (verilen harf ve yükseklikle) ve sınırlama; masadaki\n  telefon kuralı (etkinliksiz bölüm → süre 0; Adım A'da akış durmaz; Adım B'de üçüncü\n  etkinliksiz bölüm sonunda, yoklama zaman aşımından sonra duraklar); son bölüm\n  bitişi (`bottom <= innerHeight`); ileri atlama (oran +0,2 ve `okumaHiziAtlama`);\n  HTML bölüm (harf 0) geçersiz ve yedek hız; ölçüm bölümünde tempo önceki bölüm\n  sonunda kapanır; \"Rahattı\" sayacı (tek Rahattı artırmaz, ikincisi +%4, İdare eder\n"},{"oldText":"- `tests/test_reading_speed.py`: tablo oluşumu, doğrulama (422), UNIQUE tekrarında\n  son değer ama `valid=1` korunur, `kisisel_hiz` yalnız geçerli serbest, `ilk_hafta` takvim penceresi,\n  `bugun_dk` geçersizleri de sayar, kitap silmede temizlik.\n","newText":"- `tests/test_reading_speed.py`: tablo oluşumu; doğrulama 422 (`words` > `chars`,\n  uzun url, bozuk `oturum_id`); aynı `oturum_id` tekrarında güncelleme, farklı\n  oturum ayrı satır; sunucu `valid`'i yeniden hesaplar; `kisisel_hiz` süzgeci (n < 3\n  süzgeçsiz, 2× üstü atılır); `ilk_hafta` ilk 5 oturum ve `degisim` 10 oturumdan\n  azsa `null`; `bugun_dk` geçersizleri de sayar; alias slug ile yazılıp kitap\n  silinince satırlar gider.\n- Güncellenecek mevcut testler: `tests/js/alt-cubuk.test.mjs` (`kalanDakika` imzası),\n  `tests/js/oto-kaydir-yardimci.test.mjs` ve `tests/tarayici/test_oto_kaydir.py`\n  (`HIZLAR`/seviye kalkıyor).\n"},{"oldText":"  ilerleme kartı veriyle ve verisiz.\n","newText":"  ilerleme kartı veriyle ve verisiz; eski `kaydirmaSeviyesi=4` ile tempo başlatınca\n  px/sn çevrimden önce ve sonra aynı; sekme gizlenince gönderim (`keepalive`).\n\n### 7. Öbek modu (deneme; kelimeleri blok blok görme)\n\nDayanak: hızlı okurların algı aralığı daha geniştir ama bu, sözcük işlemenin kolay\nolmasının SONUCUDUR; göz egzersiziyle genişletildiğine dair kanıt yok (Rayner,\nSlattery ve Bélanger 2010; Rayner 2016). Metni anlam öbeklerine bölüp göstermek\n(phrase-cued text; visual-syntactic text formatting, Walker 2005, yöntemin\ngeliştiricilerinden) üniversite öğrencilerinde anlama ve verimi artırdı; akıcı\nyetişkinde etkisi belirsiz. Bu yüzden DENEME modudur ve etkisi kişisel ölçümle sınanır.\n\n- Öbek sınırlarını Gemini işaretler. Yeni modül `app/core/obekler.py`\n  (`ozet_zinciri.py` kalıbı: üretim işlevi `uret` dışarıdan verilir,\n  `translate.py:1460`'taki `_izli_uret` sarmalı ve `api_durum.baglam(asama=\"obek\")`).\n  İstem: Türkçe paragrafı HİÇBİR harfini değiştirmeden anlam öbeklerine `|` ile böl\n  (öbek 2-5 sözcük; özne öbeği, eylem öbeği, yan cümle, -ken/-ınca/-ıp/-dığında\n  ekli öbekler bir arada).\n- Doğrulama (güven sınırı: model metni değiştirebilir): `|` çıkarılınca paragraf\n  bayt bayt aynı değilse ya da bir öbek 8 sözcükten uzun / boşsa o paragraf için\n  model çıktısı reddedilir ve KURAL TABANLI yedek kullanılır (noktalama, ve/ama/ki/\n  çünkü/ile bağlaçları, -ken/-ınca/-ıp/-dığında ekleri; saf işlev\n  `kural_obekleri(paragraf)`). Reddedilen paragraf sayısı satırda saklanır.\n- Saklama: `obekler` tablosu (`url, book_slug, kaynak_sha256, sinirlar_json, model,\n  reddedilen, ts`; `UNIQUE(url)`). `kaynak_sha256` çeviri metninin özeti: bölüm\n  yeniden çevrilir ya da düzeltilirse öbekler bayatlar ve yeniden üretilir.\n  `sinirlar_json` paragraf başına öbek bitiş konumları (karakter sırası) — metnin\n  kopyası tutulmaz. `book_slug` sütunu sayesinde kitap silmede kendiliğinden silinir.\n- Uç: `GET /api/chapter/obekler?url=` → `{sinirlar, kaynak: \"model\"|\"kural\"}`.\n  Kayıt varsa ve özet tutuyorsa hemen döner; yoksa üretir (en çok 30 sn), hata ya da\n  zaman aşımında `kaynak: \"kural\"` ile kural tabanlı sınırları döner (okuyucu asla\n  öbeksiz kalmaz, hata sessiz değil: `api_durum` kaydına düşer). Yalnız öbek modu\n  açıkken çağrılır; sıradaki bölüm için önden bir istek atılır. `content_type='html'`\n  bölümlerde öbek yok. `sw.js`: ağ öncelikli, çevrimdışıyken önbellekteki son yanıt;\n  `SHELL_CACHE` artırılır.\n- Çizim tek noktadan: `renderParagraphs` (okuyucu.js:726) bölümün `entry.obekler`i\n  varsa paragrafı öbek span'leriyle kurar; yoksa bugünkü gibi düz metin. Bölüm ÖNCE\n  düz çizilir, öbekler gelince `renderParagraphs` yeniden çağrılır ve okuma konumu\n  `currentRatio` ile korunur (öbek isteği bölüm açılışını asla bekletmez). Arama\n  vurgusu (`appendHighlighted`, okuyucu.js:1671) öbek sınırlarını bilir: eşleşme bir\n  öbek sınırını aşarsa `mark` iki span'e bölünür; `runFind` bugünkü gibi\n  `querySelectorAll(\"mark\")` ile sayar (bölünmüş eşleşme tek sayılsın diye\n  `data-eslesme` kimliği).\n- Gösterim: her öbek `<span class=\"obek\">`; öbekler\n  arasında hafif ek boşluk ve tek-çift öbekte çok hafif zemin farkı (koyu/sepya temada\n  ayrı ton). Metin düğümleri bölünse de sözcük içinde bölme yapılmaz; terim dokunuşu,\n  sözlük seçimi, bölüm içi arama vurgusu ve çift dokunmada İngilizce orijinal bugünkü\n  gibi çalışmalı (bunlar span içinde sözcük arar; testle doğrulanır).\n- Tempo ile birlikte (Adım B'nin okuma çizgisi varsa): çizginin üstüne gelen öbek\n  vurgulanır, böylece göz sözcük sözcük değil öbek öbek ilerletilir (Outread tarzı\n  kılavuz vurgu). Tempo yoksa yalnız görsel öbekler.\n- Aç / kapa (kullanıcı isteği 2026-11-08: \"bu bir mod gibi açılır ve kapatılır\n  olmalı\"): okuyucu alt çubuğunda \"Kaydır\"ın yanında \"Öbek\" düğmesi (index.html:331\n  sırası); tek dokunuşla açılır / kapanır, açıkken basılı görünür (`aria-pressed`),\n  durum `obekModu` ayarında saklanır (varsayılan `false`) ve okuma ayarlarında da\n  aynı anahtar \"Öbek modu (deneme)\" olarak durur. Açınca aktif ve görünen bölümler\n  öbekli yeniden çizilir (öbekler gelene dek düz), kapatınca düz metne döner; her\n  iki geçişte okuma konumu korunur. Açıkken kısa bir bildirim: \"Öbek modu açık\".\n  Oturum ortasında mod değişirse o bölümün oturumu `obek` bayrağıyla değil geçersiz\n  (karışık) sayılır, kişisel hıza da öbek hızına da girmez.\n- Ölçüm: oturuma `obek` bayrağı eklenir (`reading_speed.obek` sütunu, 0/1);\n  `kisisel_hiz` yalnız `obek=0` serbest oturumlardan hesaplanır, `obek_hiz` ayrı döner.\n  Kartta en az 5'er geçerli serbest oturum olunca \"Öbek modunda X kel/dk, normalde\n  Y kel/dk\" satırı; daha azsa \"karşılaştırma için N bölüm daha\" notu.\n- Maliyet: bölüm başına bir Gemini çağrısı (çıktı ≈ girdi uzunluğu), yalnız öbek modu\n  açıkken okunan bölümlerde; varsayılan model, defterin ucuz modeliyle aynı ayar\n  yolundan seçilir (ücretli çağrı onayı CLAUDE.md'de var). `kullanim` kaydına\n  `asama=\"obek\"` olarak düşer, ayarlardaki harcama göstergesinde görünür.\n- Testler:\n  - `tests/test_obekler.py`: model çıktısı harf değiştirirse reddedilir ve kural\n    yedeği; 8 sözcükten uzun öbek reddi; `kaynak_sha256` değişince yeniden üretim;\n    zaman aşımı / hata → `kaynak: \"kural\"`; kitap silinince satır gider; `kural_obekleri`\n    tablo testleri (noktalama, bağlaç, -ken/-ınca/-ıp ekleri).\n  - `tests/js/okuma-hizi.test.mjs`: `obek` bayraklı oturum kişisel hıza girmez.\n  - `tests/tarayici/test_obek_modu.py`: alt çubuktaki \"Öbek\" düğmesi aç / kapa\n    (aria-pressed, ayara yazılır, yeniden açılışta korunur, konum kaymaz); oturum\n    ortasında mod değişince oturum karışık sayılır; öbek modu açıkken span'ler çizilir; terim\n    dokunuşu, arama vurgusu (öbek sınırını aşan eşleşme tek sayılır) ve çift dokunma\n    orijinali bozulmaz; öbekler geç gelince okuma konumu kaymaz; uç hata verince\n    kural öbekleriyle çizim.\n"}]} -->

<!-- autoplan-accepted:eng -->
- CEO bloğundaki "iki bölüm sonu geçerse akış duraklar, o bölümlerin süresi 0" kuralının YERİNE: bölüm başına kural; etkinliksiz tempo bölümü active_ms=0, gecerli=false; Adım A'da akış durmaz; Adım B'de art arda üç etkinliksiz bölüm sonunda, yoklamanın 20 sn zaman aşımından sonra duraklar; testli.
- CEO bloğundaki "sunucu 2× kişisel ortancadan hızlı serbest oturumu dışlar" kuralının tanımı: son 10 geçerli serbest oturumun ortancası, 2 katı üstü atılır, kalanların ortancası; n < 3 süzgeçsiz; testli.
- CEO bloğundaki "seviye çevrimi sınır içinde eski hızdan %10'dan fazla sapmaz" testinin YERİNE: çevrim ilk tempo başlangıcında tarayıcıda gerçek ölçüyle (eskiPxSn × 60 × harf ÷ yükseklik), Playwright ile çevrim öncesi ve sonrası px/sn eşitliği testi.
- reading_speed: oturum_id (UNIQUE, tekrar gönderim günceller), book_slug sütunu (resolve_slug), sunucu valid'i yeniden hesaplar; pydantic: words 0..chars, slug/url ≤ 2000, oturum_id deseni; testli.
- Bitiş bottom <= innerHeight; atlama (+0,2 oran, scrollToChapterRatio ve bölüm içi arama kancası) oturumu geçersiz yapar; sekme gizlenince keepalive gönderim; oturum günü bitiş günü; testli.
- ilk_hafta = ilk 5 geçerli serbest oturum; degisim 10 oturumdan azsa null; testli.
- Ölçüm bölümünde tempo önceki bölüm sonunda kapanır; okuma çizgisi örtüsü pointer-events: none; HTML bölümde harf 0 → geçersiz + yedek hız; testli.
- Mevcut testler güncellenir: tests/js/alt-cubuk.test.mjs, tests/js/oto-kaydir-yardimci.test.mjs, tests/tarayici/test_oto_kaydir.py.
- §7 öbek modu (kullanıcı kararı): Gemini öbekleri, bayt eşitliği denetimi ve kural yedeği, obekler tablosu (kaynak_sha256), GET /api/chapter/obekler, renderParagraphs tek çizim noktası ve geç gelen öbekte konum korunur, arama vurgusu öbek sınırını aşabilir, alt çubukta "Öbek" aç / kapa düğmesi (aria-pressed, obekModu ayarına kalıcı, iki yönde konum korunur; oturum ortasında değişirse oturum karışık sayılır), obek bayraklı ölçüm ve kartta karşılaştırma; testli (test_obekler.py, okuma-hizi.test.mjs, tarayici/test_obek_modu.py).
- Öbek yeniden çizim bütçesi 50 ms, Playwright performance.now() ile ölçülür.
<!-- /autoplan-accepted:eng -->

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| 1 | CEO | Kip SELECTIVE EXPANSION | Mechanical | autoplan kuralı | yeni yetenek | diğer kipler |
| 2 | CEO | Yaklaşım A + iki adımlı teslim | Taste | P1+P3 | bütünlük korunur, risk ve başlangıç çizgisi düzelir | tek seferde teslim |
| 3 | CEO | Ölçüm bölüm bazında | Mechanical | P5 | kaydırma konumu okunan satırı göstermez | kaydırma örnekleri |
| 4 | CEO | bugun_dk eklendi | Mechanical | P2 | aynı veri, S emek | — |
| 5 | CEO | Gemini anlama soruları ertelendi | Taste | P3 | çeviri hattına dokunur (3-5 dosya), M emek | ilk sürüme alma |
| 6 | CEO | Öz bildirim ara önlemi (iki Rahattı) | Mechanical | P1 | tek yöne itmeyi önler | tek yanıtla artış |
| 7 | CEO | Masadaki telefon kuralı | Mechanical | P1 | bugun_dk şişmesin | sınırsız tempo süresi |
| 8 | CEO | Ölçüm bölümü + tempo çizgisi | Mechanical | P1 | aktarım ölçülmezse etki bilinemez | yalnız serbest ölçüm |
| 9 | CEO | Sınırlar 700-4500 / 400-5000 | Mechanical | P1 | yavaş okuru zorlamaz, göz gezdirmeyi dışlar | 1500-4500 / 400-7200 |
| 10 | CEO | Hacim kaldıracı TODO'ya | Mechanical | P3 | blast radius dışı | plana alma |
| 11 | CEO | TTS NOT in scope | Mechanical | P3 | ayrı ürün kararı | — |
| 12 | CEO | Sıfıra bölme koruması | Mechanical | P1 | NaN hız akışı durdurur | — |
| 13 | CEO | ResizeObserver yalnız aktif bölüm | Mechanical | P3 | sonsuz akışta maliyet | her bölüm |
| 14 | Eng | Masadaki telefon kuralı bölüm başına, Adım A'da duraklatma yok | Mechanical | P5 | geriye dönük düzeltme UNIQUE ile çelişiyordu; mevcut özellik bozulmasın | geriye dönük kural |
| 15 | Eng | Seviye çevrimi gerçek ölçüyle | Mechanical | P1 | yorumdaki varsayım telefonda %50-75 sapıyor | sabit formül |
| 16 | Eng | oturum_id anahtarı | Mechanical | P5 | yeniden okuma ve yarım ziyaret ezilmesin | UNIQUE(day,url,mode) |
| 17 | Eng | Bitiş bottom<=innerHeight, atlama tespiti | Mechanical | P1 | son bölüm ve atlama ölçümü bozuyordu | oran 0,95 |
| 18 | Eng | book_slug sütunu, şema döngüsüne güven | Mechanical | P4 | library.py:421 zaten siliyor | elle satır |
| 19 | Eng | ilk_hafta = ilk 5 oturum | Mechanical | P1 | takvim penceresi kilitlenebiliyordu | 7 gün |
| 20 | Eng | Sunucu valid'i yeniden hesaplar | Mechanical | P1 | güven sınırı | istemciye güven |
| 21 | Eng | L1 ve L6 reddi | Mechanical | P3 | telefon ağırlıklı, zararsız | — |
| 22 | Eng | Öbek modülü ayrı (ortak yardımcı yok) | Mechanical | P5 | davranışlar farklı | ozet_zinciri ile birleştirme |
| 23 | Kullanıcı | Öbek modu: Gemini öbekleri (deneme) | Kullanıcı kararı | — | AskUserQuestion yanıtı 2026-11-08 | kural tabanlı, yalnız tempo vurgusu, ekleme yok |
| 24 | Kullanıcı | Öbek modu okuyucudan aç / kapa | Kullanıcı kararı | — | "bu bir mod gibi açılır ve kapatılır olmalı" | yalnız ayarlar sayfasında anahtar |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` (via /autoplan) | Scope & strategy | 1 | ISSUES OPEN | 6 proposals, 2 accepted, 2 deferred; 9 native findings resolved; 1 taste choice at gate |
| Outside Review | codex (plan-review) | Independent 2nd opinion | 2 | unavailable | model `gpt-6-astra` not supported on this ChatGPT account; no completed external review |
| Eng Review | `/plan-eng-review` (via /autoplan) | Architecture & tests (required) | 1 | ISSUES OPEN | 21 issues, 0 critical gaps; all accepted into plan except L1, L6 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | scope scan found no UI scope |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | skipped | false-positive term match (`sdk` = sözcük/dk); against the skill rule, flagged |

- **OUTSIDE COVERAGE:** codex, ceo + eng, unavailable (model_not_found), no completed external review; design and dx skipped.
- **VERDICT:** No review CLEAR yet; plan ready for owner approval. eng review required (issues open are accepted plan changes, no critical gaps).

NO UNRESOLVED DECISIONS
