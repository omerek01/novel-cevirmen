# DURUM — ne yapıldı, ne kaldı

> Bu dosya projenin **tek durum panosu**. Her dilim bitip main'e girince buradan
> güncellenir. "Nerede kaldık?" sorusunun cevabı hep burada.
> Son güncelleme: 2026-08-18 · SW kabuk **v66** · Testler: **290 geçiyor**

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
| 8 | **Manga çevirisi (yerel motor)** | 🔨 **KODLANDI** (dal `dilim-8-manga`) | Yerel manga-image-translator: inpaint ile temiz silme + düzgün dizgi, KOTASIZ; tüm-bölüm batch + şerit dilimleme (akan çeviri); **sonsuz devam** (bölüm sonunda site'den sonrakini çeker). Telefon QA bekliyor. |
| 9 | **Anasayfa tür-rafları + UI cilası** | 🔨 **KODLANDI** (dal `dilim-8-manga`) | Noveller/Mangalar/Kitaplar ayrı raflarda; emoji→SVG ikon, focus-visible, hover, reduced-motion. Sıcak-editoryal kimlik korundu. |
| 10 | **Çevrimdışı sözlük + ek-duyarlı çeviri** | 🔨 **KODLANDI** | Sözlüğe sunucu kapalıyken de kelime eklenir (yerel kuyruk → bağlanınca senkron); sözlük karşılığı komşu kelimeye sızmaz (`Tier→Kademe` varken `level` yine "seviye"); karşılıklar Türkçe ekini doğru alır. |
| 11 | ~~Türkçe seslendirme (TTS)~~ | ❌ **KALDIRILDI** | Kullanıcı kararı (2026-08-16). Kodlanmıştı; çevrimdışı indirmeyi bölüm başına dakikalara çıkardığı için tümden söküldü. |
| 15 | **Bölüm künyesi (motor + eklenen terimler)** | 🔨 **KODLANDI** | Bölüm sonunda dokununca açılan rozet: hangi motor çevirdi, sözlüğe ne eklendi. Eski bölümlerde rozet çıkmaz. |
| 14 | **Özel ad algılama (TÜM özel adlar)** | 🔨 **KODLANDI** | Karakter dışı her özel ad (yer, lonca, eşya, beceri, unvan, ırk, sistem terimi) Türkçe karşılığıyla sözlüğe otomatik eklenir; İngilizce kalan tek sınıf kişi adlarıdır. Kullanıcı kaydı ezilmez. |
| 13 | ~~İkinci çeviri motoru (Claude CLI)~~ | ❌ **KALDIRILDI** | Kullanıcı kararı (2026-08-16, aynı gün). Kodlanmıştı; Gemini'nin ~2,5 katı yavaş olduğu ve tek-sıra kapısı okumayı beklettiği için tümden söküldü. Ölçümler aşağıda. |
| 16 | **Sözlük İngilizce çakılması + sonsuz okuma anahtarı** | 🔨 **KODLANDI** | `detected_names` süzgeci (karakter dışı ad artık İngilizce çakılmaz), sonsuz okuma ayarlardan açılıp kapanır, akış devamı zincir KOPUNCA bölüm listesine düşer (çok-siteli/çevrimdışı okuma). Eski kayıtlar için `scripts/sozluk_gozden_gecir.py`. |
| 12 | **Çeviri kalitesi turu** | 🔨 **KODLANDI** | TEK kalite-öncelikli model zinciri (3.7-flash → 3.6-flash → 3.5-flash → 3.5-flash-lite; kota bitince bir alta iner, okuma durmaz), bölümler arası bağlam, kitap başına üslup notu, parça boyutu 1600→2800, deyim kuralı. Gerçek bölümlerle ölçüldü. |

**Ayrıca:** Çeviri modeli yalnız `gemini-3.1-flash-lite` (2.5 yedekleri kaldırıldı, kullanıcı kararı).

## Sözlük İngilizce çakılması + sonsuz okuma anahtarı + liste-tabanlı devam — 2026-08-18

Üç kullanıcı şikayeti, üç ayrı kök neden.

### 1) "Karakter adları harici Türkçe eklesin dedim, hep İngilizce ekliyor"
Kural doğruydu, kutu yanlıştı: model karakter OLMAYAN adları düzenli olarak
`detected_names` kutusuna sızdırıyor, oraya düşen her ad `merge_names` ile sözlüğe
`X -> X` diye çakılıyordu. Sözlük prompt'ta KURAL olduğu için o ad bir daha asla
Türkçeleşmiyordu. Ölçüm (kullanıcının DB'si): `reincarnation-…` kitabında 201 kaydın
**173'ü** İngilizce; içlerinde `Blackwater Guild`, `Star-Moon Kingdom`,
`Ancient Rock City`, `Hell Tanks` — hiçbiri karakter değil. Dahası
`Kızıl Alev Kalesi -> Kızıl Alev Kalesi` gibi TÜRKÇE yazımlar da bu kutuya girmişti.

| Katman | Ne yapıldı |
|---|---|
| `translate.ayikla_karakter_adlari` | Üç eleme: ad `detected_terms`'te de varsa Türkçe kazanır · Türkçe harf içeren ad İngilizce sayılmaz · ad ÇEVİRİ metninde aynen geçmiyorsa (model onu Türkçeleştirmiş demektir) kaydedilmez. Karşılaştırma `fold_term` üzerinden → "Nephis'in", "HanLi" adı elemez. |
| `pipeline._sozluge_isle` | SIRA düzeltildi: önce `merge_terms`, sonra `merge_names`. INSERT OR IGNORE'da ilk yazan kazanır; names önce koştuğu için İngilizce kayıt aynı yanıttaki Türkçe karşılığı bastırıyordu. |
| `pipeline._finalize_cached` | Önbellek isabetinde de aynı süzgeç: eski satırların HAM `detected_names`'i bölüm her açıldığında sözlüğü yeniden kirletiyordu. |
| `SYSTEM_INSTRUCTION` | detected_names maddesi sertleşti: kişi değilse oraya yazma, tereddütte terms'e yaz, buraya Türkçe kelime koyma. |

**Eski kayıtlar** ileriye dönük süzgeçle temizlenmez (sözlükte durdukça kural olmayı
sürdürürler) → `scripts/sozluk_gozden_gecir.py`: İngilizce korunan kayıtları
`translate.classify_terms` ile toplu sınıflandırır, VARSAYILAN KURU çalıştırmadır,
`--uygula` ile yazar. Model tereddütte "karakter" demeye zorlanır (yanlış
Türkçeleştirme karakterin adını kitap boyunca bozar). Kuru ölçüm: Shadow Slave 20
kayıttan 2'si, `reincarnation-…` 167 kayıttan 58'i Türkçeleşecek.

### 2) Sonsuz okuma artık bir anahtar
Ayarlar → **Sonsuz okuma: Açık / Kapalı** (`settings.infinite`, varsayılan açık).
Kapalıyken alt gözlemci HİÇ kurulmaz; bölüm sonunda **"SONRAKİ BÖLÜM →"** düğmesi
çıkar ve bölüm akışa eklenmek yerine TEMİZ sayfa olarak açılır (`navigate(..., replace)`
→ geri tuşu bölüm bölüm geri sarmaz). Manga'nın site'den sonraki bölümü çekmesi de
aynı anahtara bağlı. Anahtar okuyucu açıkken çevrilebilir: `refreshStreamEnd()`
gözlemciyi ve bitiş kartını yerinde yeniden kurar.

### 3) Akış devamı artık zincire mahkûm değil
Şikayet: kitabın devamı başka bir siteden çevrildiğinde, **indirilmiş** bölümler
dururken akış duruyor ve bölüm listesinden elle geçmek gerekiyordu. Sebep: devam
YALNIZ `next_url` zincirini takip ediyordu; bölüm 100'ün next'i A sitesinin hiç
çevrilmemiş 101'ini gösterirken fiilen indirilmiş 101 B sitesinden gelmişti.
Çevrimdışıyken zincir ölür, liste yaşar.

`pickNextTarget(last)`: zincirin next'i o kitapta ÇEVRİLMEMİŞSE ve listede sıradaki
bölüm varsa **liste kazanır**; aksi halde zincir (web'den ilerleyen okuma bozulmaz).
Liste `ensureChapterList(slug)` ile çekilir, `loadChapter` sonunda ısıtılır → SW
önbelleğine girer ve telefon çevrimdışıyken de devam eder. Altı senaryo node ile
doğrulandı (zincir listede / zincir çevrilmemiş / liste sonu / zincir yok / son bölüm
/ liste yok).

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

## Manga SONSUZ DEVAM (dal `dilim-8-manga`)
Novel sonsuz okumanın manga karşılığı: bölümün son sayfasına gelince site'deki **sonraki bölüm**
otomatik çekilir, dilimlenir, zincire eklenir, akarak çevrilir — kesintisiz. `manga_fetch` sayfaların
yanında sonraki-bölüm URL'ini de çıkarır (prev/next nav'dan "next"; gerçek asurascans'ta ch1→ch2
doğrulandı); `books.manga_source_url/manga_next_url` saklar; `POST /api/manga/continue` çeker+ekler;
okuyucu zincir sonunda otomatik çağırır. Batch **artımlı** (cache'li sayfayı atlar → yalnız yeni bölüm çevrilir).

## Anasayfa tür-rafları + UI cilası (dal `dilim-8-manga`)
Kitaplar türe göre **ayrı raflarda**: Noveller / Mangalar / Kitaplar (PDF-EPUB). Tür slug/şemadan
türetilir (`bookKind`, backend'e sütun yok); boş tür rafı çizilmez; tek tür varsa başlık gizli.
UI cilası (ui-ux-pro-max + frontend-design skill kuralları, mevcut sade-editoryal dilde): emoji→SVG
ikon, `:focus-visible` halka, masaüstü hover (sırt raftan kalkar), `prefers-reduced-motion`, scroll-snap.
Sıcak-kitaplık kimliği (sırt metaforu, 3 tema, kalın tipografi) korundu. `.claude/` skill'leri gitignore.

## Bölüm künyesi: motor + sözlüğe eklenenler — 2026-08-16 (5. tur)
İki şey görünmezdi: hangi motorun çevirdiği (Claude kotası dolunca sessizce Gemini'ye
düşülüyor) ve otomatik sözlük eklemesinin ne yaptığı. İkincisi hatalı karşılığı kalıcı
kılabiliyor (`Ore Empire → Maden İmparatorluğu`; doğrusu `Ork İmparatorluğu` — 8. tura
bak), o yüzden görünürlük şart.

**Ne eklendi:** `chapters.engine` + `chapters.added_terms` (JSON) sütunları; okuyucuda bölüm
sonunda **dokununca açılan rozet** — motor adı (`CLAUDE`/`GEMINI`) ve o bölümde sözlüğe
eklenen terimler (`Lightshadow City → Işıkgölge Şehri` / `Zero Wing (İngilizce korundu)`).
`glossary.merge_terms` artık FİİLEN eklenenleri döndürüyor; `_sozluge_isle` bunları
birleştirip künyeye koyuyor.

**İki tuzak, ikisi de teste bağlandı:**
1. Künye `save_chapter`'da `COALESCE(excluded.x, x)` ile yazılır — künye taşımayan bir
   payload (görsel içerik yolu) aynı satırı güncelleyince mevcut motor bilgisi NULL'a
   düşmesin. Aynı E-16 sınıfı hata, farklı sütunlar.
2. Rozet `renderParagraphs`/`renderHtmlContent` **sonunda** çizilir. `buildChapterEntry`
   içinde eklenseydi bölüm içi ilk aramada sessizce kaybolurdu (iki render de article'ı
   `.chapter-sep` dışında temizleyip yeniden kuruyor).

**Sözlüğe işleme uçuşun içine taşındı** (`_do_fetch_translate_save`): eskiden
`get_or_translate` içindeydi, orada kalsaydı tek-uçuşa KATILAN ikinci çağıran hep boş liste
görürdü (ilk çağıran zaten eklemiş olur).

**Uçtan uca doğrulandı:** bölüm 1877 yeni kodla çevrildi → `engine: 'claude'` (bu oturumda
ilk kez motor kesin olarak görüldü — Claude gerçekten çeviriyor). Aynı bölüm önbellekten
tekrar istendiğinde künye korundu (`cached: True · engine: 'claude'`). Eski bölümler
(1872-1876) `NULL` → rozet çizilmiyor, hata da vermiyor. 13 yeni test.

## Tek zincir, kalite öncelikli — 2026-08-17 (12. tur)
7. turdaki iki-zincir ayrımı (ucuz okuma / kaliteli yeniden-çevir) **aynı gün kaldırıldı**
(kullanıcı kararı). Sebep somut: okumanın gövdesi prefetch'ten geliyor, yani ucuz zincir
"yalnız arka plan" değil çevirinin ÇOĞUNU belirliyordu; kullanıcı bunu 10. turdaki deyim
hatasında fark etti.

**Tek zincir, her yerde aynı:**

`gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-3.5-flash-lite`

Kota dolunca (404/429) beklemeden bir alta iner, 500/503'te aynı modelde geri-çekilmeli
tekrar dener. Son halka flash-lite: en dayanıklısı, zincir tükenmesin diye orada.

**Kapsam:** okuma, prefetch, toplu çeviri, "yeniden çevir", içe aktarılan sayfa çevirisi
(`import_translate` zaten `DEFAULT_MODELS` kullanıyordu) ve sözlük terim önerisi
(`suggest_term`). `REFRESH_MODELS` sabiti SİLİNDİ; `refresh` bayrağının pipeline'a taşınması
da geri alındı — `refresh` yeniden yalnız "önbelleği yok say" demek. Bir test sabitin geri
gelmesini engelliyor (`test_ikinci_zincir_sabiti_kalmadi`).

**Kapsam DIŞI kaldı — manga motoru.** `manga_engine.py` harici araca tek bir `GEMINI_MODEL`
env'i geçiyor, yedek zinciri KABUL ETMİYOR; üstelik hâlâ zincirde bulunmayan eski bir modele
sabitli (`gemini-3.1-flash-lite`). Zincirin başına çekilirse sayfa başına 1 çağrı yapan batch
işleri 3.7'nin dar kotasını hızla bitirir ve düşecek halka olmadığı için manga çevirisi durur.
Karar kullanıcıya bırakıldı. Testler: **269 geçiyor**.

## Künyede model adı — 2026-08-17 (11. tur)
10. turdaki deyim hatası tartışılırken "bunu hangi model çevirdi" sorusu **tahminle**
cevaplanmak zorunda kaldı: künye yalnız `engine` taşıyordu, o da hep `gemini` yazıyor.
Zincirin hangi halkasının çevirdiği (3.7 mi flash-lite mı) çalışma zamanında biliniyor
ama kaydedilmeden atılıyordu. Artık kaydediliyor.

| Katman | Değişiklik |
|---|---|
| `translate._generate_with_fallback` | `(response, model)` döndürür — fiilen ÇEVİREN halka, zincirin ilki değil |
| `translate._translate_chunk` | parça sonucuna `model` ekler (parça başına ayrı: uzun bölümde kota bitip alt halkaya düşülebiliyor) |
| `translate.translate_chapter` | kullanılan modelleri sırayla toplar, tekrarı eler → `"model"`; birden fazlaysa `" + "` ile |
| `cache` | yeni `chapters.model` sütunu (`ensure_column`, idempotent), `COALESCE` ile korunur |
| `pipeline` | payload'a `model` |
| `app.js` | rozette `[GEMINI] ile çevrildi · 3.7-flash` (`gemini-` öneki kırpılır, motor rozette zaten yazıyor) |

**Gerçek DB'de doğrulandı:** migration çalıştı, 341 satır korundu, hepsinde `model` NULL
(eski bölümlerde bu bilgi hiç üretilmemişti) → rozet o bölümlerde yalnız motoru gösterir.
`engine` alanına dokunulmadı; `claude` satırları hâlâ doğru etiketleniyor. SW kabuk **v65**.
Testler: **268 geçiyor**.

## Deyimler artık kelime kelime çevrilmiyor — 2026-08-17 (10. tur)
Kullanıcı bildirimi: bölüm 1862'de `turn the tables on them` → **"masaları onlara karşı
çevirecekti"**. Doğrusu "durumu tersine çevirmek". Prompt'ta "akıcı, doğal, birebir değil,
anlamı koru" maddesi vardı ama kalıpları tutmuyordu; deyim AYRI ve ÖRNEKLİ bir madde oldu:
yanlış/doğru çiftleri (`turn the tables`, `break the ice`, `in his shoes`, `call it a day`,
`the ball is in your court`) + modele bir öz-denetim ÖLÇÜTÜ ("bağlamı bilmeyen biri 'bu ne
demek şimdi' diyorsa birebir çevirmişsindir, o cümleyi anlamıyla yeniden yaz").

**Yaygınlık ölçüldü:** 341 çevrilmiş bölüm, bilinen 12 İngilizce deyimin birebir Türkçe izi
tarandı → **tek vaka**, o da bildirilen bölüm. Yani nadir; genel kural çoğu zaman tutuyor,
kalıplarda ara sıra kaçırıyor.

**Muhtemel bağlantı (kesin DEĞİL):** 1862 bugün, 7. turda `gemini-3.5-flash-lite` zincirin
başına alındıktan sonra çevrildi ve flash-lite ölçümde zaten "üslubu en zayıf halka" diye
işaretliydi. Kesin konuşulamıyor çünkü **künye model adını saklamıyor** (`chapters.engine`
hep `gemini`) — hangi halkanın çevirdiği geriye dönük bilinmiyor. Teşhis edilebilirlik için
künyeye fiilen kullanılan model adını yazmak SONRAYA aday.

**Mevcut bölümler için:** kural yalnız yeni çevirilerde geçerli. Bozuk bölüm sunucu yeniden
başlatıldıktan sonra "yeniden çevir" ile düzelir (o yol `REFRESH_MODELS` → `3.7-flash`
başta). Testler: **262 geçiyor**.

## Okurken seçip sözlüğe ekleme — 2026-08-17 (9. tur)
Sözlüğe terim eklemek için okumayı bırakıp sözlük ekranına gitmek gerekiyordu. Artık
okuyucuda metin seçilince kayan **"+ SÖZLÜĞE EKLE"** düğmesi çıkıyor; dokununca hızlı
ekleme modalı açılıyor.

**Neden kendi düğmemiz:** Android'in seçim menüsüne (Çevir / Kopyala / Paylaş) kendi
eylemimizi ekleyemeyiz — o tarayıcının menüsü, sayfaya kapalı. Native menü seçimin
ÜSTÜNDE durduğu için düğme ALTA konumlanıyor (üste konsa menünün altında kalıp
dokunulamazdı); ekranın dibindeki seçimde üste alınıyor.

**Karşılığı sistem belirliyor** (kullanıcı isteği): yeni uç
`POST /api/book/{slug}/glossary/suggest` → `translate.suggest_term`, otomatik algılamayla
AYNI kuralı uyguluyor — **karakter adı → İngilizce kalır** (`X -> X`), **başka her özel ad
→ Türkçe karşılık**. Terimin geçtiği cümle bağlam olarak gönderiliyor: aynı sözcük bir
kitapta kişi adı, başkasında yer adı olabilir (`Rain`). Model "karakter" deyip Türkçe bir
karşılık döndürürse karşılık zorla adın kendisine çekiliyor.

**Öneri ONAYA sunuluyor, doğrudan yazılmıyor:** sözlük prompt'ta KURALdır, model onu
birebir uygular — yanlış bir karşılık kitap boyunca sabitlenirdi. Terim zaten kayıtlıysa
öneri istenmiyor, bunun yerine mevcut karşılık gösteriliyor (kayıt INSERT OR REPLACE,
kullanıcı üzerine yazdığını bilerek yazsın).

Seçim İngilizce orijinal bloğundan (`.source-line`) gelirse KAYNAK alanı, Türkçe
paragraftan gelirse KARŞILIK alanı doluyor. Kaydetme mevcut çevrimdışı kuyruğu kullanıyor
(`saveTerm` → sunucu kapalıysa telefonda bekler). Seçim 8 kelimeyi aşarsa düğme çıkmıyor
(sözlük terim eşlemesidir, cümle çevirisi değil). SW kabuk **v64**. Testler: **261 geçiyor**.

## Sözlük yazım varyantını artık tanıyor — 2026-08-17 (8. tur)
Kullanıcı bildirimi: "sözlükte `Ore Empire` kayıtlı ama metinde başka türlü yazılınca
algılamıyor." Doğrulandı — kayıp **süzme aşamasındaydı**. Sözlük 40 terimi geçince
`_relevant_glossary` yalnız o parçada geçen terimleri prompt'a koyuyor; eşleştirme
birebir yazım üzerindeydi, dolayısıyla farklı yazılan ad **sözlükte olmasına rağmen
prompt'a hiç girmiyordu** ve model onu her bölümde yeniden çeviriyordu.

Üç yerde birden düzeltildi:

| Yer | Önce | Sonra |
|---|---|---|
| `translate._term_regex` | `re.escape(terim)` birebir | Terim kelime PARÇALARINA ayrılır, aralarına esnek ayırıcı `[\s\-_'’]*`; tek parçalı kayıt CamelCase'den bölünür (`OreEmpire` → `Ore`+`Empire`, kayıpsızsa) |
| `translate._relevant_glossary` ön elemesi | `terim.lower() in metin.lower()` | `fold_term` üzerinden (boşluk/tire/kesme atılmış hâl) — terim artık regex'e VARMADAN elenmiyor |
| `glossary.merge_terms` | "kayıtlı mı" birebir | `fold_term` ile: varyant ikinci satır AÇMAZ (karşılıklar ayrışmasın) |

`fold_term` yalnız KARŞILAŞTIRMA anahtarıdır; saklanan yazım `normalize_source`
çıktısıdır (kullanıcı sözlük ekranında okunaklı hâli görmeli).

**Gerçek veriyle ölçüldü** (7 kitap, kaynağı olan 219 bölüm, gerçek sözlükler):
süzülen terim 3014 → **3018**. Kazanç 3 terim ama kalıbı öğretici — hiçbiri bitişik
yazım değil, hepsi **kesme işareti** varyantı: aynı ad metinde bazen düz `'` bazen
kıvrık `’` ile geçiyor (`Heaven's Burial` ~ `Heaven’s Burial`, `Kingdom's Sword`,
`King's Return`), sözlükteki kayıt hangisiyse öteki yazımın geçtiği bölümlerde terim
kayboluyordu. Bitişik-yazım (`OreEmpire`) vakası bu 219 bölümde hiç görülmedi;
desen onu da kapsıyor ama ölçülen fayda kesme işaretinden geldi.

**Ayrı vaka — `Ore` / `Orc` (aynı gün, veri düzeltmesi):** kullanıcı aynı varlığın bazı
bölümlerde `Orc Empire`, bazılarında `Ore Empire` yazıldığını bildirdi. Ölçüm (171 bölüm):
`Orc Empire` 157 geçiş / 29 bölüm, `Ore Empire` 60 geçiş / 19 bölüm ve **hiçbir bölümde
ikisi birlikte geçmiyor** — kaynak sitenin bölümleri farklı çevirmen gruplarından derlemesinin
izi. Doğrusu `Orc` (ork ırkı: `Orc King` 5, `orcs` 50); `ore` kelimesi romanda ayrıca gerçek
anlamıyla da geçiyor (`ore vein` 24, madencilik teması) — bu yüzden `fold_term` bunları
BİRLEŞTİRMEZ ve birleştirmemeli, tek harf farkı gerçek bir anlam farkı olabilir.
Sözlükte iki hata vardı: karşılık yanlıştı (`Ore Empire → Maden İmparatorluğu`) ve
**`Orc Empire` kaydı hiç yoktu**, yani 157 geçişin olduğu 29 bölümde sözlük hiç devreye
girmemişti. Dört kayıt elle düzeltildi (her iki yazım → aynı karşılık):
`Orc/Ore Empire → Ork İmparatorluğu`, `Orc/Ore Capital City → Ork Başkenti`.
**Sonraya:** sözlüğe yeni terim eklenirken mevcut bir terime tek harf uzaklıktaysa künyede
uyarı (otomatik birleştirme DEĞİL — `ore`/`orc` örneği tam da neden birleştirilmemesi
gerektiğini gösteriyor).

**Ölçüm tuzağı (not):** ilk ölçüm 48 terimlik sahte bir kazanç gösterdi — kıyaslanan
"eski" fonksiyona `GLOSSARY_FILTER_MIN` eşiği konmamıştı, küçük sözlüklü kitapta yeni
fonksiyon sözlüğün tamamını döndürürken eski süzüyor görünüyordu. Bu tür kıyasta eşik
kontrolü kopyalanmalı. Testler: **252 geçiyor**.

## ~~İki model zinciri: hızlı okuma / kaliteli yeniden-çeviri~~ — 2026-08-17 (7. tur) → **AYNI GÜN GERİ ALINDI**
> **Tarihçe.** Aşağıdaki iki-zincir ayrımı 12. turda kaldırıldı; tek ve kalite öncelikli
> zincire dönüldü (yukarı bak). `REFRESH_MODELS` artık YOK. Not, neyin denendiğini ve
> hangi gerekçeyle düşürüldüğünü göstermek için duruyor.

Tek zincir vardı ve KALİTE öncelikliydi (`3.6-flash` → `3.5-flash` → `3.5-flash-lite`).
Sorun: akışın gövdesi (okuma + prefetch + toplu çeviri) 3.6'nın ~25 istek/günlük ücretsiz
kotasını her gün erkenden yakıyordu. Kullanıcı kararıyla zincir ikiye ayrıldı:

| Yol | Sabit | Zincir | Gerekçe |
|---|---|---|---|
| Okuma / prefetch / toplu çeviri | `DEFAULT_MODELS` | `3.5-flash-lite` → `3.6-flash` → `3.5-flash` | En hızlı + en geniş kotalı halka önce; gövde tıkanmaz, 3.6 kotası harcanmadan durur |
| **Yeniden çevir** (`refresh=True`) | `REFRESH_MODELS` | **`3.7-flash`** → `3.6-flash` → `3.5-flash` → `3.5-flash-lite` | Kullanıcı bu çeviriyi beğenmedi → en iyi modelden başla; bir bölümlük maliyet |

`refresh` bayrağı artık `get_or_translate`'te kalmıyor, uçuşa (`_fetch_translate_save` →
`_do_fetch_translate_save`) taşınıp model zincirini seçiyor. Uçuşu AÇAN çağrının bayrağı
geçerli — sonradan katılan uçan çeviriyi bekler, modeli değiştiremez (nadir yarış, zararsız:
katılan yine taze çeviri alır).

**3.7 riski açıkça kabul edildi:** 2026-08-16 ölçümünde uzun isteklerde ısrarla 503 verdi,
kalitesi ÖLÇÜLEMEDİ. Servis hâlâ tökezliyorsa yeniden-çevir isteği parça başına birkaç
saniye boşa bekleyip (`RETRY_CODES` üstel geri-çekilme) 3.6'ya iner — çeviri yine gelir,
yalnız yavaşlar. Rozette hangi motorun çevirdiği görünmez (künye `engine` alanı hep
`gemini` yazar, model adını taşımaz); 3.7 gerçekten çalışıyor mu ancak süre/kaliteden
anlaşılır. Kapsam dışı: içe aktarılan EPUB/PDF sayfa çevirisi (`import_translate.py`) ve
manga motoru kendi model seçimlerini sürdürüyor. Testler: **241 geçiyor**.

## Sözlük artık TÜM özel adları kapsıyor — 2026-08-17 (6. tur)
4. turda açılan kutu üç sınıfla sınırlıydı (karakter / lonca / yer). **Eşya, beceri,
büyü, unvan, ırk, adlandırılmış canavar ve sistem terimleri hiçbir sınıfa girmediği
için sözlüğe hiç yazılmıyordu** — model bunları çeviride Türkçeleştiriyor ama karşılığı
kaydedilmediğinden her bölümde yeniden karar veriyordu. Gerçek bulgu: Shadow Slave 30.
bölümde `Puppeteer's Shroud` alınmamıştı.

**İki sınıf, iki davranış** (`pipeline._sozluge_isle`):

| Sınıf | JSON alanı | Sözlükteki hâli | Örnek |
|---|---|---|---|
| Karakter | `detected_names` | İngilizce (`X -> X`) — İngilizce kalan TEK sınıf | `Shi Feng -> Shi Feng` |
| **Karakter dışı HER özel ad** | `detected_terms` | **Türkçe karşılık** | `Puppeteer's Shroud -> Kuklacının Örtüsü` |

`detected_guilds` + `detected_places` tek `detected_terms` eşlemesinde birleşti; prompt
sınıfları sayıyor ("yer, lonca, EŞYA, BECERİ, unvan, ırk, adlandırılmış canavar, sistem
terimi") ve bir ÖLÇÜT veriyor: büyük harfle başlayıp o dünyaya ait belirli bir şeyi
adlandıran her ifade girer, sıradan cins isim (`a sword`) girmez ama `the Sword of Dawn`
girer. `_parse_response` eski iki alanı da okumaya devam ediyor — model arada eski şemayı
üretiyor, düşürmek terimi sessizce kaybettirirdi.

**Kapsam:** yalnız BUNDAN SONRA çevrilen bölümlerde etkili. Zaten önbellekte olan bölümler
için terim geçmişe dönük eklenmez; istenirse bölüm yenilenmeli ya da terim sözlük
ekranından elle girilmeli. Testler: **237 geçiyor**.

## Özel adlar sözlüğe otomatik işleniyor — 2026-08-16 (4. tur)
> **Güncellendi:** aşağıdaki üç-sınıflı yapı 6. turda iki sınıfa genişletildi (yukarı bak).
> `detected_guilds`/`detected_places` alan adları artık `detected_terms`.
Daha önce tespit edilen yapısal boşluk kapatıldı: sözlüğe YALNIZ karakter isimleri
otomatik giriyordu, yer ve lonca adları hiç girmiyordu → model her bölümde yeniden karar
veriyor, aynı şehir bölümden bölüme başka çıkabiliyordu (uydurma "Işıkölge" böyle doğdu).

**Üç sınıf, iki davranış** (`pipeline._sozluge_isle`):

| Sınıf | Sözlükteki hâli | Örnek |
|---|---|---|
| Karakter | İngilizce (`X -> X`) — İngilizce kalan TEK sınıf | `Shi Feng -> Shi Feng` |
| **Lonca / klan / örgüt** | **Türkçe karşılık** | `Zero Wing -> Sıfır Kanat` |
| **Yer** | **Türkçe karşılık** | `Lightshadow City -> Işıkgölge Şehri` |

Model artık JSON'da `detected_guilds` ve `detected_places` alanlarını İngilizce → Türkçe
EŞLEME olarak döndürüyor; prompt'a "yer/lonca adını uydurma biçimde birleştirme" örneği
eklendi. Kullanıcının elle yazdığı karşılık her hâlükârda üstün (`INSERT OR IGNORE`).

**Lonca kuralı 5. turda tersine çevrildi** (2026-08-16): önce kurum adı sayılıp İngilizce
korunuyordu, kullanıcı kararıyla Türkçe'ye alındı. Tek istisna: lonca adının İÇİNDE geçen
kişi adı İngilizce kalır (`Wang Lin's Hall -> Wang Lin Salonu`). `detected_guilds` bu yüzden
listeden eşlemeye dönüştü — karşılıksız (düz liste) gelen bir yanıt artık ATILIR, çünkü
karşılığı bilinmeyen bir terimi sözlüğe yazmak sözlüğü kirletir.

**Gerçek bölümde doğrulandı** (1854, sözlük boş verilerek, iki motorda da): karakter 4,
lonca 6 (çeviride İngilizce durdukları teyit edildi), yer 8 — `Lightshadow City` artık
`Işıkgölge Şehri`. İki motorun yer karşılıkları farklı olabiliyor (`Crimson Flame Fortress`
→ Claude "Crimson Flame Kalesi", Gemini "Kızıl Alev Kalesi"); sözlük İLK kaydı sabitlediği
için kitap içinde tutarlılık yine de korunuyor.

**Bilinen kalıntı:** mevcut sözlükte 13 yer adı ve 5. tura kadar eklenmiş TÜM lonca adları
`X -> X` (İngilizce) olarak duruyor. `INSERT OR IGNORE` bunları ezmez, dolayısıyla o adlar
İngilizce kalmaya devam eder. Türkçeleştirilmeleri isteniyorsa kayıtların sözlük ekranından
elle silinmesi gerekir (sonraki okumada otomatik Türkçe karşılıkla geri gelirler).

## ~~İkinci çeviri motoru: Claude CLI~~ — 2026-08-16 (3. tur) → **AYNI GÜN KALDIRILDI**

> **Bu bölüm tarihçedir; anlatılan kod artık yok.** `claude_engine.py`, `resolve_engine`,
> `_engine_for` ve iki test dosyası silindi; `TRANSLATE_ENGINE` / `CLAUDE_*` env'leri
> kaldırıldı. Kaldırma gerekçesi ve ölçümü bölümün SONUNDA. Aşağıdaki tasarım notları,
> ileride benzer bir ikinci motor düşünülürse ne öğrenildiğini göstermek için duruyor.

Gemini'nin sınırı netleşince (3.6-flash kotası ~25 istek/gün, flash-lite üslubu zayıf)
kullanıcının mevcut Claude aboneliği ikinci motor olarak devreye alındı.

**Politika:** okuma yolu Claude, **toplu çeviri Gemini** (`pipeline._engine_for`). Gerekçe:
abonelik penceresi onlarca çağrıda dolar; 170 bölümlük bir kitabı taşıyamaz ve dolduğunda
kullanıcının o an okuduğu bölüm de Claude'suz kalırdı. Kalite, okunan tek bölüme harcanır.

**Mimari:** motor sınırı `_translate_chunk`. Prompt kurulumu (`_build_user_prompt`)
motor-BAĞIMSIZ — sözlük, üslup notu, bağlam, SON HATIRLATMA iki motorda birebir aynı gider.
`translate_chapter` dönüşüne `engine` alanı eklendi (fiilen kullanılan motor). Claude
düşerse (kota/oturum) **yapışkan düşüş**: kalan parçalar da Gemini'ye gider, okuma durmaz.

**Bayraklar ölçümle seçildi** — asıl bulgu önbellekte:

| Kombinasyon | Bağlam | Maliyet |
|---|---|---|
| bayraksız | ~35.000 token | $0.22 |
| `--disallowedTools` ile | ~11.800 token | $0.073 |
| `--tools "" --system-prompt-file` | 24.215 yazılır | $0.147 |
| **+ `--exclude-dynamic-system-prompt-sections`** | 24.215 **okunur** | **$0.0088** |

Son satır kritik: dinamik sistem-promptu bölümleri (her çağrıda değişen alanlar) prompt
önekini bozduğu için önbellek hiç tutmuyordu. Dışlanınca ardışık bölümler **16x** ucuza
geliyor. `--bare` ASLA kullanılmaz (OAuth okumaz, aboneliği kırar); `--setting-sources ""`
de kullanılmaz (stdout'u bozdu). Prompt **stdin**'den geçer → Windows argv sınırı sorunu yok,
parça boyutu iki motorda aynı (2800 kelime) kalır.

**Uçtan uca ölçüm** (bölüm 1854, 450 kelime, 194 terimlik sözlük): 25,7 sn, hizalama tam
(13→13 paragraf), sözlük ihlali yok, bozuk ek yok. Kalite Gemini 3.6-flash ile yarışıyor;
hız ondan yavaş (flash-lite 4,3 sn · 3.6-flash 14,7 sn · Claude 25,7 sn).

### Kaldırma — aynı gün, kullanıcı kararı

Kullanıcı okurken "aşırı yavaş" dedi; ölçüldü. Aynı 4200 kelimelik metin, aynı makine:

| Motor | Süre | Hız |
|---|---|---|
| Claude sonnet | 82,1 sn | ~299 krkt/sn |
| Claude haiku | 75,5 sn | ~303 krkt/sn |
| gemini-3.6-flash | 32,5 sn | ~868 krkt/sn |
| gemini-3.5-flash-lite | 18,5 sn | ~1706 krkt/sn |

Üç bulgu kararı verdi:

1. **Claude flash'ın ~2,5 katı yavaş** ve fark kalite farkını karşılamıyor.
2. **Model değiştirmek kurtarmıyor** — haiku ile sonnet pratikte aynı (75,5 / 82,1).
   Darboğaz model kademesi değil, CLI üzerinden çıktı üretim hızı; parça başına ~3 sn
   süreç doğumu da üstüne biniyor.
3. **`Semaphore(1)` okumayı bekletiyordu.** Tüm Claude çağrıları tek sıradan geçiyordu;
   Gemini yolunda böyle bir kapı yok. `CLAUDE_ALLOW_BULK=1` açıldığında prefetch ve toplu
   çeviri de o sıraya girdi ve canlı okuma isteği arkalarında kuyruğa düştü. Çekim
   tarafındaki `_FETCH_GATE` bu sorunu iki-öncelikli kapıyla çözmüştü; çeviri tarafında
   karşılığı hiç yazılmamıştı.

Bir de teşhis dersi çıktı: motor politikası "okuma yolu" diye tanımlanmıştı ama okunan
bölümlerin çoğu **prefetch**'ten geliyor (`background=True` → Claude yasak). Yani ilk gün
künyede Claude neredeyse hiç görünmedi, sebebi kurulum değil bu eşleşmezlikti.
Bu ders `CLAUDE.md`'de kritik-kararlar maddesi olarak duruyor.

## Model araştırması + sözlük sızıntısının kök nedeni — 2026-08-16 (2. tur)
Kullanıcı bulgusu ("Işıkölge" gibi uydurma kelimeler) araştırıldı; sebep modelden ÖNCE
prompt yapısındaydı.

**Kök neden.** Sözlük prompt'un BAŞINDA veriliyordu. 1500 kelimelik gerçek bir bölümde
model onu "unutup" korunması gereken 26 adın **23'ünü** Türkçeleştirdi (ölçüldü, 3 tur:
23 / 6 / 11 ihlal). Uydurma "Işıkölge" böyle doğdu. Çözüm: çevrilecek metnin ARDINDAN
kısa bir "SON HATIRLATMA" — aynen kalacak adlar orada tek tek sayılıyor. Ölçüm sonrası:
**4 turda da 0 ihlal.** Etki yakınlıktan geliyor; hatırlatma metnin önüne çekilirse kaybolur.

**Model karşılaştırması (gerçek bölüm metinleriyle, ücretsiz katman).**

| Model | Akıcılık | Güvenilirlik | Hız | Karar |
|---|---|---|---|---|
| `gemini-3.6-flash` | **en iyi** (doğal deyim, düzgün tırnak) | 5/5 ama **kota ~25 istek/gün** | 36 sn/bölüm | zincir başı |
| `gemini-3.5-flash` | iyi | 3/5 (503 yüksek talep) | orta | orta halka |
| `gemini-3.5-flash-lite` | zayıf (tekrar, bozuk kurgu) | 5/5 | **10 sn/bölüm** | son çare |
| `gemini-3.7-flash` | **ölçülemedi** | uzun isteklerde ısrarla 503 | — | dışarıda, sonra denenmeli |
| `gemini-3.1-pro-preview`, `gemini-pro-latest` | — | **429: ücretsiz katmanda YOK** | — | kullanılamaz |

Zincir: `3.6-flash → 3.5-flash → 3.5-flash-lite`. 3.6'nın kotası çok dar olduğu için alt
halkalar süsleme değil, günün çoğunda asıl taşıyıcıdır — bu yüzden flash-lite'ın sözlüğe
uyması (yukarıdaki düzeltme) kritikti.

**Ayrıca:** Türkçe ek/kaynaştırma kuralı prompt'ta yalnız SÖZLÜK maddesinin altındaydı,
`CORE_TERM_HINTS` sistem terimlerini kapsamıyordu — "farklı bir seviyeindeydi" oradan
çıkmıştı. Kural bağımsız maddeye taşındı, yanlış biçimler açıkça sayıldı.

**Not:** Google ücretsiz katmanın model-başına RPD tablosunu artık yayınlamıyor (AI Studio
> Rate limits'ten bakılıyor). Bu yüzden kota tahminine değil, 429'a dayanıklı zincire
güveniliyor.

## Çeviri kalitesi turu — 2026-08-16
Dört kaldıraç birlikte sevk edildi; hepsi gerçek bölümlerle ölçüldü (kota harcandı).

**1. Model zinciri.** `gemini-3.1-flash-lite` tek başınaydı; artık
`gemini-3.5-flash-lite` → `gemini-3.6-flash`. Sıra kaliteyi değil maliyeti yansıtır:
flash-lite'ın 500 RPD'si gün boyu yeter, kota dolunca (429) **beklemeden** 3.6-flash
devralır ve o bölümler daha da iyi çevrilir. Eskiden kota bitince "biraz sonra tekrar
deneyin" hatası dönüyordu — artık okuma durmuyor.

**2. Bölümler arası bağlam.** Parçalar arasında son cümleler zaten taşınıyordu ama
**bölüm sınırında bağlam sıfırlanıyordu**: sahnenin ortasında biten bir bölümün devamı
bağlamsız çevriliyordu. Artık önceki bölümün son ~160 kelimelik Türkçesi yeni bölümün ilk
parçasına bağlam olur (`cache.prev_translation`; zincir kopuksa bölüm numarasından düşer,
görsel bölümleri atlar). Ölçülen etki: bağlamsız çeviride "Fourth Uncle" İngilizce kalıp
isim listesine düşerken, bağlamlı çeviri önceki bölümün "Dördüncü Amca" karşılığını
sürdürdü.

**3. Kitap başına üslup notu.** Sözlük terim eşler, üslup ondan bağımsızdı ve bölümden
bölüme kayıyordu. `books.style_note` (600 karakter) her prompt'a girer; sözlük ekranında
katlanır kutu (`/api/book/{slug}/style`). Ölçülen etki belirgin: aynı paragraflar notlu
sürümde uzun kurgulu cümlelere, ağır sözcük seçimine ve resmi hitaba döndü.

**4. Parça boyutu.** `MAX_WORDS_PER_CHUNK` 1600 → **2800**; `max_output_tokens` artık
açıkça veriliyor (sessiz kesilme bozuk JSON'a, o da hizalama kaybına yol açıyordu).
Ölçüm: 3.493 kelimelik bölüm 3 parça yerine **2 parçada**, 21 sn'de, hizalama tam
(100→100 paragraf), kesilme yok. Daha az kopma noktası = bölüm içinde daha tutarlı üslup.

**Sonraya bırakıldı:** ikinci geçiş (redaksiyon) — kaliteyi artırır ama kotayı ikiye
katlar; yalnız "Yeniden çevir"e bağlanırsa mantıklı. Ayrıca kalite için A/B karşılaştırma
aracı yok; şu an değişikliğin etkisi elle okunarak değerlendiriliyor.

## Seslendirme (TTS) kaldırıldı — 2026-08-16
Kodlanmış ve doğrulanmış bir özellikti (edge-tts nöral sesler, karaoke vurgu, çevrimdışı dinleme),
ama **çevrimdışı indirmeyi kullanılamaz hale getirdiği için tümden söküldü** (kullanıcı kararı).

**Neden:** "Çevrimdışı indir" akışı her bölüm için ses manifesti çekiyor, "sesler de tamamlansın"
denince bölüm başına **~4 dakika** ses üretiyordu — 40 bölümlük bir kitap ~2,5 saat. Metin
indirmesi saniyeler sürerken toplam süreyi ses belirliyordu. Ses üretimi tarayıcı poll'una bağlı
olduğu için o ekranın da açık kalması gerekiyordu.

**Ne silindi:** `app/core/tts.py`, `tests/test_tts.py`, `/api/tts/*` uçları, `tts-bulk` iş tipi,
okuyucudaki dinleme çubuğu + ses ayarı, SW'nin `/api/tts` yönlendirmeleri, `edge-tts` bağımlılığı
(`requirements.txt` TTS öncesi haline döndü). Çevrimdışı indirme artık yalnız bölüm metnini çeker.

**Geri eklenecekse:** ses üretimi indirme akışından **tamamen ayrı** durmalı — "çevrimdışı indir"
hiçbir koşulda ses üretimini beklememeli. Üretilmiş MP3'ler `cache/media/<slug>/` altında kalmış
olabilir; diskte yer kaplıyorsa elle silinebilir.

## Bilinçle ertelenenler (ihtiyaç olunca)
- Okuma geçmişi listesi ekranı · Ayarlar'da "sistem" bloğu (son kontrol, bekleyen iş, cache boyutu)
- Kapak görseli çekme (og:image) · Tek "İçe Aktar" sihirbazı (otomatik tür algılama)
- EPUB/PDF **arayüz geliştirmeleri** (kullanıcı: "belki sonra") · LAN erişim koruması (token)
- Manga tam entegrasyonu · library/glossary'yi `db.connect()`'e taşıma

## Referans dokümanlar
- Onaylı plan + tasarım kararları: `~/.gstack/projects/novel-cevirmen/OMEREK-faz-sonraki-plan-design-20260718-000427.md`
- Mimari + kritik kararlar/tuzaklar: `CLAUDE.md`
- Tasarım gerekçesi: `TASARIM.md` · Eski TODO listesi: `TODOS.md` (bu dosya onun yerini alır)
