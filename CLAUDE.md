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

# Test (kök dizinden; ağ/Gemini çağırmaz, çevrimdışı ~20 sn). `tests` VER: kökte
# koşunca takip dışı scratch/ klasöründeki betikler toplanıp çöküyor.
.\.venv\Scripts\python.exe -m pytest tests
.\.venv\Scripts\python.exe -m pytest tests\test_api.py::test_books_empty   # tek test
# Arayüz modüllerinin saf mantığı (Node; pytest de test_js_birim.py ile çağırır)
node --test "tests/js/*.test.mjs"        # klasör değil DESEN ver
# Gerçek tarayıcı testleri (Playwright, isteğe bağlı; kendi test sunucusunu açar)
$env:NOVEL_TARAYICI_TEST=1; .\.venv\Scripts\python.exe -m pytest tests\tarayici
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
kaynak seç → slug'ı kanonikleştir → glossary çek → `translate_chapter` → cache'e yaz →
glossary/library güncelle. `FetchError`/`TranslateError` yukarı sızar.

**Kaynak seçimi siteye inmeden ÖNCE dört dala bakar** (`_do_fetch_translate_save`):
görsel içerik (`content_type="html"`) → sayfa render; içe aktarılmış `raw_source` →
ondan çevir; sentetik URL ama kaynak yok → 404; **önbellekte hizalı İngilizce kaynak
(`chapters.source_text`) → `_onbellek_kaynagi`, web'e HİÇ gitme**; hiçbiri değilse
`fetch_chapter`. Dördüncü dal 2026-08-23'te eklendi: **"yeniden çevir" (`refresh=True`)
eskiden önbelleği atlayınca doğrudan Playwright + Cloudflare'e iniyordu** (deneme başına
60 sn zaman aşımı + kendi geri-çekilmesi + tek kalıcı profil yüzünden serileşme), oysa
kullanıcı "yeniden çevir" derken genellikle SÖZLÜĞÜ değiştirmiş
oluyor ve İngilizce kaynak aynı — aynı metni yeniden indirmek tamamen boşa harcanan
süreydi (ölçülen vaka: Shadow Slave 1. bölüm 1-2 dakika). Dal KENDİNİ SEÇER: bölüm
önbellekte yoksa ya da hizalama tutmadığı için `source` NULL'sa akış fetch'e düşer.
İndirmeyi zorlamak için `refetch=True` (uçta `?refetch=1`) — kaynağın KENDİSİ bozuk
geldiğinde gerekir, okuyucudaki "Bölüm Boş → Siteden Yeniden Çek" düğmesi bunu kullanır.
Bu yol `next_url`/`prev_url`'ü önbellekten TAŞIR, tazelemez; tazeleme ayrı bir iştir
(`refresh_metadata`, check-updates).

**`app/core/fetch.py`** (en riskli parça) — bölüm çekme, **ÜÇ akış, otomatik
yedekleme**: (0) **düz HTTP** (`_fetch_via_http`, tarayıcısız) → (1) `FETCH_CDP_URL`
ayarlıysa kullanıcının elle başlattığı **gerçek Chrome**'a CDP ile bağlan (otomasyon
parmak izi yok → sert CF'i geçer) → (2) paket Chromium'u kalıcı profil + `STEALTH_JS`
ile başlatan akış. Her katman başarısızlıkta `None` döner ve bir alttakine düşülür;
hiçbiri istisna FIRLATMAZ — fırlatsa alttaki yol hiç denenmezdi. Yani CDP opsiyonel,
ayarlı olsa da telefon/normal kullanım bozulmaz.

**DÜZ HTTP BİRİNCİ YOL** (2026-09-11, ölçüldü). Cloudflare koruması freewebnovel'in
ANA SAYFASINDA var, BÖLÜM sayfalarında YOK. Ölçüm: 5 kitap x 12 bölüm (bölüm 4'ten
1880'e), hepsi HTTP 200 ve ayrıştırılan metin önbellektekiyle BİREBİR aynı. Süre
1-8 sn; aynı bölüm Playwright'la 68 sn sürüyor ve çoğu zaman challenge'a takılıyordu.
Kazanç yalnız hız değil: tarayıcısız yol bulut sunucuda Chromium'u tümden gereksiz
kılar. `FETCH_HTTP_FIRST=0` acil çıkıştır. Tarayıcı yolu SİLİNMEZ — site korumayı
bölümlere yayarsa akış kendiliğinden oraya düşer.

**TLS PARMAK İZİ: `curl_cffi` ŞART** (2026-09-11, ölçüldü). Düz HTTP yolunun
SUNUCUDA çalışmasının TEK koşulu. Ölçüm (GCP e2-micro / Ubuntu 24.04): düz `requests`
ile **403 + "just a moment"**, aynı anda ev makinesinden (Windows) aynı URL **200**.
Suçlu IP DEĞİLDİ — beş ayrı ülkeden beş residential proxy IP'si denendi, **beşi de
403** (0/5). Fark TLS katmanında: Linux OpenSSL'in ürettiği JA3 imzası CF tarafından
reddediliyor. `_http_get` içindeki `impersonate="chrome"` ile sunucudan da 200 geldi,
üstelik **proxy OLMADAN**. Parametre kaldırılırsa sunucuda çekim TÜMDEN durur;
`tests/test_fetch_duz_http.py` tel tuzağıyla tutar. Ders: "403 geldi → IP engellendi"
sezgisi bu projede yanlış çıktı, önce TLS katmanını ölç.

Site-özel ayrıştırma kuralları `SITES` sözlüğünde (yeni site = yeni kayıt),
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
blok, `source` None). **ANA MOTOR: Gemini** (2026-09-02, kullanıcı kararı; 2026-09-26'dan
beri Google DIŞI tek bir son halka var, aşağıya bak) ve **TEK model
yedek zinciri, KALİTE öncelikli**: `DEFAULT_MODELS` = **`gemini-3.6-flash`** →
`gemini-3.5-flash` → `gemini-2.5-flash` → `z-ai/glm-5.3` (NVIDIA). Bu sıra HER YERDE geçerlidir — okuma,
prefetch, toplu çeviri, "yeniden çevir", içe aktarılan sayfa çevirisi (`import_translate`)
ve sözlük terim önerisi (`suggest_term`) aynı sabiti kullanır; `refresh` YALNIZ önbelleği
yok sayar, model sırasına karışmaz. Yola göre AYRI zincir (ucuz okuma / kaliteli refresh)
denendi ve aynı gün kaldırıldı: okumanın gövdesi prefetch'ten geldiği için ucuz zincir
pratikte çevirinin çoğunu belirliyordu. Zincirin alt halkaları süsleme değil, günün
çoğunda ASIL taşıyıcıdır — üst halkaların ücretsiz kotası dar. Fiilen hangi halkanın
çevirdiği künyeye yazılır (`chapters.model`).

**ÇEVİRİ MODELİ SEÇİLEBİLİR** (2026-09-02, kullanıcı isteği). Okuyucunun ayarlar
panelinde yedi seçenek: `gemini-3.8-flash` · `gemini-3.7-flash` · `gemini-3.6-flash`
(varsayılan) · `gemini-3.5-flash` · `gemini-2.5-flash` · **`claude-haiku-4-5`** ·
**`claude-sonnet-5`** (son ikisi ÜCRETLİ, aşağıya bak). `gemini-2.5-flash`
2026-09-06'da eklendi; ölçümü aşağıda. **Seçim zincirin YERİNİ ALMAZ, BAŞINA geçer**
(`translate.zincir_kur`): ölçüldü ki 3.7 ve 3.8 bu projenin uzunluktaki isteklerini sık
sık 503 ile reddediyor, dolayısıyla "yalnız bunu kullan" yorumu o modeli seçen
kullanıcının okumasını modelin kapasitesi daraldığı anda TÜMDEN durdururdu. Seçim bir
TERCİHTİR, kilit değil; künye rozeti FİİLEN çevirenin adını yazdığı için "3.8 seçtim
ama 3.6 çevirmiş" durumu gizlenmez. Tanınmayan seçim sessizce varsayılana düşer (ayar
tablosunda bozulmuş bir değer, her isteği 404'e çarpan bir birinci halka yaratırdı).

Ayar **sunucuda** durur (`app/core/settings.py`, `settings` kv tablosu; uçlar
`GET`/`POST /api/settings/model`), okuyucunun `localStorage`'ında DEĞİL. Üç sebep:
çeviriyi sunucu yapıyor · telefon ve PC aynı seçimi görmeli · okumanın GÖVDESİ
prefetch'ten ve toplu çeviriden geliyor, ikisi de istemci olmadan koşuyor ve
istemci-taraflı bir ayarı okuyamazlardı. Seçenek listesini de sunucu veriyor
(`SECILEBILIR_MODELLER`, etiket + ölçüm notuyla); okuyucuda ikinci bir liste tutulsaydı
model eklendiğinde ayrışır ve sunucunun tanımadığı bir ad gönderilirdi.

**Zincir TEK noktada çözülür** (`translate.secili_zincir`), çağrı yerlerine tek tek
geçirilmez: zinciri kullanan BEŞ yol var (okuma, prefetch, toplu çeviri, içe aktarılan
sayfa/manga, sözlük terim önerisi) ve bu projede aynı kuralın birden çok yerde
yazılması defalarca ayrışmayla sonuçlandı (künye alanları, motor adı). Biri
güncellenmeyi unutulsa kullanıcı "modeli değiştirdim ama bazı bölümler hâlâ eskisiyle
çevriliyor" derdi. `models=None` varsayılanı ayardan çözülür; açıkça verilen zincir
ayarı ezer (testler ve bakım araçları için). Sözlükle aynı kural: seçim
YALNIZ yeni çevrilen bölümde geçerlidir.

**CLAUDE: ÜCRETLİ, YALNIZ AÇIKÇA SEÇİLİNCE, YEDEKSİZ** (2026-09-02, kullanıcı kararı).
Zincirin diğer bütün halkaları ücretsiz; Claude değil, ve bu tek fark tasarımı belirliyor.
**Claude ASLA yedek halka olamaz** — `zincir_kur` Claude seçilince TEK HALKALI bir zincir
kurar. İki yönü de kapalı: Claude çeviremezse Gemini'ye sessizce düşülmez (künye "Claude"
derken bölümü Gemini çevirmiş olmaz), ve Gemini seçiliyken kota dolsa bile Claude'a
ASLA inilmez — yani sürpriz harcama YAPISAL olarak imkânsız. Gerekçe bu projede bir kez
ödenmiş bir ders: OpenRouter'ın `:free` soneki düştüğünde istek 200 dönüyor, çeviri
çalışıyor, hiçbir hata görünmüyor, yalnız FATURA işliyordu. Sessizce paraya dönen arıza,
gürültülü arızadan tehlikelidir. `tests/test_model_secimi.py` iki yönü de tel tuzağıyla
tutar.

Claude yolunun üç özel kuralı var, üçü de ÖLÇÜLEREK bulundu:
* **Anahtar döngüsü YOK.** `_generate_once_with_retry` Gemini anahtar havuzu üzerinde
  döner; Claude'un tek anahtarı var ve aynı istek her turda PARA harcardı.
* **`temperature` HİÇ gönderilmez** (Gemini yolunda 0.3). SDK'nın akış yardımcısı
  örnekleme parametrelerini kabul etmiyor (`stream()` imzasında yok — ilk gerçek çağrı
  `TypeError` ile patladı) ve Sonnet 5 onları zaten 400 ile reddediyor.
* **Düşünme (extended thinking) KAPALI.** Düşünme çıktısı da ÇIKIŞ tokenı olarak
  faturalanıyor ($5-10/M) ve çeviri mekanik bir iş. Sonnet 5'te `thinking` HİÇ
  verilmezse adaptif düşünme AÇIK gelir, yani kapatmak açıkça yapılmalı.

**GEMİNİ YOLUNDA DÜŞÜNME AÇIK — kapatma DENENDİ ve GERİ ALINDI** (2026-09-22 ->
09-23; `GEMINI_DUSUNME_BUTCESI = None`, yani `thinking_config` hiç gönderilmez).
2026-09-22'de bütçe 0 yapılmıştı: ölçüm (`gemini-2.5-flash`, iki bölüm) hizalama,
sözlük ihlali ve kalıntının değişmediğini, çıkışın ~%75'inin düşünme tokeni
olduğunu, sürenin 65 -> 19 sn düştüğünü bulmuştu. Bir gün sonra kullanıcı iki arıza
bildirdi ("3.6 sözlükteki kelimeleri çevirmiyor", "Saint ayrımını yapamıyor") ve
sunucu verisi ikisini de doğruladı. İkisini de o ölçüm GÖREMEZDİ:

* **KOŞULLU kayıt uygulanamıyor.** `Saint -> Aziz [KOŞUL: yalnız rütbe; gölgenin ADI
  ise İngilizce kalır]`: 2.5-flash'ta gölgenin adı düşünme açıkken 44 paragrafın
  44'ünde korunmuş, kapalıyken 21'in 5'inde "Aziz" olmuş. Kontrollü A/B (bölüm 667,
  aynı prompt, tek değişken): bütçe 0 -> beş adın BEŞİ "Aziz"; varsayılan -> beşi de
  "Saint". Kör nokta: uyum denetimi koşullu kayıtları BİLEREK ölçmüyor, yani arıza
  hiçbir sayıya yansımadı.
* **3.x ailesinde sözlük uyumu olasılıksal olarak ÇÖKÜYOR** — ölçülen model 2.5'ti,
  zincirin başı 3.6. Düşünme kapalıyken 3.6-flash bölüm 656'da 22 kayıtlı terimi
  İngilizce bıraktı ("Sanctuary'ye", "Transcendent'a", küçük harfli "sacred ağaç");
  3.5-flash bölüm 655'in iki koşusunda 5 ve 33 (rün bloğunu çevirmeden kopyaladı).
  Düşünme açıkken 3.6'nın 209 bölümünde yalnız biri ihlalliydi. Aynı bölümün
  kontrollü iki koşusu TEMİZ çıktı — arıza her seferinde olmuyor, ama tek bozuk koşu
  kalıcı önbelleğe yazılır ve bir daha çeviri tetiklemez.

Bedeli: bölüm başına ~40-60 sn (kapalıyken 12-18 sn) ve çıkış tokeninin ~%75'i
düşünme. Okumanın gövdesi prefetch'ten geldiği için süre çoğunlukla görünmez.
**Ders: bir kalite ölçümü, kaldırılan yeteneğin kullanıldığı yerleri de içermeli.**
Ara bütçe (ör. 2048) denenecekse ölçüm KOŞULLU bir kaydı ve bir 3.x modelini
içermeli — ilk kapatma tam olarak bu iki boşluktan geçti. Sayı verilirse gönderilir
(0 = kapalı); `thinking_config` desteklemeyen bir model 400 alır ve zincir 400'ü
KURTARMAZ. Manga görsel yolu bu daldan geçmez. Testler `tests/test_gemini_anahtarlari.py`.

**MALİYET ÖLÇÜLDÜ** (`scratch/claude_maliyet.py`, gerçek prompt + gerçek bölümler;
token sayımı Anthropic'in ücretsiz `count_tokens` ucuyla). Ortalama bölüm **8.284 giriş
+ 4.952 çıkış** token → Haiku 4.5 ~$0,033 · Sonnet 5 ~$0,066. **Maliyetin ~%75'i
ÇIKIŞTAN gelir** (çıkış tokenı girişin 5 katı fiyatta) ve bu, alışılmış tavsiyeyi
tersine çevirir: girişin %58'i sabit yük olmasına rağmen prompt önbelleklemesi bu iş
yükünde yalnız ~%13 kazandırır, o yüzden KURULMADI. Batch API %50 kazandırır ama
asenkron olduğu için okumaya uymaz.

**Claude kalite ölçümü — TEK bölüm, tek koşu** (shadow-slave #123, 2026-09-02): Haiku 4.5
uzunluk oranı **0,924** / 58 sn / $0,027 · Sonnet 5 **0,936** / 77 sn / $0,068. İkisinde
de hizalama tuttu ve SIFIR sözlük ihlali. Kıyas için AYNI bölümde Gemini: 3.6-flash 0,939 ·
3.5-flash 0,945 · 3.5-flash-lite 0,948. Yani her iki Claude modeli de ölçülen bütün Gemini
modellerinin ALTINDA kaldı ve Haiku, zincirden kalite gerekçesiyle çıkarılan minimax'ın
(0,922) seviyesinde. **Tek ölçüm tutarlılık göstermez** (bu projenin kendi kuralı) ve
uzunluk oranı akıcılığı ölçmez — çeviriler `scratch/kiyas_ciktilari/` altında, karar
okunarak verilmeli.

**HARCAMA GÖSTERGESİ** (`app/core/kullanim.py`, `kullanim` tablosu; kullanıcı kararı: fren
DEĞİL, gösterge). Ayarlar panelinde "bu ay N bölüm ≈ $X". **TOKEN saklanır, maliyet
DEĞİL**: fiyat sağlayıcının elinde ve değişir; doları kaydetseydik fiyat değiştiği gün
geçmiş kayıtlar sessizce yanlışa dönerdi. Fiyatı bilinmeyen (ücretsiz) modeller
göstergeye girmez — "0,00 $ harcadın" satırları asıl bilgiyi gürültüye boğardı. Sayaç
yazımı `sqlite3.Error`'ı YUTAR: gösterge, çeviri yolunun kritik parçası değil.

**`gemini-3.5-flash-lite` ZİNCİRDEN ÇIKARILDI** (2026-09-09, kullanıcı kararı).
Zincir o gün İKİ halkaya indi (2026-09-15'te 2.5-flash ile yeniden ÜÇ oldu; aşağıya
bak). Lite bir dönem son halkaydı ("en dayanıklısı, zincir tükenmesin
diye") ama sözlük uyumu ölçülenlerin en kötüsüydü — 4 bölümde 30 ihlal, 3.6-flash 60
bölümde 5. Son halka olması durumu ağırlaştırıyordu: üst halkalar elendiğinde okuma
sessizce ORAYA iniyor, çeviri kalıcı önbelleğe yazılıyor ve bir daha denetlenmiyordu.
Daralan kapasitenin karşılığı anahtar tarafında ödendi (aşağıdaki iki madde).

**Düşme kuralı İKİ BOYUTLUDUR ve sırası load-bearing** (2026-09-02; 503 dalı
2026-09-09'da ölçümle DÜZELTİLDİ):
1. **Kota (429) → aynı MODELDE sıradaki ANAHTAR**, ve o anahtar soğumaya alınır. Model
   sabit kalır: kota bir kalite kusuru değildir, kaliteden ödün vermek için de sebep
   değildir.
2. **Geçici arıza (500/503/taşıma) → İKİ KATMAN.** İÇ katman havuzu **uykusuz**
   dolaşır (sağlam anahtar ara); hiçbiri çeviremediyse DIŞ katman geri-çekilerek
   **turu tekrarlar** (`MAX_RETRIES` tur, 2s→4s). Tur tekrarı yalnız geçici arızaya
   özgüdür: kota beklemekle açılmaz, orada tekrar saf kayıptır (`turda_gecici`
   bayrağı bunu ayırır).

   **Model TÜKENİRSE soğumaya alınır** (2026-09-21, ölçümle EKLENDİ — eski kural
   "503 soğutmaz" diyordu). Gerekçe: **503 dönen istek de GÜNLÜK KOTADAN sayılıyor.**
   Ölçülen gün: `gemini-3.6-flash` beş anahtarın BEŞİNDE de tam 20 denemede 429'a
   çarptı (ücretsiz sınır 20/proje/model) ve o denemelerin neredeyse tamamı 503'tü —
   103 deneme harcandı, 2 bölüm çevrildi. Model akşam toparlasa bile kotası bittiği
   için kullanılamaz hâle geliyordu. Zarar iki katlı: boşa geçen süre + geri gelmeyen
   kota.

   Soğutma tek bir 503'e DEĞİL, modelin TÜKENMESİNE bağlıdır (`_gecici_sogut`, hem
   tur tükenişinde hem süre bütçesi dolduğunda): havuzdan biri çevirebildiyse
   doygunluk yok demektir ve 2026-09-09 ölçümü 503'ün tek anahtarda çıkarken
   diğerlerinin AYNI ANDA açık dönebildiğini göstermişti. Süre ÜSTEL artar
   (`GECICI_SOGUMA_TABAN_SN` 60 sn → `GECICI_SOGUMA_TAVAN_SN` 900 sn), çünkü
   doygunluk saatlerce sürüyor ama ara ara açılıyor (aynı gün 09:44-19:38 sürekli
   503, arada 13:31'de bir başarı): sabit kısa süre kotayı yakar, sabit uzun süre
   toparlanma anını kaçırır. **BAŞARIDA sayaç sıfırlanır** — tek bir kötü dalga
   günün kalanında modeli sebepsiz uzakta tutmamalı. Sayaç MODEL başınadır
   (doygunluk modele ait), soğuma ise kota soğumasıyla aynı (anahtar, model)
   kabında durur. Soğumanın SEBEBİ (`_SOGUMA_SEBEBI`) hata mesajında ayırt edilir:
   "kota soğumasında" diyen bir mesaj, yoğunluktan soğuyan anahtarda kullanıcıyı
   arızayı kota tarafında aramaya iterdi.

   Denge iki ayrı yanlıştan sonra bulundu, ikisi de ölçüldü:
   * **Anahtar başına 3 deneme + uyku** → zincirin tamamı 503 verdiğinde 5 anahtar x
     2 model = 30 istek ve **60 sn UYKU** (üç modelli zincirde 90 sn). Kullanıcı:
     "aşırı yavaş çeviriyor, çok uzun süre bekliyor."
   * **Uykuyu TÜMDEN kaldırmak** → 10 deneme saniyeler içinde tükeniyor ve zincir pes
     ediyor. Gerçek vaka (2026-09-10): 15 bölümlük toplu çeviri ikinci bölümde
     "Tüm modeller şu anda meşgul" ile durdu. Google'ın 503 gövdesi "Spikes in demand
     are usually temporary. Please try again later." diyor — beklemek BAZEN doğru cevap.

   Bugünkü hâl aynı senaryoda 30 istek / **12 sn uyku**: havuzu kullanır ve dalgayı
   bekler. Ölçüm `scratch/` altındaki maliyet betiğiyle API harcamadan tekrarlanabilir. Bu dal eskiden
   doğrudan sıradaki MODELe iniyordu ve gerekçesi ("arıza Google tarafında, anahtar fark
   etmez") ÖLÇÜMLE ÇÜRÜDÜ: 5 anahtar x 3 tur canlı yoklamada 503 tek bir anahtarda
   çıkarken diğerleri AYNI ANDA açık dönüyordu. Eski kural tek geçici 503'te o modeldeki
   kalan bütün sağlam anahtarları iptal ediyordu; iki model üst üste böyle atlanınca
   okuma zincirin dibine iniyordu (kullanıcı şikâyeti: "5 anahtar var ama lite'a düşüyor").
3. **Erişim (404) → aynı MODELDE sıradaki ANAHTAR** (2026-09-15, ölçümle DÜZELTİLDİ).
   Soğutma YOK (anahtar sağlam, o modeli görmüyor) ve tur tekrarı da YOK (erişim
   beklemekle açılmaz — 404 `turda_gecici` işaretlemez, yoksa her bölüm zincir
   başına boşuna 6 sn yakardı). Havuzun tamamı 404 verirse sıradaki MODELe inilir.

   Bu dal eskiden doğrudan sıradaki MODELe iniyordu ve gerekçesi ("404 model yok
   demektir, ikinci anahtar da aynı cevabı verirdi") projenin KENDİ ölçümüyle
   çürüktü — `kota_durum.py` 2026-09-06'da şunu yazmıştı: 3. anahtar
   `gemini-2.5-flash`'a 404 derken 1. ve 2. anahtar AÇIK dönüyordu. **Model erişimi
   de kota gibi PROJE başınadır, yani ANAHTAR başına değişir.** Eski kural tek bir
   404'te o modeldeki kalan bütün SAĞLAM anahtarları iptal ediyordu.

   Arıza 2026-09-15'te gerçekleşti: zincirin İKİ halkası da (3.6-flash, 3.5-flash)
   aynı anahtarda 404 alınca çeviri TÜMDEN durdu — kullanıcının BEŞ anahtarı vardı,
   dördü çalışıyordu ve hiçbiri denenmedi. Bu, 503 dalında 2026-09-09'da düzeltilen
   hatanın AYNISIDIR; o tur 404'ü atlamıştı. **Yeni bir hata sınıfı eklerken sor:
   bu arıza anahtara mı bağlı, modele mi — ölç, varsayma.**
4. **Anahtar reddi (401/403, 400 `API_KEY_INVALID`) → aynı MODELDE sıradaki
   ANAHTAR** (2026-09-18, kullanıcı kararı). 404 ile aynı muamele: soğutma yok, tur
   tekrarı yok. Eskiden bu dal `TranslateError` ile zinciri TÜMDEN öldürüyordu;
   rotasyon açıkken tek bir iptal edilmiş anahtar her beş bölümden birini
   çevrilemez kılardı. Sıradan 400 (bozuk istek) hâlâ çeviri hatasıdır — her
   anahtarda aynı cevabı verir. Havuzun tamamı yalnız erişim/red verdiyse mesaj
   "meşgul" DEMEZ, "anahtarlar kabul edilmedi" der (`_zincir_hatasi`).
5. **Kalan her arıza → sıradaki MODEL.** Boş/engellenmiş yanıt (safety)
   deterministiktir → bir alt model (başkası çevirebilir).

**API GÖZLEM KAYDI** (2026-09-18, `app/core/api_durum.py`). "3.6 seçiliyken neden
3.5?" sorusu bir dönem TAHMİNLE cevaplanıyordu: veritabanında yalnız bölümü fiilen
çeviren model vardı, zincirin NEDEN indiği hiçbir yerde yoktu, çeviri yolunda tek
satır log yoktu. Sunucu verisinde iki desen görüldü (dakikalar içinde geri dönen tek
tük düşüşler + gece yarısı 8 bölümlük düşüş) ve ikisi ayırt EDİLEMEDİ. Artık her
GERÇEK Gemini çağrısı `_tek_anahtarla_uret`te TEK kez kaydedilir (sınıf, HTTP kodu,
süre, token, kota türü/sınırı), soğuma atlamaları ayrı olay olarak yazılır (sayaca
GİRMEZ) ve ilk halka dışına her iniş nedeniyle kaydedilir (`gecis_kaydet`, anahtar
başına SON sonuç). Okuma: `scripts/api_durum_rapor.py` (Google'a istek ATMAZ;
`kota_durum.py` atar). Kurallar:
* **Anahtar değeri yazılmaz** — kimlik SHA-256 özetinin başı; sıra kimlik DEĞİLDİR.
* **Kayıt hatası çeviriyi başarısız kılmaz** (`_sessiz`); ham gövde/istem saklanmaz.
* **Yazım `BEGIN IMMEDIATE`** (`_yazim`): örtük ertelenmiş işlem WAL'da paralel
  yazarlar arasında BEKLEMEDEN "database is locked" veriyordu — ölçüldü, iki
  eşzamanlı istekten birinin kaydı kayboluyordu.
* **Bağlam `contextvars` ile** (`islem`/`baglam`): amaç giriş noktasında (server
  okuma/prefetch/web'den ekleme/sözlük önerisi, jobs toplu/yeniden çeviri), URL
  pipeline'da, onarım turları `asama` ile. `threading.Thread` bağlamı KOPYALAMAZ —
  elle açılan iş parçacığı bağlamı kendi içinde kurar. Yeni bir çeviri giriş
  noktası eklerken `api_durum.islem(...)` ile sar, yoksa kayıt "diger" der.
* **Soğuma yeniden başlatmaya dayanır**: bitiş UTC epoch olarak `api_son`'da durur,
  süreç anahtar listesini ilk gördüğünde (`_gemini_fabrikasi`) anahtar KİMLİĞİYLE
  eşlenip geri yüklenir; geçmiş bitiş engel sayılmaz, çıkarılan anahtarın soğuması
  yenisine taşınmaz.
* **Gün Pasifik günüdür** (kota orada sıfırlanır). Windows'ta `tzdata` paketi ŞART
  (requirements'ta): yoksa `ZoneInfo` patlar, sabit UTC-8'e düşülür ve yaz saatinde
  bir saat şaşar — testler bunu yakaladı.
Manga görsel yolu (`import_translate._manga_regions`) havuzu kullanmaz ve kayda
GİRMEZ (kullanıcı kararı: kapsam dışı).

**API DURUM PANELİ** (2026-09-18, `js/api-durum.js` + saf `js/api-durum-yardimci.js`).
Ayarlar → "API durumu" ayrı bir GÖRÜNÜMDE açılır (`view: "apidurum"`, iç içe modal
yok); geri düğmesi ve telefonun geri tuşu ayarlara döner. Üç salt-okunur uç:
`GET /api/settings/api-status` (kartlar, sayaçlar, soğuma), `/api-events` (sayfalı
geçiş listesi, `cursor`), `/api-neden?url=` (künye rozetindeki "Neden bu model?").
Kurallar:
* **Uçlar Google'a istek ATMAZ**, rotasyonu ilerletmez, anahtar değeri ya da
  KİMLİĞİ döndürmez (yalnız "Anahtar N"; `.env`'den çıkarılan anahtar "Çıkarılmış
  anahtar"). `Cache-Control: no-store` ve **SW bu yolları önbelleğe ALMAZ**
  (`sw.js`'de genel `/api/` dalından ÖNCE) — çevrimdışı bayat "başarılı" yanlış bilgidir.
* **Soğuma panelde çeviri yolunun BELLEĞİNDEN okunur** (`translate.aktif_soguma_bitisleri`,
  önce kayıttan geri yükler): ikinci bir kaynak "soğumada" derken çeviri o anahtarı
  deniyor olurdu. Kart durumu ve "neden" kararı SUNUCUDA (`kart_durumu`,
  `model_nedeni`); arayüz yalnız biçimler. Soğuma bitince durum "yeniden
  denenebilir"dir, başarılı istek olmadan "başarılı" DEĞİL.
* **"Neden" penceresi** (`NEDEN_PENCERESI_SN`): geçiş çeviri SIRASINDA, bölüm satırı
  çeviri BİTİNCE yazılır; bu pencerenin dışındaki geçiş ÖNCEKİ bir çeviriye aittir.
  Kayıt başlamadan çevrilmiş bölüm "geçmiş neden kaydedilmemiş" der — geriye dönük uydurma yok.
* **Yenileme** yalnız panel görünürken 15 sn'de bir, uçuşta olan varken yenisi
  atılmaz, bağlantı kopunca eski veri zamanıyla kalır ve "bayat" denir.
* **`popstate` SIRASI (ölçüldü):** Chromium pencere üzerindeki popstate
  dinleyicilerini capture/bubble ayrımına bakmadan KAYIT SIRASIYLA çağırıyor —
  `{capture: true}` "önce koş" demek DEĞİL. Panelin dinleyicisi görünüm değişmeden
  önce koşmalı; bu yüzden `app.js`'de `apiDurumKur()` `gezinmeKur()`'dan ÖNCE.
* Tarayıcı testleri (`tests/tarayici/test_api_durum.py`) beş anahtarlı görünümü
  `page.route` ile, 15 sn'lik aralığı `page.clock` ile sınar (test sunucusu
  anahtarsız). Sahte saati istek zaman aşımından (8 sn) uzun sarmak bekleyen
  isteği iptal eder.

**404'TE MESAJ "MEŞGUL" DEMEZ** (2026-09-15). Zincirin tamamı 404'ten düştüğünde eski
mesaj "Tüm modeller şu anda meşgul (geçici). Biraz sonra tekrar deneyin." diyordu ve bu
YANLIŞ TEŞHİSTİR: erişim beklemekle ASLA açılmaz. Kullanıcı mesaja uyup arızayı kota
tarafında aradı ("5 anahtarım var, kotanın dolması imkânsız"). Mesaj artık sebebi,
modelleri ve çıkışı (`scripts/kota_durum.py` + ayarlar panelinden model seçimi) söyler.
Aynı kural anahtarsızlık dalında ZATEN vardı; 404 dalı atlanmıştı — **hata mesajı
üreten yeni bir dal eklerken "kullanıcı bu mesaja uyarsa ne yapar" diye sor.**

**ANAHTAR ROTASYONU: her istek SONRAKİ anahtardan başlar** (2026-09-09, kullanıcı
isteği). Eskiden her istek DAİMA #1'den başlıyordu ve havuz ancak arıza hâlinde işe
yarıyordu. Ölçüm bedeli gösterdi: Gemini'nin ücretsiz günlük kotası model başına
**20 istek / PROJE** (429 gövdesinden okundu —
`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`), yani ilk anahtar
erken tükeniyor, sonraki HER istek önce ona çarpıp 429 yiyor, soğuma yazıyor ve ancak
sonra #2'ye geçiyordu. Beş anahtarlı havuzda bile yük tek anahtara yığılıyor, kotanın
dörtte beşi boşta duruyordu. Ofset istek başına BİR kez alınır (`_sonraki_baslangic`) ve
zincirdeki BÜTÜN modellere aynısı uygulanır; rotasyon sırayı kaydırır, KAPSAMI değil —
döngü yine tüm anahtarları gezer. **Soğumadaki anahtar başlangıç olarak seçilmez ve
sırayı da tüketmez**: döngü onu zaten atlıyordu, ama sayaç bir tur harcadığı için sağlam
anahtarlara eşitsiz dağılıyordu (üç anahtarın biri kotadayken dört istek kalan ikiliye
3/1 gidiyordu). Sayaç süreç
ömürlüdür, testler `anahtar_rotasyonunu_sifirla()` ile sıfırlar.

**ANAHTAR HAVUZU: birden çok Gemini anahtarı, sırayla** (2026-09-02, kullanıcı kararı).
`.env`'deki tüm Gemini anahtarları keşfedilir ve numarasına göre sıralanır
(`gemini_anahtarlari`); kota dolunca başka bir SAĞLAYICIYA değil başka bir ANAHTARA
geçilir. **UYARI — Gemini kotası PROJE başınadır, ANAHTAR başına DEĞİL:** aynı Google
Cloud projesinden üretilmiş iki anahtar aynı RPM/RPD havuzundan içer ve ikincisi hiçbir
şey kazandırmaz (birincisi 429 alırsa ikincisi de alır). Havuzun anlamlı olması için
anahtarlar AYRI PROJELERDEN gelmelidir. Değişken adı bilerek ESNEK
(`GEMINI_API_KEY`, `GEMINI2_API_KEY`, `GEMINI_API_KEY_3`…): tek bir kanonik ad dayatmak,
`.env`'i elle düzenleyen kullanıcının anahtarı sessizce görünmez kılmasına yol açardı ve
arıza "kota dolu" kılığına girerdi.

**Kota durumu: `scripts/kota_durum.py`.** "Kotam doldu mu, ne zaman açılır" sorusu
tahminle cevaplanamaz — 429 İKİ ayrı sınırdan gelir ve açılma süreleri farklıdır.
Araç her anahtar x her model için yoklar ve 429 gövdesindeki
`QuotaFailure.violations[].quotaId`'yi okuyup DAKİKALIK mı GÜNLÜK mü olduğunu
söyler, `RetryInfo.retryDelay`'i de basar. GÜNLÜK kota Pasifik gece yarısı sıfırlanır
(yaz saatinde TSİ 10:00, kışın 11:00); araç yerel saate çevirip yazar.

UYARI: araç KÜÇÜK bir istek atar, yani RPM/RPD'yi yoklar ama TPM'i (dakikadaki
TOKEN) YOKLAMAZ. Gerçek çeviri isteği ~8.000 giriş token'ı taşır; "AÇIK" sonucu
"kota tamamen boş" demek DEĞİLDİR.

Araç ayrıca PROJE AYRILIĞI ipucu verir: iki anahtarın model erişimi FARKLIYSA
(biri bir modele 404 derken öteki demiyorsa) projeleri kesinlikle ayrıdır, yani
kotaları da ayrıdır. Erişim AYNIYSA bu bir kanıt değildir — anahtardan proje
okunamaz. Ölçülen gerçek vaka (2026-09-06): 3. anahtar `gemini-2.5-flash`'a 404
verdi, 1. ve 2. vermedi — 3. anahtarın projesi kesin ayrı, 1-2 arası belirsiz.

Kota dolan anahtar **soğumaya** alınır, çünkü bir bölüm birden çok parça = birden çok
istek ve her parça o anahtara boşuna bir tur daha atardı.

**Soğuma süresi kotanın TÜRÜNDEN gelir** (2026-09-09, kullanıcı isteği). 429 iki ayrı
sınırdan gelir ve HTTP kodu ikisinde de aynı, ama ayrım gövdededir:
`QuotaFailure.violations[].quotaId` içinde `PerDay` varsa GÜNLÜK (RPD), yoksa DAKİKALIK
(RPM/TPM). `translate.gunluk_kota_mi` bunu okur; günlükse soğuma Pasifik gece yarısına
kadar (`pasifik_gece_yarisina_kalan`), değilse `ANAHTAR_SOGUMA_SN` = 60 sn. Gövde
ayrıştırılamazsa DAKİKALIK varsayılır — bir dakika erken denemek, anahtarı gün boyu
kaybetmekten ucuzdur. Süre eskiden sabit 60 sn'ydi ve günlük kotası dolan anahtar
DAKİKADA BİR yeniden deneniyordu: her bölüm ona bir boş istek daha atıyordu.

Ayrıştırma `scripts/kota_durum.py` ile PAYLAŞILIR (araç `translate._hata_govdesi` ve
`gunluk_kota_mi`'yi çağırır); ikinci bir kopya, araç "GÜNLÜK" derken çeviri yolunun 60 sn
sonra yeniden denemesi gibi sessiz bir ayrışma üretirdi.

Soğuma **MODEL BAŞINADIR**: günlük kota model başına ayrı tutulduğu için
3.6-flash'ta tükenen anahtar 3.5-flash'ta hâlâ çalışır; tek bir "anahtar bitti" bayrağı
çalışan halkaları da kapatırdı. Testler `tests/test_gemini_anahtarlari.py`.

**NVIDIA HALKASI: `z-ai/glm-5.3`, ÜCRETSİZ, ZİNCİRİN SONU** (2026-09-26, kullanıcı
kararı). build.nvidia.com'un OpenAI uyumlu ucu, `NVIDIA_API_KEY`. Gerekçe dayanıklılık:
3.x ile 2.5 ayrı nesil ama AYNI sağlayıcı, Google tarafındaki bir erişim/kota arızası
hepsini birlikte düşürebilir. Aşağıdaki "Gemini dışı sağlayıcılar kaldırıldı" kararının
TERSİNE bu halka önce ÖLÇÜLDÜ (`scratch/nvidia_kiyas.py`, 3 gerçek bölüm, tek geçiş,
onarımsız): oran medyanı 3.6-flash 0,996 · **glm-5.3 0,966** · kimi-k3 0,957 ·
nemotron-3-ultra 0,933 (düşünmeyi kısmıyor, çıkışın 3 katı); glm-5.3 hizalama 3/3,
SIFIR ihlal ve kalıntı, bölüm başına **138 sn** (106-166). Aynı katalogda elenenler:
deepseek-v4.1-flash 150 sn'de içerik üretmedi, gpt-oss-20b zaman aşımı, glm-5.3-flash 3
bölümün yalnız birini 300 sn'de çevirdi, kimi-k2.6 ve mistral-large-2 404.
**Kısa yoklama hızı uzun isteği temsil ETMEZ** (kimi-k3 kısa istekte ilk token 1,7 sn,
tam bölümde 180 sn). SONA konur: 3.6 daha iyi ve glm yavaş. Sürpriz fatura riski
YAPISAL olarak yok: NVIDIA ücretsiz katmanı kartsız hesaptır, sınırda 429 döner.
Kullanım şartı "geliştirme/test/değerlendirme" — 7/24 okuma trafiği bu tanımın sınırında.
Üç kural (`translate._nvidia_uret`): **akışlı** istek (akışsızda sunucu üretim boyunca
bayt yollamıyor, zaman aşımı yavaşlığı kuyruktan ayıramıyordu; parça arası 180 sn,
toplam 480 sn tavan) · **tek anahtar, TEK deneme** (başarısız deneme dakikalar
sürebiliyor; 429/5xx/taşıma geçici sayılır, 429 Google'ın kota gövdesi
ayrıştırılmasın diye 503'e çevrilir) · **`api_durum` kaydına GİRMEZ** (kayıt Gemini
anahtar x model tablosudur; `translate.gemini_modeli` ayırır, panel ve
`kota_durum.py` yalnız Gemini modellerini gösterir). Künyede motor `nvidia`.
Testler `tests/test_nvidia_halkasi.py`.

**VERTEX HALKASI: `vertex/gemini-3.6-flash`, ÜCRETLİ, YALNIZ SEÇİLİNCE** (2026-09-26,
kullanıcı kararı). Google Cloud deneme kredisi (~300 $ / 14.440 ₺, 90 gün, hesap
2026-09-11'de açıldı → ~2026-12-10'a kadar) AI Studio anahtarlarına HARCANAMIYOR: 2 Mart
2026'dan sonra açılan hesaplarda kredi yalnız Vertex AI'da geçer. Vertex aynı 3.6-flash'ı
günlük 20 istek sınırı olmadan sunuyor. Kurulum sunucu projesinde (`My First Project`,
`project-b09dd2ba-…`): Vertex AI API açık, VM servis hesabına `cloud-platform` kapsamı
(VM durdurulup başlatıldı — dış IP değişti) ve `roles/aiplatform.user`. **Anahtar dosyası
YOK**: kimlik metadata sunucusundan gelir, `.env`'de yalnız `VERTEX_PROJE` durur. Emniyet
Claude'la aynı yönde: ücretsiz zincir ASLA Vertex'e inmez (`DEFAULT_MODELS`'te yok), yalnız
açıkça seçilince başa geçer. Claude'dan farkı TERS yön: Vertex çeviremezse ücretsiz Gemini
halkalarına düşülür (künye fiilen çevireni yazar, para harcanmaz). Çağrı ayarları AI Studio
yoluyla TEK yardımcıdan gelir (`_gemini_yapilandirmasi`); tokenlar (düşünme dahil) harcama
göstergesine yazılır (`kullanim.FIYAT`, 0,75/3,75 $ tanıtım fiyatı — 2027'den 1,50/7,50),
`api_durum`'a yazılmaz. **Kredi bitince ya da süresi dolunca** hesap ücretliye
yükseltilmişse gerçek fatura başlar — modeli ücretsiz bir Gemini halkasına geri almak
gerekir. **AI Studio'daki ücretsiz projelerde "Set up billing"e BASILMAZ**: o projenin
ücretsiz kotası biter ve anahtarı sessizce ücretli olur. Testler `tests/test_vertex_halkasi.py`.

**GEMİNİ DIŞI SAĞLAYICILAR KALDIRILDI** (2026-09-02, kullanıcı kararı; 2026-09-26'da
yukarıdaki NVIDIA halkası ÖLÇÜLEREK istisna oldu). Bir dönem zincirde
OpenAI-uyumlu üç sağlayıcı vardı (`openrouter:minimax/minimax-m3:free`,
`mistral:mistral-medium-latest`, ayrıca Groq/Cerebras kod desteği). Hepsi zincire KOTA
gerekçesiyle girmişti, kaliteyle değil, ve ölçüm tersini söyledi — bkz. aşağıdaki uzunluk
oranı bulgusu. Taşıdıkları yük de bedavaya gelmiyordu: ikinci bir düşme kuralı, sağlayıcıya
özel token tavanları ve OpenRouter'ın `:free` sonekinin sessizce PARAYA dönme riski (sonek
düşerse istek yine 200 döner, hiçbir hata görünmez, yalnız fatura işler — gerçek vaka: bu
projenin ilk kıyas turları hesapta 0,05 $ yaktı). Kotanın yerini anahtar havuzu aldı.
Geri eklenmesi düşünülürse ölçüm kayıtları: minimax uzunluk oranı medyanı 22 bölümde
**0,949** (22'sinin 22'si de 0,98'in ALTINDA) · mistral-medium **0,914** · Groq ücretsiz
TPM 8.000'e karşı bu projenin girdisi tek başına 5.061 token (tüm sohbet modelleri 413) ·
Cerebras ücretsiz bağlamı 8.192 token, aynı duvar. `translate.OPENAI_UYUMLU`,
`_openai_uyumlu_uret`, `_onek_ayir` ve `<sağlayıcı>:<model>` yönlendirmesi tümüyle kalktı;
`tests/test_gemini_anahtarlari.py` geri gelmelerini tutan bir tel tuzağı taşıyor.

**UZUNLUK ORANI birincil kalite ölçütüdür** (2026-09-02, kullanıcı şikâyeti + ölçüm).
Türkçe çıktı / İngilizce kaynak karakter. Sebebi somut: hizalama ve `sozluk_ihlalleri`
"terimi doğru yazdın mı" diye sorar, "cümleyi eksiksiz kurdun mu" diye SORMAZ — minimax
ikisinden de SIFIR hatayla geçtiği hâlde metni sistematik olarak kısaltıyordu ve şikâyet
("çeviriyi düzgün yapmıyor") ancak bu ölçütle doğrulanabildi. Önbellekteki gerçek üretim
verisi: `gemini-3.6-flash` 76 bölümde medyan **0,972** · minimax 22 bölümde **0,949** ·
mistral-medium **0,914**. Aynı bölümde kontrollü koşu (shadow-slave 123): 3.6-flash 0,939 ·
minimax 0,922. **Yeni bir model önerirken uzunluk oranını da ölç** — hizalama+sözlük
ikilisi bu kusuru göstermiyor.

**Model kıyası: `scratch/gemini_kiyas.py`** (2026-09-02). Gemini modellerini kendi
aralarında ölçer: gerçek prompt (`_build_user_prompt`), gerçek sözlük, İKİ ayrı kitaptan
gerçek bölümler. Kısa uydurma metinle yapılan doğrulama "çalışıyor mu" sorusunu cevaplar,
"iyi mi" sorusunu CEVAPLAMAZ (Mistral dersi). Ölçütler projenin KENDİ deterministik
fonksiyonlarındandır (`_split_by_markers`, `sozluk_ihlalleri`); kopyalanırsa ikinci bir
kural kümesi doğardı. Akıcılık ölçülmez, okunur — çeviriler `scratch/kiyas_ciktilari/`
altına yazılır. **Takma adlar (`gemini-flash-latest`) zincire konmaz**: hareketli hedeftir,
ölçtüğümüz model bir gün sessizce başkası olur.

**`gemini-2.5-flash` EKLENDİ, `gemini-3-flash-preview` ÖLÇÜLEREK ELENDİ**
(2026-09-06, kullanıcı isteği + ölçüm). 2.5 O GÜN yalnız seçilebilir listeye girdi,
`DEFAULT_MODELS` zincirine DEĞİL. Ayrım load-bearing: seçilebilir liste bir
TEKLİFTİR, zincir ise hiç kimse seçim yapmadığında herkesin düştüğü yoldur —
ölçülmemiş bir modeli zincire koymak, ayarı hiç açmamış kullanıcının çevirisini
sessizce değiştirirdi. **Listeye eklemek zincire eklemek değildir; zincire giriş
ayrı bir karar ister.** (Bugün listede olup zincirde OLMAYANLAR bunun kanıtı: 3.8
ve 3.7 uzun bölümleri 503 ile reddediyor, Claude ise ücretli.)

**2.5-flash ZİNCİRE TERFİ ETTİ — ÜÇÜNCÜ ve SON halka** (2026-09-15, kullanıcı
kararı; yukarıdaki kaydı GÜNCELLER). Gerekçe bir arıza: zincirin iki halkası da
3.x AİLESİNDENDİ (`3.6-flash`, `3.5-flash`) ve o aile kullanıcının anahtarlarına
404 dönmeye başlayınca ayakta kalan hiçbir halka kalmadı — çeviri TÜMDEN durdu.
2.5 o gün çalışan tek modeldi ama yalnız listede olduğu için, ancak ayarı açıp
elle seçen kullanıcı çeviri yapabildi.

**Ders: zincirin dayanıklılığı halka SAYISINDAN değil, halkaların BİRLİKTE
ölmemesinden gelir.** Aynı ailenin iki sürümü ortak bir kaderi paylaşır — aynı
erişim politikası, yakın kota havuzları. Farklı nesilden bir halka bunu kırar;
2.5'in kotası 3.x'ten ayrıdır. `tests/test_ceviri_yolu.py` zincirin kazara
yeniden TEK AİLEYE daralmasını bir tel tuzağıyla tutar.

2.5 **SONA** konur, başa değil: ölçümde 3.6-flash hâlâ daha iyi (uzunluk oranı
0,972 / 0,932), yani 3.x çalışırken davranış birebir eskisi gibi kalır ve 2.5'e
ancak üst halkalar elendiğinde inilir. Başa alınsaydı 3.x geri geldiğinde herkesin
çevirisi sessizce daha kötü bir modele kayardı. Künye rozeti fiilen çevirenin adını
yazdığı için inildiği gizlenmez. Bu, "zincire ÖLÇÜLMEMİŞ model koyma" kuralının
istisnası DEĞİL — 2.5 ölçülmüştü (oran 0,932, hizalama 3/3, 3 bölümde 1 sözlük
ihlali, ölçülenlerin en hızlısı); ölçülmemiş olsaydı yine listede kalırdı.

**`gemini-3-flash` diye bir ad YOK.** Yoklandı: `gemini-3-flash` ve
`gemini-3.0-flash` 404 dönüyor; çalışan ad `gemini-3-flash-preview`. Bu, projenin
"model adını LİSTEYE bakarak seçme, YOKLA" kuralının bir kez daha işe yaradığı yer.

Ölçüm (`scratch/gemini_kiyas.py`, 3 gerçek bölüm, iki kitap):

| model | uzunluk oranı | hizalama | sözlük ihlali | süre |
|---|---|---|---|---|
| `gemini-3.6-flash` (taban) | 0,952 | 3/3 | 0 | 49 sn |
| `gemini-2.5-flash` | 0,932 | 3/3 | 1 | **45 sn** |
| `gemini-3-flash-preview` | **0,436** | **0/3** | 0 | 109 sn |

`gemini-3-flash-preview` bu iş yükünde ÇEVİRMİYOR, ÖZETLİYOR: 53-62 paragraflık
bölümlere 19-25 paragraf döndü, yani paragrafları birleştirip metnin yarısını attı.
Hizalama üçünde de kayboldu. **Zincir bunu KURTARAMAZ** — düşme yalnız HATADA olur
(429/503/404), başarılı ama kötü bir yanıtta olmaz; seçilseydi her bölüm böyle
çevrilir, iki dilli okuma ölür ve İngilizce-kalıntı denetimi de çalışamazdı
(hizalama ister). Bu yüzden LİSTEDEN ÇIKARILDI (kullanıcı kararı): sert bir uyarı
notu yetmez, çünkü seçenek listesi bir TEKLİFTİR ve teklif edilmemesi gereken tek
şey sessizce bozan bir yoldur. `tests/test_model_secimi.py` geri gelmesini bir tel
tuzağıyla tutar.

`gemini-2.5-flash` ise gerçek bir alternatif: oran 3.6-flash'a yakın, hizalama tam,
ve ölçülenlerin EN HIZLIsı. Kotası 3.x'ten ayrı olduğu için 3.x halkaları
tükendiğinde işe yarar.

Bu ölçüm aynı zamanda "yeni sürüm daha iyidir" sezgisinin bu projede kaç kez
yanlış çıktığının dördüncü kaydı (3.7, 3.8, 3.1-pro-preview, şimdi 3-preview).
Yeni bir model eklerken ÖNCE uzunluk oranını ve hizalamayı ölç.

**`gemini-3.7-flash` ve `gemini-3.8-flash` zincirde YOK** (3.7: 2026-08-23; 3.8:
2026-09-02, ikisi de ölçülerek). İkisi de bu projenin uzunluktaki isteklerini ısrarla
**503** ile reddediyor ve reddin bedeli sabit değil: ölçülen vakada 3.7 bir bölüm için
74 sn, bir başkası için **220 sn** yakıp yine reddetti (3.8 daha hızlı reddediyor, 5-15
sn). Üstüne üretim yolunda 503 aynı modelde 3 deneme + 6 sn uyku demek. Somut eski vaka:
Shadow Slave 1. bölüm "yeniden çevir" 1-2 dk sürdü ve künyeye `gemini-3.6-flash` yazıldı —
yani 3.7 reddetmiş, o süre tamamen boşa gitmişti. Ara sıra çalışması onları daha da kötü
bir İLK halka yapıyor: kazanç belirsiz, maliyet düzenli. Geri eklenecekse ÖNCE kalitesi
ölçülmeli; `tests/test_ceviri_yolu.py` ve `tests/test_gemini_anahtarlari.py` kazara geri
gelmelerini tutan tel tuzakları taşıyor.

**PARÇA BOYUTUNU DÜŞÜRMEK 503'Ü ÇÖZMEZ** (2026-09-21, ölçüldü). 3.x ailesi
doygunken "istek küçülürse model kabul eder mi" diye soruldu. `gemini-3.7-flash`
ile gerçek prompt kullanılarak altı boyut ölçüldü: 152 · 442 · 808 · 1210 · 1631 ·
2263 kelime (prompt 9.788 → 152.383 karakter). **ALTISI DA 503**, üstelik red
süreleri 0-10 sn — model isteği içeriğine bakmadan reddediyor, kuyruğa bile
almıyor. Ölçümden önceki hipotez tersiydi ve dayanağı yanıltıcı bir kıyastı:
çıplak `contents="hi"` isteği (~5 token, sözlüksüz) geçiyordu, ondan "küçük istek
geçiyor" sonucu çıkarılmıştı. Oysa GERÇEK prompt taşıyan en küçük istek bile
eşiğin üstünde: sabit yük (sistem talimatı 8.098 karakter + sözlük) tek başına
~8.800 giriş token'ı demek. **`MAX_WORDS_PER_CHUNK` düşürmek bu arızayı çözmez**,
yalnız kaliteyi düşürür (aşağıdaki parçalama ölçümü) — bir daha önerilirse bu
kayda bak.

**YENİ ANAHTAR ALMAK DAYANIKLILIK KAZANDIRMAZ** (2026-09-21, ölçüldü). Havuzdaki
beş anahtarın ikisi (1-2) hem 3.x hem 2.5 ailesini görüyor; **üçü (3-4-5) YALNIZ
3.x görüyor** — `gemini-2.5-flash`, `gemini-2.5-pro` ve `gemini-2.5-flash-lite`
üçünde de 404 ve sebep kalıcı: *"This model ... is no longer available"*, yani
2.x artık YENİ projelere sunulmuyor. Model `/v1/models` LİSTESİNDE beş anahtarda
da görünüyor, o liste genel katalogdur ve erişimi göstermez — "adı listeye bakarak
seçme, YOKLA" kuralının bir kez daha doğrulandığı yer. Sonuç: bugün açılan bir
Google Cloud projesinden alınan anahtar, 3.x doygunken HİÇBİR ŞEY çeviremez.
Havuzu büyütmek kota genişletir ama aynı kaderi paylaşan halkalar eklediği için
dayanıklılık eklemez; 2.5 erişimi olan ESKİ projeler bu yüzden değerlidir.

**PARÇALAMA KALİTEYİ İYİLEŞTİRMİYOR** (ölçüldü 2026-09-02). "Bölümü 3'e bölsek model daha
az atlar mı" hipotezi sınandı: aynı model, aynı bölüm, üç parça → oran 0,922'den 0,912'ye
DÜŞTÜ, süre 51'den 76 sn'ye çıktı, token ~1,8 kat arttı. Sebep prompt anatomisinde:
**%41-48'i SABİT yük** (sistem talimatı + 250-267 kayıtlık sözlük = 7.323
karakter) ve o kısım her parçada YENİDEN gider. Parçalama yalnız bağlam penceresi dar
katmanlara sığmak için bir araçtır, kalite aracı DEĞİL.

**Model adını LİSTEYE bakarak seçme, YOKLA**: `/v1/models` çıktısında görünen bir ad
ücretsiz katmanda çalışmayabilir (ölçülen vakalar: `mistral-large-latest` 403
`tier_not_allowed`, `gemini-3.1-pro-preview` / `gemini-pro-latest` 429). Aynı disiplin
`gemini-3.7-flash`ta bir kez çiğnendi ve düzenli gecikme + ölçülmemiş kalite ile geri
alındı. Ölçüm önce gelir.

**SÖZLÜK UYUM DENETİMİ ve bayrağı** (2026-08-30). Zincir yalnız ERİŞİLEBİLİRLİĞE bakarak
iniyordu ve kaliteyi hiçbir yerde ölçmüyordu; alt halkanın çevirisi sessizce kalıcı
önbelleğe yazılıp bir daha kontrol edilmiyordu. Ölçüm (Shadow Slave'in önbellekteki 110
bölümü): Türkçe karşılığı KAYITLI olduğu hâlde İngilizce kalan terim, 3.6-flash'ta 60
bölümde 5, 3.5-flash'ta 45 bölümde 1, **flash-lite'ta 4 bölümde 30**. Somut vaka: 109.
bölümü flash-lite çevirdi, `Saint -> Aziz` kaynakta 12 kez geçti ve 12'si de İngilizce
kaldı. `translate.sozluk_ihlalleri` çeviriden sonra bunu deterministik olarak ölçer
(API çağırmaz, bedava koşar); sonuç `chapters.glossary_leaks`'e yazılır ve okuyucuda
künye rozetinde ⚠ ile çıkar. Ölçüt prompt'a hangi terimlerin gireceğini belirleyen
ölçütle AYNI sabittendir (`_terim_metinde`); ayrışırlarsa prompt'a giren bir terim
denetimden kaçardı.

**OTOMATİK ONARIM VAR, TEK TUR** (2026-09-11, kullanıcı kararı — eski "otomatik
deneme yok" kaydının yerini aldı). Eski karar flash-lite gerekçesiyle alınmıştı
("lite'a zaten kota tükendiği için düşülmüştü") ve lite 2026-09-09'da zincirden
çıkınca gerekçe düştü. Tespit tek başına yetmiyordu: bayrak künyeye yazılıp ⚠
çıkıyor ama çeviri kalıcı önbelleğe BOZUK giriyor ve önbellek isabeti bir daha
çeviri tetiklemediği için kullanıcı o terimi SONSUZA DEK İngilizce görüyordu.
Onarım `_kalintiyi_onar` ile AYNI deseni izler: `sozluk_ihlali_paragraflari`
bozuk paragrafları bulur, `_paragraflari_yeniden_cevir` (iki onarım yolunun ORTAK
gövdesi) yalnız onları tek turda yeniden gönderir. Bayrak onarımdan SONRA ölçülür;
künyeye "onarıma rağmen kalan" yazılır.

**Ölçüm artık `translate_chapter`'da, pipeline TAŞIYICI.** `_uyum_denetimi`
eskiden ölçümü KENDİ yapıyordu ve `kosullar`ı hiç görmüyordu — koşullu kayıtlara
sahte ihlal yazardı. Denetim hizalamaya İHTİYAÇ DUYMAZ (düz metin karşılaştırması);
hizalama yalnız ONARIM için şarttır (hangi paragrafın bozuk olduğu ancak öyle
bilinir). Bayrağı üreten iki nokta var (`_fetch_translate_save` ve
`fetch_into_book`); künyeye yeni alan eklerken olduğu gibi İKİSİNİ de güncelle.
Geriye dönük araç (`scripts/uyum_denetle.py`) AYNI ölçütü kullanmalı ve koşulları
geçirmelidir — `tests/test_sozluk_ihlal_onarim.py` bunu tel tuzağıyla tutar.

DÖRT sınıf denetim DIŞIDIR: `X -> X` (İngilizce korunan kişi adları), bölümün
kaynağında geçmeyen kayıtlar, karşılığının İÇİNDE kaynağı geçen kayıtlar
(`Ore Empire -> Ore Empire Krallığı` — doğru çeviri bile deseni tetikler) ve
KOŞULLU kayıtlar: koşulun sağlanıp sağlanmadığı deterministik olarak ölçülemez,
koşulu yok saymak önce sahte bir ⚠ üretir sonra otomatik onarımın DOĞRU bırakılmış
özel adı zorla Türkçeleştirmesine yol açardı.

**SÖZLÜK, KİŞİ ADI İSTİSNASINI EZER** (2026-09-11, ölçüldü). Arıza: `Saint -> Aziz`
kayıtlı ve prompt'a giriyordu (`_terim_metinde` üç bölümde de True), buna rağmen
model terimi bölümden bölüme farklı çeviriyordu — shadow-slave #379/#380'de "Aziz",
#376/#378/#381'de "Saint". Kök neden MODELDE değil KURALDAYDI: `SYSTEM_INSTRUCTION`
"İngilizce korunacak TEK sınıf: bir KİŞİYİ ADLANDIRAN ifadeler" diyor ve
İngilizce-bırakma yasağına "Tek istisna yukarıdaki KİŞİ ADLARI kuralıdır" diye açık
bir KAÇIŞ KAPISI koyuyordu; sözlüğün o istisnayı ezip ezmediği hiçbir yerde
yazmıyordu. `Saint` kitapta hem bir rütbe hem bir gölge kölesinin adı olduğu için
model onu ad gördüğü an kapıdan çıkıyordu. Aynı prompt sistem terimleri için
önceliği ZATEN açıkça söylüyordu ("SÖZLÜK'te farklı bir karşılık verilmişse SÖZLÜK
geçerlidir") — çalışan örnekle bozuk örnek arasındaki fark tam buydu. Kural
kendinden FARKLI karşılığı olan kayıtlara özgüdür; kişi adları sözlükte kendi
yazımıyla durduğu için (`Sunny -> Sunny`, `merge_names`) onları etkilemez.

Eski bölümler için `scripts/uyum_denetle.py` (varsayılan KURU çalıştırma, `--uygula` ile
yazar, `--ayrinti` ile ihlalli bölümleri listeler). Ölçütü BUGÜNKÜ sözlük DEĞİL, o bölüm
çevrilirken sözlükte duran kayıtlardır (`glossary.bolumdeki_sozluk`, `first_chapter`
sütununu okur): 200. bölümde kaydedilmiş terim 50. bölümün prompt'unda yoktu, model onu
ihlal edemezdi. Köken taşımayan kayıt "her zaman vardı" sayıldığı için, sözlüğünün
`MIN_KOKEN_KAPSAMA`'dan azı kökenli olan kitapların sayıları GÜVENİLMEZDİR ve rapor bunu
açıkça söyler (gerçek veri: `reincarnation-of-the-strongest-sword-god`, 267 kaydın 267'si
kökensiz). Araç ayrıca hatalı SÖZLÜK kayıtlarını da yakalar: iyi bir modelin ısrarla
"ihlal ettiği" bir terim genellikle modelin haklı olduğunu gösterir (gerçek bulgu: elle
eklenmiş `Rock -> Taş`, oysa Rock bir karakter adı — kural gereği İngilizce kalmalıydı).

**İNGİLİZCE KALINTI: denetim + OTOMATİK ONARIM** (2026-09-05). Kullanıcı şikâyeti:
"bazı kelimeler veya cümleler İngilizce kalıyor". Ölçüm (önbellekteki 392 hizalı
bölüm, 21.411 paragraf) altı vaka buldu, ALTISI da `gemini-3.5-flash` — 3.6-flash
93 bölümde sıfır verdi. Arıza iki biçimde geliyor: paragrafın TAMAMI kaynakla
birebir aynı dönüyor (replik hiç çevrilmemiş), ya da paragraf çevrilmiş olduğu
hâlde cümle BAŞINDAKİ bağlaç/yardımcı fiil düşmüyor (`...But sadece birkaç
dakika`, `Was Neph... çalışıyor muydu?`) — Türkçede eke dönüşen `was` gibi
sözcükler modelin en sık atladığı yer.

**Kök neden denetimsizlikti, model değil.** Hizalama TUTUYORDU: `_split_by_markers`
yalnız YAPIYI doğrular (işaretler tam ve sıralı mı), `sozluk_ihlalleri` yalnız
KAYITLI terimlere bakar. İkisi de "bu paragraf Türkçe mi" sorusunu SORMUYORDU ve
prompt'un hiçbir maddesi paragrafın çevrilmiş olmasını istemiyordu — model
işaretçiyi doğru koyup metni olduğu gibi kopyalayınca hiçbir kural çiğnenmiyordu.
Sonuç kalıcı önbelleğe yazılıyor, önbellek isabeti bir daha çeviri tetiklemediği
için kullanıcı o paragrafı SONSUZA DEK İngilizce görüyordu.

Üç katman eklendi:
* **Önleme** — `SYSTEM_INSTRUCTION`'a açık madde: hiçbir paragraf İngilizce
  kalamaz, kaynak metin KOPYALANMAZ; `But/Then/And` ve `was/were/did` örnekli.
* **Denetim** — `translate.ingilizce_kalinti(tr_paras, en_paras, glossary)`.
  Deterministik ve API'siz (`sozluk_ihlalleri` gibi bedavaya koşar). İKİ ölçüt:
  BLOK (kaynakla ortaklık oranı >= `KALINTI_ORAN`, en az `KALINTI_MIN_TOKEN` aday
  token) ve SÖZCÜK (`ISLEV_SOZCUKLERI`'nden biri hem çeviride hem kaynakta).
* **Onarım** — `translate._kalintiyi_onar`, TEK tur. YALNIZ sızan paragrafları
  yeniden gönderir (tipik vaka 60 paragrafta 1), bölümün tamamını değil.

**Eşikler ölçülerek kondu, tahminle değil.** Ortaklık oranı dağılımında 0,7 ile
1,0 arasında HİÇ paragraf yok; eşik o boşluğa oturur. `KALINTI_MIN_TOKEN` şart:
kısa replikte (`"Sunny! Sunny! Uyan!"` ~ `"Sunny! Sunny! Wake up!"`) oran DOĞRU
çeviride bile 0,5-0,67'ye çıkıyor, çünkü özel ad + ünlem paragrafın tamamı oluyor.
Kalibrasyon sonucu: 6 gerçek vaka, **0 yanlış pozitif**.

**SAYI sözcükleri AYRI bir sınıftır** (2026-09-05, kullanıcı bildirimi). `ten times`
-> `ten kat`: model ölçü sözcüğünü çevirdi, sayıyı bıraktı (shadow-slave #201,
`gemini-3.6-flash`). Sayılar `ISLEV_SOZCUKLERI`'ne GİREMEZ çünkü o listenin kuralı
"Türkçe yazımı olan sözcük girmez" ve `ten` Türkçede cilt demek. Ama sızıntı gerçek
ve ötekilerden PAHALI: yanlış kalan bir sayı cümlenin anlamını değiştirir ve okurken
göze çarpmaz. Ölçüm sınıfın güvenle ayrılabileceğini gösterdi: sayı sözcüklerinin
korpustaki 112 geçişinin TAMAMI özel ad parçasıydı (`Solitary Nine`, `Ninth Heaven`,
`Thousand Transformations`, `Hundred Flowers Pavilion`) ve hepsi BÜYÜK harfliydi;
tek gerçek sızıntı küçük harfliydi.

`SAYI_SOZCUKLERI` bu yüzden İŞLEV sözcüklerinden FARKLI bir guard taşır: sonraki
sözcük büyük harfliyse ad başlangıcıdır ve elenir. **Bu guard işlev sözcüklerine
UYGULANAMAZ** — gerçek vaka `Was Neph...` tam olarak o desendedir (sonraki sözcük
büyük harfli bir kişi adı) ve aynı guard onu sessizce elerdi. İki sınıfın guard'ları
bilerek ayrıdır; birleştirme.

Korpus temelli genel tarama da yapıldı (bir token Türkçeyse, kaynağında o token
GEÇMEYEN paragraflarda da görünür; sızıntıysa görünmez). 69 küçük harfli adayın
tamamı meşru çıktı: Türkçe alıntı sözcükler (`metal`, `platform`, `form`, `risk`),
bilerek korunan yabancı terimler (`kunai`, `tachi`, `dantian`) ve tireli özel ad
parçaları (`All-rounded Device`, `Lightning-horned Earth Dragon`). Yani `ten`
dışında kapatılacak sınıf KALMADI — ve yöntem `ten`'i yapısal olarak bulamaz,
çünkü eş sesli bir Türkçe sözcüğü vardır. Yeni bir sızıntı sınıfı aranacaksa bu
taramayı tekrarla (`n_siz == 0` ölçütü), eş sesli sınıfları elle ekle.

`ISLEV_SOZCUKLERI` bilerek DAR: Türkçe'de de var olan yazımlar ELENMİŞTİR. `not`
("not etmişti") ve `has` ("kendine has") tek başına 126 sahte vaka üretmişti; `of`
Türkçe ünlem "Of!" ile çakıştığı için yok. **Listeyi genişletirken ölçüt: sözcüğün
Türkçe bir yazımı VAR MI — varsa girmez.** Üç eleme daha var, üçü de ölçülmüş
yanlış pozitiften geliyor: sözcük kaynakta geçmiyorsa Türkçedir · çeviride BÜYÜK
harfli ve cümle başında değilse özel adın parçasıdır (`Glorious Will` -> `Will`) ·
çok kelimeli bir sözlük kaydının İÇİNDEyse sızıntı değildir (`Auro of the Nine`
-> `the`). Cümle başı / özel ad ayrımı load-bearing: onsuz `Was Neph...`
vakasındaki `Was` "özel ad" sayılıp elenirdi.

**Onarım TEK turdur ve sözlüğe YAZMAZ.** Sızıntı modelin dikkat kaymasıdır; kısa,
odaklı bir istek onu çoğunlukla düzeltir (ölçüm: 6/6). Düzeltmiyorsa döngü kurmak
yalnız maliyeti — ücretli model seçiliyken PARAYI — katlar; onarılamayan sızıntı
`chapters.ingilizce_kalinti`'ye yazılır ve okuyucuda ⚠ rozetiyle görünür. Onarımın
sözlüğe kayıt eklememesi de bilinçli: tek bir paragraftan çıkan öneri, bölümün
tamamını görerek verilmiş özgün kararla çelişebilir ve sözlük kaydı sonraki BÜTÜN
bölümlerde KURAL olarak uygulanır.

Eski bölümler için `scripts/kalinti_onar.py` (varsayılan KURU çalıştırma;
`--isaretle` yalnız bayrak yazar ve API'siz koşar, `--uygula` yeniden çevirir).
Kaynak önbellekten okunur — siteye YENİDEN İNİLMEZ. Onarım aracı çeviri yolundaki
`_kalintiyi_onar`'ı AYNEN çağırır; ikinci bir onarım kuralı yazmak iki yolun
zamanla ayrışması demekti (bu projede künye alanları tam olarak böyle ayrışmıştı).
Araç künyeyi de tazeler (`cache.set_translation(model=…, engine=…)`), yoksa rozet
paragrafı fiilen onaran halkayı gizlerdi.

**Bayrağı üreten noktalar** `glossary_leaks` ile AYNI ikilidir:
`_fetch_translate_save` ve `fetch_into_book`. Yeni bir çeviri yolu eklenirse
İKİSİNİ de güncelle — `model` alanında tam bu hata yaşandı. NULL (hiç
denetlenmedi) ile `{}` (denetlendi, temiz) AYRIDIR.

`SAFETY_SETTINGS` = `BLOCK_NONE`, `max_output_tokens` açıkça verilir
(sessiz kesilme → bozuk JSON → hizalama kaybı). Çıktı JSON
`{translation, detected_names}`; bozuk/yarım JSON için kurtarma ayrıştırıcısı.
Prompt'a giren bağlam: `prev_context` — önceki BÖLÜMÜN son ~160 kelimelik Türkçesi
(`cache.prev_translation`), sahne sürekliliği bölüm sınırında kopmasın diye.

**ÜSLUP NOTU KALDIRILDI** (2026-09-02, kullanıcı kararı: "boşuna token harcamasın").
Kitap başına serbest bir üslup notu (`books.style_note`) her çeviri prompt'una
giriyordu. Ölçüm kararı verdi: HİÇBİR kitapta yazılı değildi, yani satır her istekte
`(yok)` diye gidiyordu — 36 token, girişin %0,4'ü. Token kazancı ihmal edilebilir
(maliyetin %75'i ÇIKIŞTAN geliyor, bkz. aşağıdaki Claude ölçümü); asıl gerekçe ölü
özellik: okuyucudaki kutu, uç (`/api/book/{slug}/style`), `library.set_style_note` ve
prompt maddesi hep birlikte kaldırıldı. YARIM kaldırma bilinçle reddedildi — kutuyu
bırakıp prompt'tan çıkarmak, kullanıcının not yazıp hiçbir şey olmadığını fark
etmediği SESSİZ bir arıza üretirdi. `books.style_note` SÜTUNU duruyor (SQLite'ta
sütun düşürmek zahmetli, veri zaten boş) ama hiçbir kod okumuyor.

**`app/core/cache.py`** — `chapters` tablosu: çevrilmiş bölümlerin URL-anahtarlı
kalıcı önbelleği. Cache isabeti = API çağrısı yok, anahtar gerekmez.

**`app/core/library.py`** — Sunucu-taraflı **paylaşılan kütüphane** (`books` +
`aliases`): PC ve telefon aynı kitap listesini ve okuma konumunu (`current_ratio`)
görür. `merge_books`/`resolve_slug`: aynı kitabın farklı sitelerdeki slug'larını tek
**kanonik slug**'a bağlar (bölüm + glossary tek kitapta toplanır).

**`app/core/glossary.py`** — Kitap-başına terim eşlemesi (kaynak→karşılık). Özel adlar
çeviri sırasında OTOMATİK eklenir (`pipeline._sozluge_isle`), **iki sınıf iki davranış**:
**bir KİŞİYİ ADLANDIRAN ifade** (`detected_names`) → İngilizce kalır (`merge_names`,
`X -> X`) ve İngilizce kalan TEK sınıf budur; **kişi adlandırmayan HER özel ad**
(`detected_terms`: yer, lonca, eşya, beceri/büyü, kategori unvanı, ırk, adlandırılmış
canavar, sistem terimi…) → modelin çeviride kullandığı Türkçe karşılıkla sabitlenir
(`merge_terms`). **Kişi sınıfına gerçek adın yanında LAKAP da girer** (2026-08-23):
gerçek adı bilinmeyen birini ad yerine geçerek adlandıran sözcük (`Scholar`, `Shifty`,
`Hero`). Sınıf eskiden "gerçek kişi/karakter adları" idi ve unvanı açıkça çevrilecekler
arasında sayıyordu; model bu lakapları harfiyen unvan sayıp Türkçeleştirdi (Shadow Slave
6. bölüm: `Kurnaz`, `Bilgin`, `Kahraman`), karşılık sözlüğe KURAL olarak yazıldı ve
7. bölüm de ona uydu — model bunları `detected_names`'e hiç önermediği için süzgeçlerin
eleyeceği bir şey yoktu, boşluk KURALDAYDI. Ölçüt (`translate.LAKAP_KURALI`) bilerek DAR:
büyük harfli + TEK belirli kişiyi gösteren + önünde `a/an/the` OLMAYAN sözcük lakaptır;
belirteç alan ya da sınıf anlatan (`an Aspirant`, `the Awakened`) çevrilir — gevşek bir
kural sistem terimlerini İngilizce'ye kaçırırdı, bu daha büyük bir zarar. **Ölçüt üç
talimatta da AYNI sabitten gelir** (çeviri, okurken terim önerisi, bakım aracının
sınıflandırması); ayrışırlarsa aynı kitapta iki politika oluşur. Kutu eskiden yalnız lonca+yer
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
Sözlük YALNIZ yeni çevrilen bölümde etkilidir.

**KOŞULLU SÖZLÜK KARŞILIĞI** (2026-09-06, kullanıcı isteği + ölçüm). Sözlük düz bir
`kaynak -> karşılık` eşlemesiydi ve aynı İngilizce sözcüğün BAĞLAMA göre iki farklı
Türkçe karşılığı olduğu durumu İFADE EDEMİYORDU. Ölçülen vaka: Shadow Slave'de
`Great` bir Kabus Yaratığı RÜTBESİ ("Dormant, Awakened, Fallen, Corrupted, Great,
Cursed, Unholy") ve `Ulu` olmalı; insan tarafındaki eşdeğer rütbe `Supreme` ise
`Yüce`. İkisi de "Yüce"ye eşlenmişti, ayrım kaybolmuştu.

**Düz bir `Great -> Ulu` kaydı çözüm DEĞİLDİ ve ölçüm bunu gösterdi.** Önbellekteki
32 geçişin ~17'si rütbe, **~12'si gündelik İngilizce** (`Great!`, `Great job`,
`Great people`). Sözlük karşılığı prompt'ta KURAL olduğu için düz kayıt o on ikisini
de "Ulu!" yapardı — bir sorunu çözerken on ikisini açardı. Çok kelimeli kayıtlar
(`Great Devil` gibi) da yetmiyordu: rütbe dizisinde `Great` YALIN geçiyor.

Çözüm `glossary.kosul` sütunu: karşılığın hangi bağlamda geçerli olduğunu anlatan
serbest metin. Prompt'a `Great -> Ulu  [KOŞUL: ...]` diye çıkar ve
`SYSTEM_INSTRUCTION` modele koşul sağlanmıyorsa karşılığı ZORLAMAMASINI söyler.
Doğrulandı (aynı istekte beş cümle): `Great!` -> Harika · `Great rank` -> Ulu ·
`Great job` -> Harika · `Great Devil` -> Ulu Şeytan · `Supreme rank` -> Yüce.

Üç kural load-bearing:

* **Koşul karşılığın YERİNE GEÇMEZ**, yanına iliştirilir ve YALNIZ prompt'a çıkar.
  `sozluk_ihlalleri`, `_terim_metinde` ve terim eşleştirme karşılığı olduğu gibi
  görmeye devam eder — koşulu karşılığın içine gömmek bu üçünü birden bozardı.
  AMA koşullu KAYIT uyum denetiminin DIŞINDADIR (2026-09-11): karşılık yalnız o
  bağlamda geçerli olduğu için "uyulmadı" ölçülemez. Ölçüt tek yerde durur
  (`translate._denetlenebilir_terimler`) ve hem bayrağı hem otomatik onarımın
  hedefini o belirler; ayrışırlarsa onarım denetimin görmediği sahte bir ihlali
  "düzeltmeye" kalkar ve doğru bırakılmış özel adı bozar.
* **`set_term` koşulu KORUR, `set_kosul` yazar/temizler.** İkisinin "verilmedi"
  anlamı zıttır: okuyucunun çevrimdışı kuyruğu yalnız `{source, target}` gönderir
  ve `set_term`'ün koşulu silmesi, kullanıcının sıradan bir karşılık düzeltmesinin
  kuralı sessizce yok etmesi demekti. `INSERT OR REPLACE` satırı silip yeniden
  yazdığı için koşul `created_at`/`first_chapter` gibi TAŞINIR.
* **Koşul yalnız SÜZGEÇTEN geçen terimler için yazılır.** Metinde geçmeyen bir
  terimin koşulu her istekte boşa token yakardı.

Koşul okuyucunun sözlük ekranında satırın altında GÖRÜNÜR (`.gloss-kosul`) — kural
prompt'a çıkıyor, ekranda saklanırsa terim beklenmedik çevrildiğinde sebebi hiçbir
yerde okunamaz. Düzenleme uçtan yapılır (`POST /api/book/{slug}/glossary`, `kosul`
alanı); `None` = alan gönderilmedi (KORU), `""` = temizle.

**Koşulları okuyan yol SÖZLÜĞÜ okuyan yolla aynı olmalı.** `pipeline`'da
`get_glossary` çağrılan her yerde `get_kosullar` da çağrılır ve `translate_chapter`'ı
çağıran her nokta `kosullar=` geçirir; `tests/test_sozluk_kosul.py` ikisini de
statik tel tuzağıyla tutar. Bu projede `model` künyesi tam olarak böyle ayrışmıştı.


**`app/core/jobs.py`** — **Bellek-içi** arka plan toplu çeviri (sekme kapansa da sürer;
sunucu yeniden başlarsa iş kaybolur — bölümler cache'te kaldığı için sorun değil).
**GEÇİCİ çeviri hatası işi ÖLDÜRMEZ** (2026-09-10): `TranslateError` alınınca aynı
bölüm `BULK_GECICI_DENEME` (3) kez, aralarında `BULK_GECICI_BEKLEME` (30 sn, sonra
90 sn) beklenerek yeniden denenir. Eskiden tek bir hata `state="error"` yazıp işi
bırakıyordu — 15 bölümlük iş ikinci bölümde ölüyor, kullanıcı kalan 13'ünü hiç almıyor
ve rafta yalnız "! HATA" rozeti kalıyordu. **ÇEKİM hatası bilerek AYRI tutulur**:
`fetch` kendi üstel geri-çekilmesini zaten yapıyor, buradan ikinci bir tekrar katmanı
Cloudflare'e üst üste inmek olurdu. Bekleme `_bekle()` ile PARÇALIDIR (1 sn'lik
adımlar, her adımda durdurma sorgulanır) — tek uzun uyku olsaydı "DURDUR" düğmesi
dakikalarca cevapsız kalırdı.

**Raf rozetini seçen kural İKİ AŞAMALIDIR** (`get_book_job`, 2026-09-10): önce her TİP
kendi EN SON kaydıyla temsil edilir, sonra tipler arasında dikkat önceliği uygulanır
(çalışan iş > hata > gerisi). İkinci aşama tek başınayken aynı tip içinde TARİH yok
sayılıyordu: bulk 09-09'da hataya düştü, kullanıcı 09-10'da yeniden çalıştırıp 10/10
bitirdi, ama raf hâlâ "! HATA" gösteriyordu. Rozet "ilgilenmen gereken bir şey var"
demektir; sorun çözülmüşken orada durması yanlış bilgidir. İlk aşama E-5'i BOZMAZ —
gece check-updates işinin done kaydı yarım bulk hatasının rozetini yine sökmez, çünkü
iki tip ayrı temsil edilir (`tests/test_jobs_types.py` ikisini de tutar).

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

**`app/web/`** — Çerçevesiz (vanilla JS) PWA, **build adımı yok**: `index.html`,
`style.css`, `sw.js` ve **ES modülleri** (2026-09-16'da tek 170 KB'lık `app.js`
bölündü). `app.js` yalnız giriş noktasıdır: modülleri içe aktarır ve sırayla
`kur()` çağırır — olay kayıtları modül YÜKLENİRKEN değil `kur()`da kurulur
(döngüsel içe aktarmada yarım değerlendirilmiş modüle erken dokunulmasın).
`js/`: `temel` · `durum` (modüller arası PAYLAŞILAN değişken durum tek nesnede —
içe aktarılan bağlamaya atama yapılamaz) · `konum` · `ayarlar` · `gezinme` ·
`kutuphane` · `kitap` · `cevrimdisi` · `okuyucu` · `sozluk` (kuyruk bağdaştırıcısı +
sözlük ekranı) · `sozluk-kuyruk` (SAF, Node testli) · `sozluk-secim` (okurken seçim) ·
`sozluk-inceleme` · `terim-paneli` · `terim-yardimci` (SAF) · `bildirim` · `diyalog`
(ortak `<dialog>`) · `api-durum` (API durum paneli + künye "neden bu model?") ·
`api-durum-yardimci` (SAF). **Yeni modül = `sw.js` SHELL listesine ekle** (`tests/test_modul_kabugu.py`
tutar): listede olmayan modül çevrimdışı açılışta indirilemez ve uygulama HİÇ başlamaz.
**`scripts/start_chrome_cdp.py`** — gerçek Chrome'u `:9222` debug
portu + ayrı profil (`cache/.chrome-cdp`) ile açar. **`faz0/`** — eski kavram-kanıtı
(bağımsız; `app/` bunun yerini aldı, dokunma).

## Tek veritabanı

Her şey **tek SQLite dosyasında**: `cache/chapters.db` (WAL modu). Mantıksal depolar:
`chapters` (cache) + `ceviri_arsivi`, `books`+`aliases` (kütüphane), `glossary` +
`sozluk_gecmis` / `sozluk_surumu` / `sozluk_red` / `sozluk_yazim` / `sozluk_anlam`,
`settings` (sunucu-taraflı genel ayarlar — bugün yalnız çeviri modeli seçimi) ve
`kullanim` (ücretli model token sayacı). **Merkezi şema/migration
dosyası yoktur** — her modülün `_connect()`'i kendi tablosunu `CREATE TABLE IF NOT EXISTS`
ile tembel oluşturur. **Yeni sütun eklerken `db.ensure_column()` kullan** (idempotent;
SQLite'ta `ADD COLUMN IF NOT EXISTS` yok). `NOVEL_DB_PATH` env'i yolu değiştirir;
`tests/conftest.py` her testi geçici DB'ye yönlendiren autouse fixture ile izole eder.

## Kritik kararlar & tuzaklar

- **PWA service worker sürümü**: kabuk varlıkları (`app.js`/`js/*.js`/`index.html`/`style.css`)
  değişince `app/web/sw.js` içindeki `SHELL_CACHE = "novellink-shell-vNN"` **artırılmalı**,
  yoksa telefonlar bayat kabuğu servis eder. `DATA_CACHE` **sabit** isimlidir (bölüm
  `/api` yanıtlarını tutar; sürümle silinmez). Bu tekrarlayan, elle yapılan bir adımdır.
- **ÇEVRİMDIŞI KAYIT GÜVENLİ BAĞLAM İSTER — düz IP adresinde ÇALIŞMAZ** (2026-09-10,
  ölçüldü). Service Worker ve Cache API yalnız `https://` ya da `http://localhost`
  üzerinde vardır. Telefon `http://100.x.x.x:8000` (Tailscale IP) ya da
  `http://10.x.x.x:8000` (LAN) ile bağlandığında `window.isSecureContext` **false**,
  `caches` API **yok**, SW **hiç kaydolmaz**. Ölçüm (aynı sunucu, üç adres):

  | adres | secureContext | caches | SW |
  |---|---|---|---|
  | `http://localhost:8000` | True | var | AKTİF |
  | `http://100.103.112.103:8000` | False | YOK | YOK |
  | `https://<makine>.<tailnet>.ts.net` | True | var | AKTİF |

  Arıza AYLARCA "toplu çeviri çevrimdışı kaydetmiyor" kılığında göründü, çünkü
  `otoIndirmeTur` `caches` bulamayınca SESSİZCE çıkıyordu — çalışmayan bir özellik
  çalışıyor gibi duruyordu. Artık güvensiz adreste KALICI bir uyarı basılır (4 sn'lik
  temizleyici bilerek çalıştırılmaz). Çözüm Tailscale Serve'dir
  (`tailscale serve --bg 8000`) ve `start.bat` HTTPS adresini MagicDNS'ten
  (`tailscale status --json` → `Self.DNSName`) bulup ÖNERİLEN olarak basar; düz IP
  satırlarının yanında "CEVRIMDISI KAYIT YAPMAZ" yazar. **Batch tuzağı:** `for /f`
  backtick'i içinde çift tırnaklı PowerShell komutuna `^|` geçirilemez — pipe
  `tailscale`e argüman olarak gider (`unexpected non-flag arguments`). Pipe yerine
  `ConvertFrom-Json ($t -join '')` kullanılır.
- **Toplu çeviri telefona KENDİLİĞİNDEN inmez; taramayı tetikleyen kütüphanedir.**
  SW yalnız telefondan GEÇEN `GET /api/chapter` yanıtlarını `DATA_CACHE`'e yazar; toplu
  çeviri ise SUNUCUDA koşuyor ve telefona tek bayt inmiyor. Isıtma taraması
  (`app.js:otoIndirmeTur`) boşluğu kapatır ve **`renderLibrary`'den** çağrılır — yani
  uygulamayı açmak yeter. Eskiden tek tetikleyici `openBook` idi (o kitabın bölüm
  listesini açmak) ve `pollBulk`'ün bitiş dalı da yalnız hâlâ o sayfadaysan
  `openBook` çağırıyordu; üç boşluk açık kalıyordu — iş sen başka yerdeyken biterse,
  uygulamayı kapatırsan, ya da ertesi gün açarsan hiçbir şey inmiyordu (gerçek
  şikâyet 2026-09-03). Tarama tek-uçuşludur, zaten önbellekte olanı atlar (tekrarlanan
  turlar genelde sıfır istek), elle indirme açıkken ya da çevrimdışıyken durur.
- **`translated` bayrağı PARA güvenliğidir** (`cache.list_chapters`). `chapters`
  tablosu SAHNELENMİŞ satır da tutar (içe aktarılan PDF/EPUB/manga sayfaları,
  `translation` NULL, okundukça çevrilir) ve bir bölümü GET'lemek çevirisi yoksa
  ÇEVİRİ TETİKLER — ücretli model seçiliyken PARA harcar. Her iki toplu indirme yolu
  da (elle "çevrimdışı indir" ve otomatik tarama) yalnız `translated` olanları ister:
  ikisi de "indir" diyor, "çevir" demiyor. Bayrak olmadan otomatik tarama, içe
  aktarılan bir kitabı sessizce baştan sona çevirtirdi. **Listeye yeni bir toplu
  indirme yolu eklerken bu süzgeci de ekle.**
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
  `engine` artık FİİLEN çeviren sağlayıcıdır (`translate.motor_adi`, tek tanım):
  `gemini` · `mistral` · parçalar farklı sağlayıcıya düştüyse `mistral + gemini`.
  2026-08-30'a kadar sabit `"gemini"` yazıyordu ("tek motor kaldığından sabit") ve
  Mistral zincirin ilk halkası olunca bu doğrudan YANLIŞ bilgiye dönüştü: Mistral'in
  çevirdiği bölüm rozette "GEMINI ile çevrildi" diyordu. Motoru üreten ÜÇ nokta var
  (`translate_chapter`, `_render_import_page`, `manga_engine._save_engine_page`);
  üçü de aynı yardımcıyı çağırmalı, yoksa aynı bilgi için üç ayrı kural oluşur.
  DB'de ikinci-motor denemesinden kalma `claude` satırları da var; okuyucu rozeti
  sağlayıcı adını olduğu gibi büyüttüğü için onlar da doğru etiketlenmeye devam eder
  (yeni motor eklenince rozette ayrı bir dal açmak gerekmez).
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
- **ÇOĞUL kaydedilmiş terim tekili de yakalamalı** (`_term_regex(term, cogul_esnek)`):
  kuyruk eki (`(?:'s|es|s)?`) çoğulu EKLİYOR ama ÇIKARMIYORDU, yani çoğul anahtar
  tekili ASLA yakalayamıyordu ve kayıt sözlükte durduğu hâlde prompt'a hiç girmiyordu.
  Ölçülen vaka (2026-08-23): `tyrants -> Tiranlar` kayıtlıyken metinde `tyrant` 22 kez
  tekil / 2 kez çoğul geçiyordu; `the Tyrant` prompt'a girmediği için model serbestçe
  "hükümdar" çevirdi. Düzeltme anahtarın SON `s`'ini isteğe bağlı yapar; gerçek
  sözlükte kapsanan geçiş **14 → 59**. Esneklik **yalnız TÜRKÇE KARŞILIKLI kayıtlarda**
  açılır (`_terim_metinde`): risk sınıfı İngilizce korunan KİŞİ adlarıdır (`Nephis`
  → `Nephi`) ve orada yanlış eşleşme sıradan bir sözcüğü İngilizce bıraktırır — pahalı
  yön. `MIN_COGUL_KOK` kısa kökleri korur, `es` çoğulları bilerek kapsam dışı (fazla
  soymak gerçek kökü bozar, eksik soymak yalnız fırsat kaçırır). Ölçüm: `s` ile biten
  53 kaydın 17'sinin kökü metinde geçiyor ve 17'si de meşru tekil/çoğul çifti.
  **Sözlüğe terim TEKİL yazılmalı** — karşılık da tekil olmalı, yoksa tekil cümlede
  modele çoğul karşılık dayatılır.
  **Tekili AYRICA kayıtlıysa çoğul esnekliği KAPALI** (2026-09-23,
  `_tekili_kayitli_cogullar`): tekil geçişin sahibi tekil kayıttır. Esneklik tekili
  kayıtsız çoğul içindi; tekil de kayıtlıyken çoğul kayıt tekili yakalayınca
  tekilin KOŞULUNU eziyordu. Ölçülen vaka: koşullu `Saint -> Aziz` yanında koşulsuz,
  otomatik `Saints -> Azizler` — gölgenin adı geçen bölümlerde prompt'a koşulsuz
  çoğul satırı giriyor, adı DOĞRU koruyan çeviri de sahte `Saints` ihlali alıp
  gereksiz bir onarım isteği tetikliyordu (saklı bayrakların 44'ünün 44'ü sahte).
  Koşulsuz çiftte aynı sızıntı iki kez sayılıyordu (`Nightmare` + `Nightmares`).
  Etki alanı shadow-slave'de 85 çift. `_terim_metinde`'yi çağıran HER yer kümeyi
  geçirir; `tests/test_glossary_terms.py` statik tel tuzağıyla tutar.
  **Ucuz ön eleme sonucu DEĞİŞTİRMEZ** (2026-09-23, `_on_eleme_anahtari`): prompt
  süzgeci ve "bu bölümde geçenler" listesi regex'ten önce `fold_term` ile ön eleme
  yapar. O eleme TAM anahtarı ("tyrants") arıyordu, desen ise tekili ("Tyrant") —
  yani yukarıdaki **14 → 59** kazancı yalnız DENETİMDE gerçekleşti, esneklik
  girdiğinden (09-10) beri prompt'a hiç ulaşmadı. Ölçüm (sunucu kopyası): 838
  bölümün 115'inde 124 kayıt prompt'a girmesi gerekirken girmedi (`Warriors` 39,
  `Trials` 24, `Dolls` 20, `Return Scrolls` <- "Return Scroll"). Anahtar artık
  desenle AYNI parçalardan türer; bir özellik testi iki kümenin eşitliğini tutar.
  Çoğul karşılığın tekil cümleye çoğul dayatma riski ölçüldü: kayıt zaten
  prompt'tayken yalnız-tekil 42 paragrafın 41'i tekil çevrilmiş, kalan biri de
  çoğul özneli ("their trial, Aspirants" -> "Sınavlarını") ve doğru.
- **Hiyerarşi basamakları küçük harfli de olsa terimdir** (`SYSTEM_INSTRUCTION`,
  HİYERARŞİ İSTİSNASI): `detected_terms` ÖLÇÜTÜ "metinde BÜYÜK HARFLE başlayarak
  adlandıran" diyordu; canavar rütbeleri kaynakta çoğunlukla küçük harfli geçiyor
  (Shadow Slave 4. bölüm: `monsters` 13 küçük / 1 büyük) ve model onları harfiyen
  cins isim sayıp hiçbirini sözlüğe yazmadı. İstisna DAR: ad bir DİZİ hâlinde
  sayılıyorsa ya da bir düzene bağlanıyorsa basamaktır; düzene bağlanmadan geçen
  sıradan cins isim girmez.
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
- **Bölüm NUMARASI uydurulabilir bir alandır; ARADAN ekleme onu bozar.**
  `fetch_into_book` ("web'den devam") bir dönem sayfanın KENDİ numarasını yok sayıp
  kuyruk sayacı (`tail+1`) veriyordu ve her ekleme kuyruğun `next`'ini yeni bölüme
  çeviriyordu. Sona ekleme için doğru, ARAYA ekleme için yıkıcı: ölçülen gerçek vaka
  (Shadow Slave 2026-09-02) kuyruk 140'tayken eklenen `chapter-137` 141 numarasını,
  sonra eklenen `chapter-141` 142'yi aldı; zincir de koptu (140 → 137 → 141) ve
  okuma sırası kaydı. Numara önceliği artık: açık argüman → **sayfanın kendi
  numarası** → `tail+1`. Ortadaki adım KOŞULLU — yalnız kitap zaten kaynağın
  numaralandırmasını izliyorsa (kuyruğun URL'sindeki numara `chapter_no`'ya eşitse).
  Koşul şart: `fetch_into_book`'un asıl işi PASTE kitabını web'e köprülemek ve orada
  sayfanın numarası başka bir evrenden gelir (paste kitabın 2. bölümü, sitenin
  1704'ü). Zincir de yalnız gerçekten kuyruğa eklerken kurulur.
  Onarım: **`scripts/bolum_sirasi_denetle.py`** (varsayılan KURU çalıştırma,
  `--uygula` ile yazar; slug verilmezse tüm kitaplar). Üç ayrı denetim:
  numara (URL ve BAŞLIK **birbiriyle** uyuşup `chapter_no`'dan ayrıldığında —
  tek kaynağa dayanmak manga sayfalarını ve "Chapter 0" ön sözlerini bozardı),
  zincir (yalnız AYNI kitapta önbellekli bir bölümü gösteren yanlış bağ; önbellek
  BOŞLUKLU olabildiği için boş/dışarıyı gösteren bağlantı bozukluk sayılmaz) ve
  okuma konumu (`current_url` ölçüttür, ad/numara türetilmiş alanlardır).
  Konumu düzelten yardımcı `library.konum_adini_duzelt` — `upsert_book(
  update_position=False)` bu iş için KULLANILAMAZ, o var olan satıra bilerek hiç
  dokunmuyor (`INSERT OR IGNORE`).
- **Okuma konumu bir ÜÇLÜDÜR: (url, ad, numara) — ayrı yazılamaz** (2026-09-12).
  `library.set_position` bir dönem yalnız `current_url` + `current_ratio` +
  `updated_at` yazıyordu; ad ve numara bir önceki bölümde kalıyordu. Ölçülen vaka:
  `current_url` 393'ü gösterirken `chapter_no` 391, ikinci kitapta sapma 15 bölüm.
  Zarar İKİ katmanlı ve ikincisi daha sinsi: `updated_at` de tazelendiği için
  okuyucunun DOĞRU yerel kaydı (`resolveResume`, `local.ts >= serverTs` ölçütü)
  "bayat" sayılıp ATILIYOR ve ekrana bayat SUNUCU değeri çiziliyordu — kullanıcı
  391'deyken ana sayfa "BÖL. 390" diyor, okuyucuya girip çıkınca (yerel ts
  tazelenince) düzeliyordu. Adı doğru yazan yol (`upsert_book`) devreye girmiyor:
  indirilmiş bölüm Service Worker önbelleğinden geliyor, `GET /api/chapter`
  sunucuya HİÇ ulaşmıyor. Ad/numara verilmediğinde davranış bilerek asimetriktir:
  aynı bölümde kaydırma (url değişmedi) adı KORUR — en sık çağrı budur; bölüm
  değiştiyse TEMİZLER, çünkü eski adı korumak okuyucuya güvenle YANLIŞ bir numara
  çizdirir ve NULL'da fiş "SON BÖLÜM"e düşer (eksik bilgi yanlıştan iyidir). Karar
  TEK bir UPDATE içinde SQL'le verilir (SET sağ tarafları ESKİ satır değerleriyle
  hesaplandığı için url karşılaştırması aynı deyimde güvenli; SELECT-sonra-yaz
  TOCTOU açardı). İstemci değerleri `currentChapterNo`/`currentChapterTitle`
  GLOBAL'lerinden değil konumu yazılan ENTRY'den okur. Eski satırların onarımı:
  `scripts/bolum_sirasi_denetle.py` (KONUM denetimi). `tests/test_konum_uclusu.py`.
- **slug her şeyin anahtarı**, URL'den türetilir; pipeline cache/glossary'den önce daima
  `resolve_slug` ile kanonikleştirir. Yeni endpoint yazarken bu adımı atlama.
- Durum dökümanları: `PLAN-dayaniklilik.md` (Faz 5, kısmen sevk edildi — bulk kalıcılığı
  bilinçle düşürüldü), `progress.md`, `TODOS.md`.

## Sözlük düzenleme sistemi (2026-09-16, `FRONTEND-SOZLUK-ARASTIRMA.md` uygulaması)

- **Yazma kuyruğu v2** (`js/sozluk-kuyruk.js`, saf, Node testli): her işlemin KİMLİĞİ
  var, yalnız gönderilen kimlik düşer (eskiden terim anahtarıyla siliniyor, uçuştayken
  yazılan yeni değer de kayboluyordu). Depolama yazma hatası YUTULMAZ, görünür durumdur.
  4xx işlemi SİLMEZ ("hata"), 408/425/429/5xx/ağ yeniden denenir. Kural: kaydedilmemiş
  değer asla kaydedilmiş gibi görünmez. İşlem alanı `tur` İŞLEM türüdür (yaz/sil/geri);
  terim türü `terim_turu` adıyla taşınır.
- **Sürüm ve çakışma**: `glossary.kimlik/surum/updated_at` (EKLEMELİ göç — tablo yeniden
  kurulmadı). `surum` yalnız PROMPT alanları (karşılık, koşul, yazım, ek anlam) değişince
  artar. İstemci gördüğü sürümü `taban_surum` ile gönderir; uyuşmazsa **409 + güncel kayıt**,
  arayüz iki değeri yan yana gösterir ("Benimkini yaz" / "Sunucudakini kullan").
  Uçuştaki işlem dönünce aynı terimin sonraki işlemlerinin tabanı yeni sürüme taşınır —
  yoksa kullanıcı KENDİ kaydıyla çakışır. `taban_surum` yok = denetim yok (eski istemci,
  hızlı ekleme formu, bakım araçları).
- **Geçmiş**: sözlüğe YAZAN her fonksiyon `_gecmise_yaz` çağırır; `tests/test_sozluk_surum.py`
  statik tel tuzağı atlayanı yakalar. Yeni bir yazma yolu eklerken ya geçmişe yaz ya da
  (yalnız prompt dışı alan yazıyorsa) istisna listesine gerekçesiyle ekle.
- **Kitap sözlük sürümü** `sozluk_surumu` tablosunda; bölüm çevrilirken ÇEVİRİDEN ÖNCE
  okunup `chapters.sozluk_surumu` künyesine yazılır (iki metin yolu, tel tuzağı).
- **Çeviri arşivi**: çeviri METNİ değişen her yazımda eski hâl `ceviri_arsivi`ne (url başına
  son 3). Geri yükleme `created_at`'i tazeler — telefon kopyasının bayatladığı buradan anlaşılır.
- **Telefon kopyası tazeliği**: SW önbelleğindeki yanıtın `Date`'i `ceviri_zamani`ndan
  eskiyse kopya silinip yeniden indirilir (kitap açılışı + kütüphane taraması). Sunucuda
  yeniden çevrilen bölümü telefona indirmek için `refresh=1` KULLANMA — ikinci çeviri
  tetikler; önce SW kopyasını sil, sonra düz GET.
- **Çeviri yolu ekran sözlüğünü OKUMAZ**: `pipeline` `glossary.ceviri_sozlugu` +
  `ceviri_kosullari` okur (alternatif yazımlar + ek anlamlar dahil); ekran `get_glossary`.
  Ek anlam koşul metnine `BAŞKA ANLAM:` işaretiyle işlenir, denetimden çıkar ve açıklaması
  prompt'a YALNIZ o istekte ek anlamlı terim varsa girer (öteki prompt'lar bayt bayt aynı).
  Terim TÜRÜ prompt'a girmez (ölçülmedi).
- **İnceleme**: yeni otomatik kayıt `inceleme='bekliyor'`; eski kayıtlardan yalnız
  çakışan/belirsiz olanlar nedenleriyle hesaplanır (mevcut bakım fonksiyonları). Ret
  kaydı siler ve `sozluk_red`'e yazar; `merge_terms` reddedileni ve alternatif yazımı atlar.
- **Değerlendirme seti**: `scripts/degerlendirme.py` — kuru kip API'siz (önbellekteki
  çevirileri ölçer), `--calistir` kota harcar ve önbelleğe YAZMAZ, ücretli modeli reddeder.
  Çıktılar `cache/degerlendirme/` (depoya girmez).

**Test tuzakları (ölçüldü):**
- **`page.wait_for_function` ASYNC yüklemi BEKLEMEZ** — dönen Promise truthy, anında geçer
  (`"async () => false"` 0,03 sn). Sunucu durumunu fetch ile bekleyen her iddia için
  `tests/tarayici/yardimci.js_bekle`. Statik tel tuzağı var. Yeni tarayıcı testini
  MUTASYONLA sına: bu projede ilk seferde geçen testlerin ikisi dişsiz çıktı.
- **Okuyucu dışındaki bölüm GET'leri `track=0` taşır** (indirme, kaynak getirme): yoksa
  sunucu okuma konumunu o bölüme taşır. `tests/test_konum_izleme_js.py` tutar.
- Commit'i pytest ÇIKIŞ KODUNA bağla; `| tail` zincirinde kod kaybolur.

## Ortam değişkenleri (`.env`, kök dizinde)

| Değişken | Zorunlu | Ne işe yarar |
|---|---|---|
| `GEMINI_API_KEY` | Evet | Zincirin BİRİNCİ anahtarı (yalnız yeni çeviri için; cache isabeti gerektirmez) |
| `GEMINI2_API_KEY` | Hayır | İKİNCİ anahtar: birincinin kotası dolunca (429) aynı MODELDE devralır. Yoksa sessizce atlanır. Ad esnek — `GEMINI_API_KEY_2` / `GEMINI3_API_KEY`… da tanınır, sıra addaki sayıdan gelir. **Kota PROJE başına olduğu için ayrı bir Google Cloud projesinden alınmadıkça hiçbir şey kazandırmaz** |
| `NVIDIA_API_KEY` | Hayır | Zincirin SON halkası `z-ai/glm-5.3` (build.nvidia.com, ÜCRETSİZ, kartsız). Google dışı yedek: Gemini halkalarının hepsi düştüğünde çeviri durmaz. Yoksa halka sessizce atlanır |
| `VERTEX_PROJE` | Hayır | Vertex halkası (`vertex/gemini-3.6-flash`) için Google Cloud proje kimliği. **ÜCRETLİ** (deneme kredisinden düşer), YALNIZ okuyucudan seçilince. Sır değil — kimlik VM servis hesabı. `VERTEX_KONUM` boşsa `global`. Yoksa halka sessizce atlanır |
| `CLAUDE_API_KEY` | Hayır | Claude halkaları (`claude-haiku-4-5` · `claude-sonnet-5`). **ÜCRETLİ** ve YALNIZ okuyucudan açıkça seçilince kullanılır — ücretsiz zincir asla buraya inmez. `ANTHROPIC_API_KEY` de tanınır (SDK'nın kanonik adı). Yoksa halka sessizce atlanır |
| `FETCH_HTTP_FIRST` | Hayır | `0` → düz HTTP yolunu KAPAT, doğrudan tarayıcıya düş. **ACİL ÇIKIŞ**; varsayılan açık. Bölüm sayfalarında CF koruması yok, düz HTTP 1 sn'de çekiyor (tarayıcı yolu aynı bölümde 68 sn) |
| `FETCH_PROXY` | Hayır | Çekimi residential proxy üzerinden çıkarır (`http://kullanıcı:parola@host:port`; parolada `@` varsa `%40` diye yüzde-kodla). Bulut sunucuda **gerekmedi** — engel IP değil TLS'ti, `curl_cffi` çözdü. Sigorta olarak durur |
| `FETCH_BLOCK_ASSETS` | Hayır | `1` → TARAYICI yolunda resim/font/medya indirilmez. `script`/`stylesheet` ASLA engellenmez (CF challenge JS ile çözülür). Manga etkilenmez (`_extract_html`'den geçmez) |
| `FETCH_CDP_URL` | Hayır | Örn. `http://127.0.0.1:9222` → sert CF için gerçek Chrome'a bağlan. Bulut sunucuda BOŞ (gerçek Chrome yok) |
| `FETCH_HEADLESS` | Hayır | `0` → görünür pencere (CF'i bir kez elle çözmek için) |
| `NOVEL_DB_PATH` | Hayır | Test/CI'da DB'yi geçici dosyaya yönlendirir |

`OPENROUTER_API_KEY` · `MISTRAL_API_KEY` · `GROQ_API_KEY` · `CEREBRAS_API_KEY` 2026-09-02'de
ARTIK OKUNMUYOR (Gemini dışı sağlayıcılar kaldırıldı). `.env`'de kalmaları zararsızdır ama
hiçbir işe yaramaz.

**Anahtar kapısı ANAHTAR HAVUZUNA bakar** (2026-09-02, `translate.ceviri_anahtari_var_mi`).
Eskiden `if not api_key` diye sorulup "GEMINI_API_KEY ayarlı değil" hatası veriliyordu; ikinci
anahtar yalnız `.env`'de durabildiği için bu, pekâlâ çalışabilecek bir kurulumu sebepsiz
reddederdi. Gemini istemcisi ayrıca TEMBEL kurulur (`translate._gemini_fabrikasi`):
`_generate_with_fallback` kurulmuş istemci değil FABRİKA alır, istemci ancak gerçekten
kullanılacağı anda kurulur — böylece hiç inilmeyen bir halka için anahtar zorunlu olmaz.
Zincirin TAMAMI anahtarsızlıktan düşerse hata mesajı "modeller meşgul" değil "API anahtarı
yok" der (yanlış teşhis kullanıcıyı beklemeye iterdi).

**Test tuzağı:** `server` importu `.env`i pytest sürecine yüklüyor, bu yüzden "anahtarsız
reddedilir" testleri anahtar değişkenlerini `translate.gemini_anahtar_degiskenleri()` ile
TÜRETİP döngüyle `delenv` etmeli. Adları tek tek yazmak, üçüncü bir anahtar eklendiğinde
testi sessizce geliştiricinin makinesindeki `.env`e bağımlı kılar.


`.env` git'e girmez (`.gitignore`); ikinci makineye elle kopyalanır — bkz. `KURULUM.md`
Şablon: `.env.example` (tüm değişkenler, değerler BOŞ). Ad `.env.ornek` DEĞİL —
güvenlik araçları `.env.<sonek>` desenini gerçek sır dosyası sayıyor ve yalnız
`.example/.sample/.template/.dist` soneklerini istisna tanıyor.

## Bulut sunucu (2026-09-12'den beri ASIL kurulum)

Backend artık **Google Cloud e2-micro**'da 7/24 çalışıyor; ev bilgisayarı devrede
değil. Erişim `https://novel-cevirmen.<tailnet>.ts.net` (Tailscale, **tailnet-only** —
`funnel` KULLANILMAZ, proje kişisel kullanım için dışarıya kapalı kalmalı). Servis
systemd (`novel-cevirmen.service`): açılışta başlar, çökerse kalkar.

**SUNUCU TEK KAYNAKTIR.** `cache/chapters.db` sunucuda yaşar ve orada büyür: yeni
bölümler, sözlüğe OTOMATİK eklenen terimler, okuma konumu. Ev makinesindeki kopya
taşındığı gündeki hâlinde donmuştur. Yerel `start.bat`'ı BAŞLATMA — iki ayrı
kütüphane, iki ayrı okuma konumu ve iki ayrı sözlük oluşur. Gerçek vaka
(2026-09-12): `Saints -> Azizler` kaydı yalnız SUNUCUDA oluştu (orada çevrilen bir
bölümden), yerelde hiç yoktu; sözlük onarımı iki yerde ayrı ayrı koşturuldu.
Sözlük/veri düzeltmeleri SUNUCUDA yapılır; yerel kurulum yalnız geliştirme içindir.

**Bedava katman ŞARTLARI** (biri bozulursa fatura işler, sessizce):
* Ayda **1 adet** e2-micro; ikincisi ücretli.
* Bölge **us-west1 / us-central1 / us-east1**; başka bölge ücretli.
* Boot disk **`pd-standard`**, en fazla 30 GB. Konsol varsayılanı `pd-balanced`
  getirir ve o ÜCRETLİDİR — sürpriz faturaların en yaygın sebebi. İlk kurulumda
  tam bu tuzağa düşüldü, VM silinip `--boot-disk-type=pd-standard` ile yeniden
  oluşturuldu.
* Egress ayda 1 GB bedava. Ölçülen kullanım ~50-100 MB/ay (bölüm başına ~15-20 KB),
  yani sınırın çok altında. İSTİSNA: `cache/media` (içe aktarılan kitaplar) Service
  Worker'a girmez, her erişimde egress yakar — o yüzden sunucuya hiç taşınmadı.

Fatura hesabında **10 TRY bütçe uyarısı** kurulu (%50 ve %100 eşiği). Bu projede
"sessizce paraya dönen arıza" dersi bir kez ödendi (OpenRouter `:free` soneki);
gürültüsüz fatura riskine karşı gösterge şart.

Sunucuya Chromium KURULMADI: düz HTTP yolu yeterli ve 1 GB RAM'de Chromium zaten
zor. Yani tarayıcı yedeği bu sunucuda FİİLEN yok — düz HTTP kapanırsa (site CF'i
bölümlere yayarsa) ayrı bir çözüm gerekir, `playwright install chromium` tek başına
yetmeyebilir.

**Dağıtım `git pull`'dur, `scp` DEĞİL** (2026-09-12, kullanıcı kararı). Kod
`github.com/omerek01/novel-cevirmen` (ÖZEL depo) üzerinden gider; sunucudaki
`~/novel-cevirmen` gerçek bir çalışma ağacıdır. Sunucu depoya SALT-OKUNUR bir
**deploy key** ile bağlanır (`~/.ssh/novel-cevirmen-deploy`, `~/.ssh/config`'te
`github.com` kaydı): sunucuda yazma yetkisi olan bir token durmaz, ve anahtar
yalnız BU depoyu açar. Erişim `ssh -i ~/.ssh/google_compute_engine OMEREK@100.75.105.102`
(Tailscale). `-i` ŞART: varsayılan anahtarla bağlantı reddediliyor.

```bash
ssh -i ~/.ssh/google_compute_engine OMEREK@100.75.105.102 'cd ~/novel-cevirmen && git pull && sudo systemctl restart novel-cevirmen'
```

Dört kural:
* **Şema değiştiren sürümden ÖNCE sunucu DB'sini yedekle** (`cp cache/chapters.db
  cache/chapters.db.yedek-<tarih>`; WAL açıkken `sqlite3 ... ".backup ..."` daha
  güvenli). Göçler tembel ve eklemelidir ama ilk bağlantıda canlı veriye yazar.
* **Restart'tan ÖNCE koşan toplu çeviri işi var mı bak.** İşler BELLEK-İÇİ
  (`jobs.py`), restart onları öldürür: `curl -s localhost:8000/api/book/<slug>/job`.
* **Yalnız `app/web/` değiştiyse restart GEREKMEZ** — statikler her istekte
  diskten okunuyor. Python değiştiyse gerekir (süreç açılışında yükleniyor).
  Açılış e2-micro'da ~8 sn sürer; hemen atılan `curl` 000 döner, panik etme.
* **`cache/`, `.env`, `.venv/` takip EDİLMEZ** (`.gitignore`), yani `git pull`
  ve hatta `git reset --hard` onlara dokunmaz — takipsiz dosyalar silinmez.
  Yine de `--hard`'a geçmeden önce `git reset` (MIXED) + `git diff
  --ignore-cr-at-eol` ile gerçek farkı gör: sunucuya elle konmuş bir düzeltme
  varsa sessizce kaybolur. (Dosyalar scp ile gittiği için sunucuda CRLF, repoda
  LF — satır sonunu yok saymazsan HER dosya "değişmiş" görünür.)
(Tailscale ile 7/24 sunucu kurulumu ve sorun giderme).

## Test yazımı

Testler **çevrimdışıdır** — Playwright/Gemini çağıran endpoint'ler (`/api/chapter`,
bulk başlatma) test edilmez; saf fonksiyonlar (translate ayrıştırma, fetch nav çıkarımı),
SQLite roundtrip'leri ve ağ gerektirmeyen endpoint'ler (`TestClient`) kapsanır. `conftest.py`
`app/`'i `sys.path`'e ekler ve `NOVEL_DB_PATH`'i geçici DB'ye ayarlar (autouse), böylece
testler `from core import …` / `import server` yapabilir ve gerçek DB'ye dokunmaz.
