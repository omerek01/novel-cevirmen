# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Bu proje ile ilgili tüm kod, yorum ve döküman **Türkçe**dir; aynı dili sürdür.
> (Not: proje tesadüfen `gstack\` klasörü altında duruyor ama gstack ile ilgisi
> yoktur — global gstack talimatları buraya uygulanmaz.)

## Proje ne

Kişisel bir **web roman çeviri okuyucusu**. İngilizce web romanlarını (novelbin,
novelfull, freewebnovel, webnovel) Cloudflare arkasından çeker, **özel isimleri
bozmadan** Gemini ile Türkçe'ye çevirir ve telefon-öncelikli bir PWA okuyucuda
sunar. Backend bir Windows PC'de çalışır; telefondan Tailscale (`100.x.x.x`) veya
aynı Wi-Fi LAN üzerinden `:8000`'e bağlanılır. **Sadece kişisel kullanım** —
satma/yayınlama yok (yasal gri alan). Tasarım gerekçesi: `TASARIM.md`.

## Komutlar

Windows + `.venv` tabanlı. Kabuk PowerShell; Bash aracında yol `.venv/Scripts/...`.

```powershell
# Kurulum (bir kez)
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # KÖK requirements.txt kanonik
.\.venv\Scripts\python.exe -m playwright install chromium

# Çalıştırma — tam akış (CDP Chrome yardımcısı + sunucu, 3 erişim adresini basar)
start.bat
# Çalıştırma — sadece sunucu
.\.venv\Scripts\python.exe app\server.py      # uvicorn, 0.0.0.0:8000

# Test (kök dizinden; ağ/Playwright/Gemini çağırmaz, hepsi çevrimdışı ~2sn)
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests\test_api.py::test_books_empty   # tek test
```

Lint/format adımı **yok** (ruff/flake8/black yapılandırması yok). Kod kalitesi
elle sürdürülüyor. `pytest.ini`/`pyproject.toml` yok — testler `tests/conftest.py`
içindeki `sys.path` eklemesiyle çalışır.

## Mimari (büyük resim)

```
[Telefon/PWA]  ──GET /api/chapter?url=…──►  server.py (FastAPI)
                                               │
                                          pipeline.get_or_translate()   ◄── jobs.py (toplu) da AYNI yolu kullanır (DRY)
                                               │
                    cache HIT? ──evet──► anında dön (API'siz)
                                               │ hayır
                          fetch.py (Cloudflare'i aş, HTML ayıkla)
                                               │
                       translate.py (Gemini EN→TR, isim koru, parça+bağlam)
                                               │
                   cache.save + glossary.merge_names + library.upsert
```

**`app/server.py`** — FastAPI uygulaması + tüm HTTP endpoint'leri; giriş noktası
(`__main__` → uvicorn). Kök `.env`'i yükler, `app/web`'i statik PWA olarak `/`'e
mount eder (API rotalarından **sonra**). `/api/chapter` bilinçli olarak **sync
def**'tir: Playwright sync API'si FastAPI'nin thread havuzunda koşsun diye —
saf-heves ile `async`'e çevirme.

**`app/core/pipeline.py`** — Tek orkestrasyon noktası. Hem HTTP endpoint'i hem
arka plan toplu-çeviri işi bunu kullanır. Sıra: refresh değilse cache'e bak →
`fetch_chapter` → slug'ı kanonikleştir → glossary çek → `translate_chapter` →
cache'e yaz → glossary/library güncelle. `FetchError`/`TranslateError` yukarı sızar.

**`app/core/fetch.py`** (en riskli parça) — Playwright ile Cloudflare bypass. **İki
akış, otomatik yedekleme**: (1) `FETCH_CDP_URL` ayarlıysa kullanıcının elle
başlattığı **gerçek Chrome**'a CDP ile bağlan (otomasyon parmak izi yok → sert CF'i
geçer); Chrome kapalıysa sessizce (2) paket Chromium'u kalıcı profil + `STEALTH_JS`
ile başlatan akışa düşer. Yani CDP opsiyonel, ayarlı olsa da telefon/normal kullanım
bozulmaz. Site-özel ayrıştırma kuralları `SITES` sözlüğünde (yeni site = yeni kayıt),
bilinmeyen host için `GENERIC_SITE`. Çözülen CF cookie'si `cache/.pw-profile`'da
kalıcı. **Tüm çekimler tek `_FETCH_GATE` (iki-öncelikli kapı) ile serileşir** — tek kalıcı profil eşzamanlı
açılamaz. Kapıda bekleyen okuyucu isteği (`priority="interactive"`, varsayılan) toplu
çeviri çekiminden (`priority="bulk"`, jobs → pipeline `background=True`) her zaman önce
geçer; geri-çekilme uykuları kapı DIŞINDA tutulur. Tipli hatalar:
`CloudflareChallenge`, origin 52x (`CF_ORIGIN_ERRORS`, beklemez), geçici → `_Transient`
(üstel geri-çekilmeyle yeniden dener).

**`app/core/translate.py`** — Gemini EN→TR, isim-koruyan. Paragrafları
`MAX_WORDS_PER_CHUNK` (2800 kelime) sınırında parçalar, parçalar arası son cümleleri
bağlam olarak taşır, glossary'i prompt'a enjekte eder. **`[[n]]` işaretçileri**
Türkçe↔İngilizce paragrafları hizalar (iki-dilli okuma; hizalama tutmazsa o parça tek
blok, `source` None). **TEK model yedek zinciri, KALİTE öncelikli** (2026-08-17, kullanıcı
kararı): `DEFAULT_MODELS` = `gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash`
→ `gemini-3.5-flash-lite`. Bu sıra HER YERDE geçerlidir — okuma, prefetch, toplu çeviri,
"yeniden çevir", içe aktarılan sayfa çevirisi (`import_translate`) ve sözlük terim önerisi
(`suggest_term`) aynı sabiti kullanır; `refresh` artık YALNIZ önbelleği yok sayar, model
sırasına karışmaz. Yola göre AYRI zincir (ucuz okuma / kaliteli refresh) denendi ve aynı
gün kaldırıldı: okumanın gövdesi prefetch'ten geldiği için ucuz zincir pratikte çevirinin
çoğunu belirliyordu. Düşme kuralı: 500/503 → aynı modelde geri-çekilmeli tekrar, 404/429
(kota dolu) → beklemeden sıradaki modele geç, boş/engellenmiş yanıt (safety) → sıradaki
model. Ölçüm (2026-08-16): 3.6 en akıcı ama ücretsiz kotası ~25 istek/gün, 3.5-flash orta
halka (503'e meyilli), flash-lite en hızlı/en dayanıklı (o yüzden zincirin SON halkası),
3.7 o gün ısrarla 503 verdi (kalitesi ölçülemedi; tökezlerse zincir 3.6'ya iner).
Zincirin alt halkaları süsleme değil, günün çoğunda ASIL taşıyıcıdır — üst halkaların
ücretsiz kotası dar. Fiilen hangi halkanın çevirdiği künyeye yazılır (`chapters.model`).
`SAFETY_SETTINGS` = `BLOCK_NONE`, `max_output_tokens` açıkça verilir
(sessiz kesilme → bozuk JSON → hizalama kaybı). Çıktı JSON
`{translation, detected_names}`; bozuk/yarım JSON için kurtarma ayrıştırıcısı.
**İki bağlam kaynağı** prompt'a girer: `prev_context` (önceki BÖLÜMÜN son ~160 kelimelik
Türkçesi — `cache.prev_translation`) ve `style_note` (kitap başına üslup notu —
`books.style_note`).

**`app/core/cache.py`** — `chapters` tablosu: çevrilmiş bölümlerin URL-anahtarlı
kalıcı önbelleği. Cache isabeti = API çağrısı yok, anahtar gerekmez.

**`app/core/library.py`** — Sunucu-taraflı **paylaşılan kütüphane** (`books` +
`aliases`): PC ve telefon aynı kitap listesini ve okuma konumunu (`current_ratio`)
görür. `merge_books`/`resolve_slug`: aynı kitabın farklı sitelerdeki slug'larını tek
**kanonik slug**'a bağlar (bölüm + glossary tek kitapta toplanır).

**`app/core/glossary.py`** — Kitap-başına terim eşlemesi (kaynak→karşılık). Özel adlar
çeviri sırasında OTOMATİK eklenir (`pipeline._sozluge_isle`), **iki sınıf iki davranış**:
**karakter** (`detected_names`) → İngilizce kalır (`merge_names`, `X -> X`) ve İngilizce
kalan TEK sınıf budur; **karakter dışı HER özel ad** (`detected_terms`: yer, lonca, eşya,
beceri/büyü, unvan, ırk, adlandırılmış canavar, sistem terimi…) → modelin çeviride
kullandığı Türkçe karşılıkla sabitlenir (`merge_terms`). Kutu eskiden yalnız lonca+yer
idi; eşya/beceri adları hiçbir sınıfa girmediği için sessizce kaydedilmiyordu (gerçek
bulgu: Shadow Slave 30. bölüm, `Puppeteer's Shroud`) — 2026-08-17'de tek genel kutuya
çevrildi, **sınıf listesini yeniden daraltma**. Lonca eskiden İngilizce korunuyordu,
2026-08-16'da kullanıcı kararıyla Türkçe'ye alındı — geri döndürmeden önce sor.
`_parse_response` eski `detected_guilds`/`detected_places` alanlarını da okur (model
arada eski şemayı üretiyor; düşürmek terimi kaybettirirdi). **`detected_names` kutusu
SÜZGEÇTEN geçer** (`translate.ayikla_karakter_adlari`, 2026-08-18): model karakter
olmayan adları bu kutuya sızdırıyordu ve oraya düşen her ad sözlüğe İngilizce çakılıp
(prompt'ta KURAL) bir daha Türkçeleşmiyordu — ölçüm: bir kitapta 201 kaydın 173'ü
`X -> X`, içlerinde `Blackwater Guild`, `Star-Moon Kingdom`. Üç eleme: ad
`detected_terms`'te de varsa Türkçe kazanır · Türkçe harf içeren ad İngilizce sayılmaz ·
ad ÇEVİRİ metninde aynen geçmiyorsa (model onu Türkçeleştirmiş) kaydedilmez. Süzgeç
`_finalize_cached`'de de koşar (eski cache satırları her açılışta yeniden kirletiyordu).
Sözlüğe yazma SIRASI da load-bearing: `_sozluge_isle` önce `merge_terms`, sonra
`merge_names` — INSERT OR IGNORE'da ilk yazan kazanır. Kitaplara ÇAKILMIŞ eski kayıtlar
ileriye dönük süzgeçle temizlenmez; `scripts/sozluk_gozden_gecir.py` onları
`translate.classify_terms` ile toplu gözden geçirir (varsayılan KURU çalıştırma,
`--uygula` ile yazar). Amaç tutarlılık: bu adlar
sözlükte olmadıkça model her bölümde yeniden karar veriyor ve aynı şehir bölümden bölüme
başka çıkabiliyordu. İkisi de `INSERT OR IGNORE` — kullanıcının elle yazdığı karşılık ASLA
ezilmez, otomatik algılama yalnız boşluğu doldurur. Terim **okurken de eklenebilir**: okuyucuda
metin seçilince kayan "+ SÖZLÜĞE EKLE" düğmesi çıkar (Android'in kendi seçim menüsüne eylem
eklenemez — o tarayıcının menüsü, sayfaya kapalı), modal açılır ve karşılığı
`POST /api/book/{slug}/glossary/suggest` → `translate.suggest_term` ÖNERİR: aynı kural
(karakter → İngilizce kalır, başka her özel ad → Türkçe). Öneri onaya sunulur, doğrudan
yazılmaz; sözlük prompt'ta KURALdır, yanlış karşılık kitap boyunca birebir uygulanırdı.
Terimi sözlük eşler, **üslubu** ise `books.style_note` sabitler (aynı ekranda,
`/api/book/{slug}/style`): anlatım kişisi/hitap/ton kitap boyunca kaymasın diye her
çeviri prompt'una girer. İkisi de YALNIZ yeni çevrilen bölümde etkilidir.

**`app/core/jobs.py`** — **Bellek-içi** arka plan toplu çeviri (sekme kapansa da sürer;
sunucu yeniden başlarsa iş kaybolur — bölümler cache'te kaldığı için sorun değil).

**`app/core/db.py`** — Paylaşılan SQLite yardımcıları: `db_path()` (`NOVEL_DB_PATH` ile
override), `connect()` (WAL + `busy_timeout`), `ensure_column()` (idempotent migration).

**`app/core/epub_export.py`** — EbookLib ile cache'teki çevrilmiş bölümlerden ePub üretir.

**`app/core/import_book.py`** — EPUB/PDF dosyalarından **GÖRSEL** kitap içe aktarır (web-
romanı gibi düz metin DEĞİL; sayfa/bölümün kendisi çevrilir, resim+düzen korunur). PDF:
her SAYFA = 1 bölüm, kaynak PDF `media`'ya saklanır (`pdf://slug/N`). EPUB: her doküman =
1 bölüm, gömülü resimler `media`'ya çıkarılır + `<img src>` `/media`'ya yeniden yazılır,
gövde HTML'i raw_source'ta (`epub://slug/N`). İkisi de `content_type="html"` sahneli satır;
İÇE AKTARIM ÇEVİRMEZ, yalnız sahneler. Uçlar `POST /api/import/epub` · `/pdf` (ham gövde,
50MB, parse threadpool).

**`app/core/import_translate.py`** — içe aktarılan sayfayı OKUDUKÇA (on-demand) çevir+üret:
PDF → sayfa metin bloklarını bbox'la çıkar, hizalı Türkçe çeviri, orijinali redaction ile
sil + Türkçe'yi aynı yere DİKEY AKIŞLA yaz (üst üste binmesin; Türkçe TTF, font küçülür),
sayfayı PNG render → `<img>` HTML. EPUB → HTML'i temizle (script/on*/href elenir), blok
metinleri yerinde çevir, resim/yapı korunur. MANGA → sayfa görselini **Gemini-vision**'a
gönder (balon metni + bbox + Türkçe), PIL ile orijinali kapat + Türkçe'yi kutuya yaz.
`pipeline._render_import_page` üçünü de çağırır (pdf://·epub://·manga://); sonuç HTML cache'lenir.

**`app/core/media.py`** — içe aktarılan kitapların medyası (`cache/media/<slug>/`: kaynak
PDF, render'lı sayfa PNG'leri, EPUB resimleri). `GET /media/<yol>` ile YALNIZ çevrimiçi
servis (SW DATA_CACHE'ine girmez); path-traversal korumalı.

**`app/web/`** — Çerçevesiz (vanilla JS) PWA, **build adımı yok**: `app.js`, `index.html`,
`style.css`, `sw.js`. **`scripts/start_chrome_cdp.py`** — gerçek Chrome'u `:9222` debug
portu + ayrı profil (`cache/.chrome-cdp`) ile açar. **`faz0/`** — eski kavram-kanıtı
(bağımsız; `app/` bunun yerini aldı, dokunma).

## Tek veritabanı

Her şey **tek SQLite dosyasında**: `cache/chapters.db` (WAL modu). Üç mantıksal depo:
`chapters` (cache), `books`+`aliases` (kütüphane), `glossary`. **Merkezi şema/migration
dosyası yoktur** — her modülün `_connect()`'i kendi tablosunu `CREATE TABLE IF NOT EXISTS`
ile tembel oluşturur. **Yeni sütun eklerken `db.ensure_column()` kullan** (idempotent;
SQLite'ta `ADD COLUMN IF NOT EXISTS` yok). `NOVEL_DB_PATH` env'i yolu değiştirir;
`tests/conftest.py` her testi geçici DB'ye yönlendiren autouse fixture ile izole eder.

## Kritik kararlar & tuzaklar

- **PWA service worker sürümü**: kabuk varlıkları (`app.js`/`index.html`/`style.css`)
  değişince `app/web/sw.js` içindeki `SHELL_CACHE = "novellink-shell-vNN"` **artırılmalı**,
  yoksa telefonlar bayat kabuğu servis eder. `DATA_CACHE` **sabit** isimlidir (bölüm
  `/api` yanıtlarını tutar; sürümle silinmez). Bu tekrarlayan, elle yapılan bir adımdır.
- **mimetypes düzeltmesi** (`server.py` başı): Windows kayıt defteri `.webmanifest`/`.svg`
  için yanlış Content-Type verir → Chrome PWA ikonu/manifesti reddeder; elle kayıt şart.
- **Tipli hata → `error_class`**: `server.py` hata yanıtlarında `error_class` döndürür
  (`CloudflareChallenge`/`OriginError`/`FetchError`/`TranslateError`); frontend kırılgan
  string-eşleştirmesi yerine sınıfa göre dallanır.
- **Seslendirme (TTS) bilinçle KALDIRILDI**: çevrimdışı indirmeyi bölüm başına dakikalara
  çıkarıyordu (her bölüm için ses üretimi). Geri eklenecekse indirme akışından TAMAMEN ayrı
  tutulmalı — "çevrimdışı indir" hiçbir koşulda ses üretimini beklememeli.
- **Bölüm künyesi cache'te saklanır** (`chapters.engine`, `chapters.model`,
  `chapters.added_terms`): hangi motor + zincirin hangi HALKASI çevirdi ve o çeviride
  sözlüğe ne eklendi. Okuyucuda bölüm sonundaki açılır rozet bunu gösterir.
  `engine` bugün hep `gemini` yazar ama sütun DURUYOR: DB'de ikinci-motor
  denemesinden kalma `claude` satırları var, rozet onları da doğru göstermeli.
  `model` (2026-08-17) fiilen çeviren model adıdır — `_generate_with_fallback` artık
  `(response, model)` döndürüp bunu yukarı taşır; parçalar farklı halkalara düştüyse
  `" + "` ile birleşir. Eklenme sebebi somut: bir deyim hatası tartışılırken "bunu hangi
  model çevirdi" sorusu tahminle cevaplanmak zorunda kaldı. Eski satırlarda NULL.
  DB'de saklanmasının sebebi önbellek isabeti: bölüm ikinci açılışta
  `merge_*` boş döner (her şey zaten kayıtlı), künye DB'den okunmazsa kaybolurdu.
  Künye alanları `save_chapter`'da **`COALESCE(excluded.x, x)`** ile yazılır — künye
  TAŞIMAYAN bir payload (ör. çevrilecek metni olmayan görsel sayfa) aynı satırı
  güncelleyince mevcut künye NULL'a düşmesin (E-16 sınıfı hata, farklı sütunlar).
  **Künyeyi üreten DÖRT nokta var** — `_fetch_translate_save` (okuma/prefetch/toplu),
  `fetch_into_book` ("web'den devam": kitaba URL ile bölüm ekleme), `_render_import_page`
  (PDF/EPUB/manga sayfası) ve `manga_engine._save_engine_page` (yerel motor batch'i
  cache'e KENDİ yazar). Künyeye yeni alan eklerken DÖRDÜNE de ekle: `model` bir süre
  yalnız ilkindeydi, URL ile eklenen bölüm "GEMINI ile çevrildi" deyip hangi halkanın
  çevirdiğini söylemiyordu, görsel bölümde ise rozet hiç çizilmiyordu. Görsel yolda
  künye taşımak için üç çeviri fonksiyonu `(html, model)` döndürür
  (`translate_pdf_page` · `translate_epub_html` · `translate_manga_page`) — modeli
  atan tek satır rozeti sessizce söndürür. Sayfada çevrilecek metin YOKSA model None
  ve künye hiç yazılmaz: "çevrildi" demek yanlış olurdu.
- **Künye rozeti `renderParagraphs`/`renderHtmlContent` SONUNDA çizilir**, `buildChapterEntry`
  içinde değil: iki render fonksiyonu da article'ı `.chapter-sep` dışında temizleyip yeniden
  kuruyor ve bölüm içi arama `renderParagraphs`'ı tekrar çağırıyor — yukarıda eklenseydi ilk
  aramada sessizce kaybolurdu.
- **Tek çeviri motoru var: Gemini.** İkinci motor (Claude CLI köprüsü) 2026-08-16'da
  DENENDİ ve KALDIRILDI — geri eklemeden önce ölçümü oku. Aynı 4200 kelimelik metin:
  Claude sonnet 82,1 sn · Claude haiku 75,5 sn · gemini-3.6-flash 32,5 sn ·
  gemini-3.5-flash-lite 18,5 sn. Yani Claude flash'ın ~2,5 katı yavaştı ve MODEL
  DEĞİŞTİRMEK KURTARMIYORDU (haiku ile sonnet pratikte aynı). Üstüne parça başına ~3 sn
  süreç doğumu ve `Semaphore(1)` — tüm Claude çağrıları tek sıradan geçtiği için
  prefetch okuyucunun canlı isteğini bekletiyordu (Gemini yolunda böyle bir kapı yok).
  Kalite farkı bu gecikmeyi karşılamadı.
- **Okunan bölümü çeviren şey prefetch'tir, okuma isteği değil**: bölüm açılınca
  `app.js:prefetchNext` → `POST /api/prefetch` → `get_or_translate(background=True)`
  bir SONRAKİ bölümü ısıtır. Kaydırıp oraya geçtiğinde artık önbellek isabetidir.
  Motor/politika değiştirirken bunu unutma: "okuma yoluna" uygulanan bir kural pratikte
  yalnız SOĞUK açılışa uygular, akışın gövdesi prefetch'ten gelir (Claude denemesinin
  ilk günü tam olarak buna takıldı — künyede beklenen motor bir türlü görünmedi).
- **`MAX_WORDS_PER_CHUNK` çalışma zamanında monkeypatch'lenemez**: `_split_paragraphs`'ın
  varsayılan argümanı modül yüklenirken bağlanır. Testte parça sayısını değiştirmek için
  `_split_paragraphs`'ı sahtele.
- **Sözlük prompt'ta İKİ kez geçer; sıra load-bearing**: liste başta, kısa bir "SON
  HATIRLATMA" çevrilecek METNİN ARDINDAN. Ölçülen sorun: 1500 kelimelik bölümde model
  baştaki sözlüğü unutup korunması gereken 26 adın 23'ünü Türkçeleştiriyordu (uydurma
  "Işıkölge" böyle çıktı); hatırlatma sona eklenince ihlal 4 turda da 0'a indi. Prompt'u
  yeniden düzenlerken hatırlatmayı metnin ÖNÜNE çekme — etki yakınlıktan geliyor.
- **Sözlük karşılığı prompt'ta KURALDIR, öneri değil**: model onu birebir uygular. Garip
  bir Türkçe çıktı gördüğünde ÖNCE `glossary` tablosuna bak — otomatik eklenen kayıtlar
  daima `X -> X` (İngilizce korunur, `merge_names`), farklı bir karşılık gören her satır
  ELLE eklenmiştir. Gerçek bulgu: "Lightshadow City"nin "ışık gölge şehri" çıkmasının
  sebebi model değil, `lightshadow city -> ışık gölge şehri` kaydıydı.
- **Deyimler prompt'ta AYRI ve ÖRNEKLİ madde ister**: "akıcı, birebir değil" genel
  maddesi kalıpları tutmuyor. Gerçek bulgu (bölüm 1862): `turn the tables on them` →
  "masaları onlara karşı çevirecekti". Kural artık örnekli ve modele bir ÖLÇÜT veriyor
  ("bağlamı bilmeyen biri 'bu ne demek şimdi' diyorsa birebir çevirmişsindir").
  Örnekleri silme — etki genel ifadeden değil, somut yanlış/doğru çiftlerinden geliyor.
- **Terim eşleştirme YAZIM VARYANTINA toleranslı olmalı** (`translate._term_regex`,
  `glossary.fold_term`): aynı özel ad metinde `Ore Empire` · `OreEmpire` · `Ore-Empire`
  diye ve — ölçülen gerçek vaka — bir bölümde düz `'`, ötekinde kıvrık `’` kesme
  işaretiyle geçiyor. Desen kelime PARÇALARINDAN kurulur, aralarına esnek ayırıcı
  (`[\s\-_'’]*`) girer; tek parçalı kayıt CamelCase'den bölünür (`OreEmpire` → `Ore`
  + `Empire`), ama bölme kayıpsız değilse ad bozulmasın diye bölünmez. Süzmenin ucuz
  ön elemesi de `fold_term` üzerinden yapılır — düz `term.lower() in text.lower()`
  kontrolü terimi regex'e VARMADAN eliyordu, yani sözlükte kayıtlı ad prompt'a hiç
  girmiyordu. `merge_terms` "zaten kayıtlı mı" kararını da `fold_term` ile verir
  (varyant ikinci satır açmaz, karşılıklar ayrışmaz). **Ayırıcı listesini daraltma.**
- **Türkçe ek kuralı prompt'ta TEK ve GENEL madde olmalı**: kural bir zamanlar yalnız
  SÖZLÜK maddesinin altındaydı, `CORE_TERM_HINTS` ile gelen sistem terimlerini
  (level→seviye) kapsamıyordu — "farklı bir seviyeindeydi" (doğrusu: seviyesindeydi)
  oradan çıktı. Yeni kural ekleyeceksen ek/kaynaştırma maddesinin kapsamını daraltma.
- **Sonsuz okuma bir AYARDIR** (`settings.infinite`, ayarlar panelinde Açık/Kapalı):
  kapalıyken alt gözlemci HİÇ kurulmaz, bölüm sonunda "SONRAKİ BÖLÜM →" düğmesi çıkar ve
  bölüm akışa eklenmek yerine temiz sayfa olarak açılır. Manga'nın site'den sonraki bölümü
  çekmesi de aynı anahtara bağlı. Anahtar okuyucu açıkken çevrilebildiği için
  `refreshStreamEnd()` gözlemciyi + bitiş kartını yerinde yeniden kurar.
- **Akış devamı zincire (next_url) MAHKÛM DEĞİL**: aynı kitap iki siteden çevrilmiş
  olabilir — bölüm 100'ün next'i A sitesinin HİÇ çevrilmemiş 101'ini gösterirken fiilen
  indirilmiş 101 B sitesinden gelmiş olur; çevrimdışıyken zincir ölür, liste yaşar (gerçek
  bulgu: telefonda akış durdu, bölüm listesinden elle geçildi). `app.js:pickNextTarget`
  zincirin next'i o kitapta çevrilmemişse ve listede sıradaki varsa LİSTEYİ seçer; liste
  `ensureChapterList` ile çekilir ve `loadChapter` sonunda ısıtılır (SW önbelleğine girsin
  diye — çevrimdışı devamın ön koşulu bu). Kuralı tersine çevirme: zincir listedeyse yine
  zincir kazanır, yoksa web'den ilerleyen okuma bozulur.
- **slug her şeyin anahtarı**, URL'den türetilir; pipeline cache/glossary'den önce daima
  `resolve_slug` ile kanonikleştirir. Yeni endpoint yazarken bu adımı atlama.
- Durum dökümanları: `PLAN-dayaniklilik.md` (Faz 5, kısmen sevk edildi — bulk kalıcılığı
  bilinçle düşürüldü), `progress.md`, `TODOS.md`.

## Ortam değişkenleri (`.env`, kök dizinde)

| Değişken | Zorunlu | Ne işe yarar |
|---|---|---|
| `GEMINI_API_KEY` | Evet | Gemini anahtarı (yalnız yeni çeviri için; cache isabeti gerektirmez) |
| `FETCH_CDP_URL` | Hayır | Örn. `http://127.0.0.1:9222` → sert CF için gerçek Chrome'a bağlan |
| `FETCH_HEADLESS` | Hayır | `0` → görünür pencere (CF'i bir kez elle çözmek için) |
| `NOVEL_DB_PATH` | Hayır | Test/CI'da DB'yi geçici dosyaya yönlendirir |

`.env` git'e girmez (`.gitignore`); ikinci makineye elle kopyalanır — bkz. `KURULUM.md`
(Tailscale ile 7/24 sunucu kurulumu ve sorun giderme).

## Test yazımı

Testler **çevrimdışıdır** — Playwright/Gemini çağıran endpoint'ler (`/api/chapter`,
bulk başlatma) test edilmez; saf fonksiyonlar (translate ayrıştırma, fetch nav çıkarımı),
SQLite roundtrip'leri ve ağ gerektirmeyen endpoint'ler (`TestClient`) kapsanır. `conftest.py`
`app/`'i `sys.path`'e ekler ve `NOVEL_DB_PATH`'i geçici DB'ye ayarlar (autouse), böylece
testler `from core import …` / `import server` yapabilir ve gerçek DB'ye dokunmaz.
