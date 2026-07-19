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
`MAX_WORDS_PER_CHUNK` sınırında parçalar, parçalar arası son cümleleri bağlam olarak
taşır, glossary'i prompt'a enjekte eder. **`[[n]]` işaretçileri** Türkçe↔İngilizce
paragrafları hizalar (iki-dilli okuma; hizalama tutmazsa o parça tek blok, `source`
None). **Model yedek zinciri** (`DEFAULT_MODELS`): 500/503 → aynı modelde geri-çekilmeli
tekrar, 404/429 → beklemeden sıradaki modele geç, boş/engellenmiş yanıt (safety) →
sıradaki model. `SAFETY_SETTINGS` = `BLOCK_NONE`. Çıktı JSON
`{translation, detected_names}`; bozuk/yarım JSON için kurtarma ayrıştırıcısı.

**`app/core/cache.py`** — `chapters` tablosu: çevrilmiş bölümlerin URL-anahtarlı
kalıcı önbelleği. Cache isabeti = API çağrısı yok, anahtar gerekmez.

**`app/core/library.py`** — Sunucu-taraflı **paylaşılan kütüphane** (`books` +
`aliases`): PC ve telefon aynı kitap listesini ve okuma konumunu (`current_ratio`)
görür. `merge_books`/`resolve_slug`: aynı kitabın farklı sitelerdeki slug'larını tek
**kanonik slug**'a bağlar (bölüm + glossary tek kitapta toplanır).

**`app/core/glossary.py`** — Kitap-başına terim eşlemesi (kaynak→karşılık); algılanan
karakter isimleri otomatik eklenir (`merge_names`, mevcut düzenlemeyi bozmaz), kullanıcı
düzenler.

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
- **slug her şeyin anahtarı**, URL'den türetilir; pipeline cache/glossary'den önce daima
  `resolve_slug` ile kanonikleştirir. Yeni endpoint yazarken bu adımı atlama.
- Durum dökümanları: `PLAN-dayaniklilik.md` (Faz 5, kısmen sevk edildi — bulk kalıcılığı
  bilinçle düşürüldü), `progress.md`, `TODOS.md`.

## Ortam değişkenleri (`.env`, kök dizinde)

| Değişken | Zorunlu | Ne işe yarar |
|---|---|---|
| `GEMINI_API_KEY` | Çeviri için evet | Gemini anahtarı (cache isabeti gerektirmez) |
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
