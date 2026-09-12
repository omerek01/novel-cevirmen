# Buluta Taşıma — Uygulama Planı

> **Ajan işçiler için:** Bu planı görev görev uygulamak için
> `superpowers:subagent-driven-development` (önerilen) ya da
> `superpowers:executing-plans` alt-becerisini kullanın. Adımlar takip için
> onay kutusu (`- [ ]`) biçimindedir.

**Hedef:** Backend'i evdeki bilgisayardan çıkarıp bulut sunucuda 7/24 çalıştırmak;
Cloudflare'in veri merkezi IP reddini residential proxy ile aşmak.

**Mimari:** Tek Linux sunucu, bugünkü tek-süreç mimarisi korunur. Playwright
`FETCH_PROXY` üzerinden çıkar; roman sayfası çekerken ağır kaynaklar engellenir.
Her iki özellik de ortam değişkeniyle açılır — değişken boşsa ev makinesindeki
davranış birebir aynı kalır.

**Teknoloji:** Python 3.12, FastAPI, Playwright (Chromium), SQLite, systemd,
Tailscale, DataImpulse residential proxy.

**Tasarım dokümanı:** `PLAN-bulut-tasima.md`

**DURUM: TAMAMLANDI (2026-09-12).** Plan uygulanırken iki ölçüm mimariyi
değiştirdi; aşağıdaki görevler yazıldıkları hâliyle duruyor (tarihsel kayıt),
fiilen olan şu:

* **Görev 1-2 (proxy, kaynak engelleme)** — yazıldı ve sevk edildi, ama sunucuda
  KULLANILMIYOR. Düz HTTP birinci yol olunca ikisi de yedek yolun parçası kaldı.
* **Görev 2.5 (proxy karar noktası)** — geçildi ama sonucu beklenmedik: proxy
  sunucuda 403 verdi, suçlu IP değil TLS parmak iziymiş. `curl_cffi` (Chrome TLS
  taklidi) eklendi ve proxy gereksizleşti.
* **Görev 3 (sunucu)** — Oracle kaydı reddedildi (kart doğrulandı, hesap
  oluşturma başarısız; forumlarda yaygın, çözümü manuel inceleme). **Google Cloud
  e2-micro** kuruldu. İlk VM konsol varsayılanlarıyla `pd-balanced` + Debian 13
  olarak açıldı (ücretli disk), silinip `pd-standard` 30 GB + Ubuntu 24.04 ile
  yeniden oluşturuldu.
* **Görev 4-5** — veri taşındı (`chapters.db`; medya taşınmadı, kullanılmıyor),
  systemd + Tailscale kuruldu, 560 test sunucuda geçti, canlı çekim 0,4-0,5 sn.
* **Ek:** 10 TRY bütçe uyarısı kuruldu.

Güncel dağıtım bilgisi: `CLAUDE.md` → "Bulut sunucu". Aşağıdaki adımlarda geçen
`.env.ornek` dosyası `.env.example` adıyla sevk edildi.

## Genel kısıtlar

- Tüm kod, yorum ve doküman **Türkçe** (proje kuralı, CLAUDE.md).
- Testler **çevrimdışı**: ağ, Playwright ve Gemini çağrılmaz; `monkeypatch` ile
  sahtelenir.
- Testler kök dizinden: `.\.venv\Scripts\python.exe -m pytest tests/`
  (`tests/` yolu ŞART — `scratch/` altında pytest toplamasını bozan dosya var).
- Varsayılan davranış değişmez: `FETCH_PROXY` ve `FETCH_BLOCK_ASSETS` boşken
  bugünkü akış birebir korunur.
- `browse/dist/` benzeri derlenmiş dosya yok; `git add` ile dosya adları tek tek
  verilir, `git add .` kullanılmaz.
- Commit yalnız kullanıcı istediğinde atılır.

---

### Görev 1: Ortak tarayıcı bağlamı + `FETCH_PROXY`

**Dosyalar:**
- Değiştir: `app/core/fetch.py` (satır 310-350 civarı: `_fetch_via_launch`,
  `_refresh_clearance_via_launch`)
- Test: `tests/test_fetch_proxy.py` (yeni)

**Arayüzler:**
- Üretir: `fetch._proxy_ayari() -> dict | None`,
  `fetch._baglam_ac(p, headless: bool) -> BrowserContext`
- Tüketir: mevcut `PROFILE_DIR`, `USER_AGENT`, `LAUNCH_ARGS`, `STEALTH_JS`

**Neden ortak bağlam:** `launch_persistent_context` bugün İKİ yerde, aynı parametre
bloğuyla çağrılıyor. Proxy'yi ikisine ayrı ayrı eklemek, birinin unutulması riskini
taşır — ve unutulan `_refresh_clearance_via_launch` olursa Cloudflare cookie'si
proxy DIŞINDAN, yani yanlış IP'yle alınır ve profile yazılır. O cookie sonra proxy'li
çekimlerde kullanılır ve sessizce reddedilir. Bu projede aynı sınıf hata `model`
künyesinde yaşandı.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_fetch_proxy.py` dosyasını oluştur:

```python
"""`FETCH_PROXY`: çekim trafiğini residential proxy üzerinden çıkarır.

Neden ölçülerek gerekli: Cloudflare 2026 itibarıyla öncelikli olarak IP
itibarına bakıyor ve veri merkezi ASN'lerini otomatik en yüksek risk skoruna
alıyor — parmak izi taklidi bunu kurtarmıyor (ölçüm: VPS IP'sinde stealth
Playwright, challenge'ların ~%5'ini geçiyor). Ev makinesinde değişken BOŞTUR
ve akış bugünkü gibi doğrudan çıkar.

Ağa çıkmaz — Playwright sahtelenir.
"""
import pathlib

from core import fetch


class _SahteBaglam:
    def __init__(self):
        self.scriptler = []

    def add_init_script(self, s):
        self.scriptler.append(s)


class _SahteChromium:
    def __init__(self):
        self.kwargs = {}

    def launch_persistent_context(self, **kw):
        self.kwargs = kw
        return _SahteBaglam()


class _SahtePlaywright:
    def __init__(self):
        self.chromium = _SahteChromium()


def test_proxy_ayarsizken_none(monkeypatch):
    monkeypatch.delenv("FETCH_PROXY", raising=False)
    assert fetch._proxy_ayari() is None


def test_proxy_bos_dizeyken_none(monkeypatch):
    """`.env`'de anahtar var ama değeri boş — ayarlanmamış sayılır."""
    monkeypatch.setenv("FETCH_PROXY", "   ")
    assert fetch._proxy_ayari() is None


def test_kimlik_bilgisi_AYRI_alanlara_gider(monkeypatch):
    """Playwright `server` içine gömülü kullanıcı/parolayı YOK SAYAR.

    URL'de bırakılırsa proxy kimlik doğrulaması sessizce başarısız olur ve
    çekim "Cloudflare geçilemedi" kılığında arıza verir.
    """
    monkeypatch.setenv("FETCH_PROXY", "http://kul:parola@proxy.ornek:8000")
    assert fetch._proxy_ayari() == {
        "server": "http://proxy.ornek:8000",
        "username": "kul",
        "password": "parola",
    }


def test_kimliksiz_proxy_sadece_server_verir(monkeypatch):
    monkeypatch.setenv("FETCH_PROXY", "http://proxy.ornek:8000")
    assert fetch._proxy_ayari() == {"server": "http://proxy.ornek:8000"}


def test_yuzde_kodlu_parola_cozulur(monkeypatch):
    """Parolada `@` ya da `:` varsa `.env`'de yüzde-kodlu yazılır."""
    monkeypatch.setenv("FETCH_PROXY", "http://kul:a%40b@proxy.ornek:8000")
    assert fetch._proxy_ayari()["password"] == "a@b"


def test_baglam_proxyi_playwrighte_gecirir(monkeypatch):
    monkeypatch.setenv("FETCH_PROXY", "http://kul:parola@proxy.ornek:8000")
    p = _SahtePlaywright()

    fetch._baglam_ac(p, headless=True)

    assert p.chromium.kwargs["proxy"] == {
        "server": "http://proxy.ornek:8000",
        "username": "kul",
        "password": "parola",
    }


def test_proxysiz_baglam_none_gecirir(monkeypatch):
    """Ev makinesi: proxy alanı None olmalı, Playwright onu yok sayar."""
    monkeypatch.delenv("FETCH_PROXY", raising=False)
    p = _SahtePlaywright()

    fetch._baglam_ac(p, headless=True)

    assert p.chromium.kwargs["proxy"] is None


def test_baglam_stealth_scriptini_kurar(monkeypatch):
    """Ortaklaştırma sırasında kaybolmamalı — CF'i geçiren parça bu."""
    monkeypatch.delenv("FETCH_PROXY", raising=False)
    p = _SahtePlaywright()

    ctx = fetch._baglam_ac(p, headless=True)

    assert ctx.scriptler == [fetch.STEALTH_JS]


def test_baglam_TEK_yerde_acilir():
    """Statik tel tuzağı: `launch_persistent_context` tek çağrı noktası.

    İkinci bir çağrı eklenirse proxy oraya geçirilmeyi unutulabilir; clearance
    yolunda unutulursa Cloudflare cookie'si YANLIŞ IP'yle alınıp profile
    yazılır ve sonraki proxy'li çekimlerde sessizce reddedilir.
    """
    kaynak = pathlib.Path("app/core/fetch.py").read_text(encoding="utf-8")
    assert kaynak.count("launch_persistent_context(") == 1
```

- [ ] **Adım 2: Testleri çalıştır, başarısız olduklarını gör**

Çalıştır: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_proxy.py -q`

Beklenen: `AttributeError: module 'core.fetch' has no attribute '_proxy_ayari'`
ve tel tuzağında `assert 2 == 1`.

- [ ] **Adım 3: `_proxy_ayari` ve `_baglam_ac` fonksiyonlarını yaz**

`app/core/fetch.py:9` satırındaki import'a `unquote` ekle. Mevcut hâli:

```python
from urllib.parse import urljoin, urlparse
```

Yenisi (`urljoin` KORUNUR — başka yerde kullanılıyor):

```python
from urllib.parse import unquote, urljoin, urlparse
```

`_fetch_via_launch` fonksiyonunun HEMEN ÜSTÜNE ekle:

```python
def _proxy_ayari() -> dict | None:
    """`FETCH_PROXY` → Playwright proxy sözlüğü; ayarsızsa None.

    Bulut sunucuda çekim residential proxy üzerinden çıkmak ZORUNDA: Cloudflare
    veri merkezi ASN'lerini otomatik en yüksek risk skoruna alıyor ve stealth
    ayarları bunu kurtarmıyor (ölçüm: VPS IP'sinde challenge'ların ~%5'i
    geçiliyor). Ev makinesinde değişken boştur, akış doğrudan çıkar.

    Biçim: `http://kullanici:parola@host:port`. Kimlik bilgisi AYRI alanlara
    ayrıştırılır — Playwright `server` içine gömülmüş kullanıcı/parolayı yok
    sayar ve kimlik doğrulaması sessizce başarısız olur.
    """
    ham = os.getenv("FETCH_PROXY", "").strip()
    if not ham:
        return None
    parca = urlparse(ham)
    ayar: dict[str, str] = {
        "server": f"{parca.scheme}://{parca.hostname}:{parca.port}"
    }
    if parca.username:
        ayar["username"] = unquote(parca.username)
    if parca.password:
        ayar["password"] = unquote(parca.password)
    return ayar


def _baglam_ac(p, headless: bool):
    """Kalıcı profille Chromium bağlamı açar — çekim ve clearance için ORTAK.

    İki çağıran aynı parametre bloğunu ayrı ayrı taşıyordu. Proxy'yi ikisine
    ayrı eklemek, birinin unutulması riskini taşır: clearance yolunda
    unutulursa Cloudflare cookie'si proxy DIŞINDAN alınıp profile yazılır ve
    sonraki proxy'li çekimlerde sessizce reddedilir.
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        user_agent=USER_AGENT,
        locale="en-US",
        viewport={"width": 1280, "height": 800},
        args=LAUNCH_ARGS,
        proxy=_proxy_ayari(),
    )
    context.add_init_script(STEALTH_JS)  # tüm sayfalara, goto'dan önce
    return context
```

- [ ] **Adım 4: İki çağıranı ortak yardımcıya bağla**

`_fetch_via_launch` gövdesini şununla değiştir:

```python
def _fetch_via_launch(
    url: str, headless: bool, site: dict, host: str, timeout_ms: int
) -> str:
    """Paket Chromium'u kalıcı profille başlatıp sayfayı çeker (varsayılan akış)."""
    with sync_playwright() as p:
        context = _baglam_ac(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            return _extract_html(page, url, site, host, timeout_ms, _LAUNCH_SOLVE_HINT)
        finally:
            context.close()
```

`_refresh_clearance_via_launch` gövdesini şununla değiştir:

```python
def _refresh_clearance_via_launch(
    url: str, headless: bool, host: str, timeout_ms: int
) -> None:
    """Paket Chromium kalıcı profilini açıp hafif sayfa ziyareti yapar."""
    with sync_playwright() as p:
        context = _baglam_ac(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _visit_clearance_page(page, url, host, timeout_ms, _LAUNCH_SOLVE_HINT)
        finally:
            context.close()
```

(`PROFILE_DIR.mkdir(...)` satırları artık `_baglam_ac` içinde; iki fonksiyondan da
kaldırılmış olmalı.)

- [ ] **Adım 5: Testlerin geçtiğini doğrula**

Çalıştır: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_proxy.py -q`
Beklenen: 9 passed.

- [ ] **Adım 6: Tüm paketin yeşil kaldığını doğrula**

Çalıştır: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Beklenen: 537 + 9 = 546 passed, 0 failed.

Başarısız olan varsa ortaklaştırma bir davranışı bozmuştur — düzelt, devam etme.

- [ ] **Adım 7: `.env.ornek` dosyasına değişkeni belgele**

Kök dizinde `.env.ornek` yoksa oluştur, varsa ekle:

```
# Çekim trafiğini residential proxy üzerinden çıkarır. BULUT SUNUCUDA ŞART:
# Cloudflare veri merkezi IP'lerini reddeder. Ev makinesinde BOŞ bırak.
# Parolada @ ya da : varsa yüzde-kodla (@ -> %40).
FETCH_PROXY=
```

---

### Görev 2: Kaynak engelleme

**Dosyalar:**
- Değiştir: `app/core/fetch.py` (`_extract_html` fonksiyonu)
- Test: `tests/test_fetch_kaynak_engelleme.py` (yeni)

**Arayüzler:**
- Üretir: `fetch.ENGELLENEN_KAYNAKLAR: set[str]`, `fetch._kaynak_engelle(route)`
- Tüketir: Görev 1'den bir şey tüketmez (bağımsız)

**Neden `_extract_html` içinde:** Roman çekiminin İKİ yolu var (`_fetch_via_launch`
ve `_fetch_via_cdp`) ve ikisi de `_extract_html`'e uğruyor. Engellemeyi oraya koymak
tek noktadan iki yolu da kapsar. `manga_fetch.py` bu fonksiyonu KULLANMAZ (kendi
`page.goto`'su var), yani manga sayfa görselleri etkilenmez.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_fetch_kaynak_engelleme.py` dosyasını oluştur:

```python
"""Roman sayfası çekilirken ağır kaynakları indirme.

Neden: Playwright bugün her bölüm sayfasında sitenin reklamlarını, logosunu ve
fontlarını da indiriyor; oysa koddan yalnız `site["content"]` seçicisindeki
metin alınıyor. Proxy GB başına ücretlendirildiği için bu doğrudan para yakar —
bölüm başına ~2 MB yerine ~300 KB, aylık gider 10 kat düşer (500 bölüm/ay'da
~$1 yerine ~$0,15).

`script` ve `stylesheet` ENGELLENMEZ ve engellenmemeli: Cloudflare challenge'ı
JavaScript ile çözülüyor, script kesilirse sayfa hiç açılmaz.

Ağa çıkmaz — route nesnesi sahtelenir.
"""
from core import fetch


class _SahteIstek:
    def __init__(self, tur):
        self.resource_type = tur


class _SahteRoute:
    def __init__(self, tur):
        self.request = _SahteIstek(tur)
        self.iptal = False
        self.devam = False

    def abort(self):
        self.iptal = True

    def continue_(self):
        self.devam = True


def test_agir_kaynaklar_iptal_edilir():
    for tur in ("image", "media", "font"):
        r = _SahteRoute(tur)
        fetch._kaynak_engelle(r)
        assert r.iptal and not r.devam, f"{tur} engellenmeliydi"


def test_cloudflare_icin_gerekli_turler_gecer():
    """`script` engellenirse CF challenge çözülemez ve çekim TÜMDEN durur."""
    for tur in ("document", "script", "stylesheet", "xhr", "fetch"):
        r = _SahteRoute(tur)
        fetch._kaynak_engelle(r)
        assert r.devam and not r.iptal, f"{tur} geçmeliydi"


def test_bilinmeyen_tur_gecer():
    """Beyaz liste değil KARA liste: tanımadığımız bir tür sayfayı bozmasın."""
    r = _SahteRoute("websocket")
    fetch._kaynak_engelle(r)
    assert r.devam


def test_script_kara_listede_DEGIL():
    """Tel tuzağı: biri 'daha çok tasarruf' diye script eklerse CF kırılır."""
    assert "script" not in fetch.ENGELLENEN_KAYNAKLAR
    assert "stylesheet" not in fetch.ENGELLENEN_KAYNAKLAR
    assert "document" not in fetch.ENGELLENEN_KAYNAKLAR
```

- [ ] **Adım 2: Testleri çalıştır, başarısız olduklarını gör**

Çalıştır: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_kaynak_engelleme.py -q`
Beklenen: `AttributeError: module 'core.fetch' has no attribute '_kaynak_engelle'`

- [ ] **Adım 3: Engelleme mantığını yaz**

`app/core/fetch.py` içinde `LAUNCH_ARGS` tanımının hemen ALTINA ekle:

```python
# Roman sayfasında İÇERİK DIŞINDA kalan ağır kaynaklar. Proxy GB başına
# ücretlendirildiği için bunları indirmek doğrudan para yakar: bölüm başına
# ~2 MB yerine ~300 KB (sitenin reklamları, logosu, fontları). Koddan yalnız
# `site["content"]` seçicisindeki metin alınıyor, hiçbiri kullanılmıyor.
#
# KARA liste, beyaz liste DEĞİL: tanımadığımız bir kaynak türü sayfayı
# bozmasın. `script` ve `stylesheet` BURAYA EKLENMEZ — Cloudflare challenge'ı
# JavaScript ile çözülüyor, script kesilirse sayfa hiç açılmaz.
ENGELLENEN_KAYNAKLAR = {"image", "media", "font"}


def _kaynak_engelle(route) -> None:
    """Ağır kaynakları iptal eder, kalan her şeyi geçirir."""
    if route.request.resource_type in ENGELLENEN_KAYNAKLAR:
        route.abort()
    else:
        route.continue_()
```

- [ ] **Adım 4: `_extract_html` içinde devreye al**

`_extract_html` (satır 426) içinde, docstring'den SONRA ve `try:` bloğundan ÖNCE
ekle — yani `resp = page.goto(...)` satırından önce route kurulmuş olmalı, sonra
kurulursa ilk istek engellemeden kaçar:

```python
    # Kaynak engelleme yalnız ROMAN yolunda ve yalnız açıkça istendiğinde.
    # Varsayılan kapalı: Cloudflare'in görsel bileşenleri (Turnstile) kaynak
    # engellemeden etkilenebilir ve ev makinesinde trafiğin maliyeti yok.
    # Sunucuda açılır; doğrulama sırası önce proxy'yi TEK BAŞINA sınar
    # (bkz. Görev 5), böylece arıza çıkarsa suçlu belli olur.
    if os.getenv("FETCH_BLOCK_ASSETS", "").strip() == "1":
        page.route("**/*", _kaynak_engelle)
```

- [ ] **Adım 5: Testlerin geçtiğini doğrula**

Çalıştır: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_kaynak_engelleme.py -q`
Beklenen: 4 passed.

- [ ] **Adım 6: Tüm paket yeşil**

Çalıştır: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Beklenen: 550 passed.

- [ ] **Adım 7: `.env.ornek` dosyasına ekle**

```
# Roman çekerken resim/font/medya indirme (proxy trafiğini ~10 kat düşürür).
# Sunucuda 1 yap. Önce proxy'yi TEK BAŞINA doğrula, sonra bunu aç.
FETCH_BLOCK_ASSETS=
```

---

### Görev 2.5: Proxy'yi EV MAKİNESİNDE doğrula (karar noktası)

**Dosyalar:** kod değişikliği yok.

**Bu adım sunucudan ÖNCE gelir ve planın gerçek karar noktasıdır.** Proxy
kullanıldığında çıkış IP'si proxy'nin havuzundan gelir; evden mi sunucudan mı
bağlandığın Cloudflare açısından fark etmez. Yani bu test, sunucudaki testin
geçerli bir vekilidir — ve sunucu kiralamadan, kurulum emeği harcamadan yapılır.

Sıralama gerekçesi: harcanan tek para $5 proxy. Eğer proxy bu siteleri geçemiyorsa
bunu ÖNCE öğrenmek, sunucu kurup taşıma yaptıktan sonra öğrenmekten çok ucuzdur.

- [ ] **Adım 1: DataImpulse hesabı aç ve $5 yükle**

Residential paket, $1/GB, trafik süresiz (aylık abonelik DEĞİL — harcanana kadar
durur, sunucu değişse de geçerli). Panelden endpoint, kullanıcı adı ve parolayı al.

- [ ] **Adım 2: Ev makinesinde `.env`'e geçici olarak ekle**

```
FETCH_PROXY=http://KULLANICI:PAROLA@gw.dataimpulse.com:823
```

Parolada `@` ya da `:` varsa yüzde-kodla (`@` → `%40`).

- [ ] **Adım 3: Proxy üzerinden tek bölüm çek**

Sunucuyu başlat (`start.bat`) ve çevrilmemiş bir bölümü zorla çek:

```powershell
curl.exe -s "http://localhost:8000/api/chapter?url=https://freewebnovel.com/novel/shadow-slave/chapter-382&refetch=1"
```

**Beklenen:** Türkçe çeviri döner → proxy Cloudflare'i geçiyor, plan devam eder.

**`error_class: CloudflareChallenge` dönerse:** sırayla dene (a) DataImpulse
panelinden farklı ülke/oturum tipi, (b) `FETCH_HEADLESS=0` ile bir kez görünür
pencerede elle çözüp profile cookie yaz. İkisi de olmazsa proxy yolu bu siteler
için kapalıdır → **plan durur**, scraping API alternatifi yeniden değerlendirilir.
Kaybedilen: $5. Sunucu parası ve kurulum emeği harcanmamış olur.

- [ ] **Adım 4: Engellemeyi de ev makinesinde sına**

`.env`'e `FETCH_BLOCK_ASSETS=1` ekle, sunucuyu yeniden başlat, başka bir bölüm çek.
Çeviri dönüyorsa engelleme Cloudflare'i bozmuyor demektir. Bozuyorsa değişkeni boşa
çevir ve engellemesiz devam et (aylık ~$1, hâlâ kabul edilebilir).

- [ ] **Adım 5: Panelden bölüm başına trafiği oku**

Engellemeli ve engellemesiz iki ölçümü not et. Bu, aylık gider tahminini gerçek
veriye oturtur ve sunucudaki ölçümle karşılaştırma tabanı olur.

- [ ] **Adım 6: `FETCH_PROXY`'yi ev `.env`'inden KALDIR**

Ev makinesi residential IP'de zaten; proxy üzerinden gitmek gereksiz trafik yakar.
Değişken yalnız sunucuda dolu kalacak.

---

### Görev 3: Sunucu kirala ve hazırla

**Dosyalar:** kod değişikliği yok (operasyon görevi).

Bu görev kullanıcı ile birlikte yapılır; adımlar sunucuda SSH ile koşar.

- [ ] **Adım 1: Oracle Cloud Free Tier'da ARM sunucu aç**

- Hesap aç, **Home Region** olarak Ampere A1 destekleyen bir bölge seç
  (Frankfurt / Amsterdam — Türkiye'ye yakın gecikme).
- Instance: **VM.Standard.A1.Flex**, 2 OCPU / 12 GB, Ubuntu 24.04 (ARM).
- "Out of capacity" hatası alınırsa: bölgeyi değiştirmeyi dene, birkaç saat
  arayla tekrarla. **İki gün içinde yer çıkmazsa Adım 2'ye geç.**

- [ ] **Adım 2: (Yalnız Oracle olmazsa) Contabo sunucu aç**

- Cloud VPS 10 (€4,5/ay), Ubuntu 24.04, bölge: Almanya.
- Kod tarafı aynı; yalnız güvenlik duvarı adımı basitleşir.

- [ ] **Adım 3: Sistem bağımlılıklarını kur**

```bash
sudo apt update && sudo apt install -y \
  python3.12 python3.12-venv python3-pip git fonts-dejavu
```

`fonts-dejavu` şart: `import_translate._FONT_CANDIDATES` Türkçe glif için
`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` yolunu arıyor; yoksa PDF
çevirisi gömülü `helv` fontuna düşer ve Türkçe karakterler bozulur.

- [ ] **Adım 4: Projeyi klonla ve sanal ortamı kur**

```bash
git clone <repo-url> ~/novel-cevirmen
cd ~/novel-cevirmen
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium
```

`--with-deps` Chromium'un sistem kütüphanelerini de kurar; onsuz headless
Chromium açılmaz.

- [ ] **Adım 5: Testleri sunucuda çalıştır (port doğrulaması)**

```bash
cd ~/novel-cevirmen && .venv/bin/python -m pytest tests/ -q
```

Beklenen: 550 passed. Burada bir hata çıkarsa Linux portunda gözden kaçan bir
şey var demektir — taşımaya devam etmeden çöz.

---

### Görev 4: Veri taşıma, yapılandırma ve servis

**Dosyalar:**
- Oluştur: `~/novel-cevirmen/.env` (sunucuda, elle)
- Oluştur: `/etc/systemd/system/novel-cevirmen.service` (sunucuda)

- [ ] **Adım 1: Veriyi sunucuya kopyala**

Ev makinesinden (PowerShell):

```powershell
scp cache\chapters.db kullanici@SUNUCU:~/novel-cevirmen/cache/
scp -r cache\media kullanici@SUNUCU:~/novel-cevirmen/cache/
scp .env kullanici@SUNUCU:~/novel-cevirmen/.env
```

`cache/` dizini sunucuda yoksa önce `mkdir -p ~/novel-cevirmen/cache`.

**Kopyalanmaz:** `.venv/`, `cache/.pw-profile*`, `cache/.chrome-cdp`,
`__pycache__/`. Toplam ~950 MB; hepsi sunucuda yeniden oluşur.

- [ ] **Adım 2: Proxy hesabını aç ve `.env`'i tamamla**

- DataImpulse'ta hesap aç, $5 yükle (residential, $1/GB, trafik süresiz).
- Panelden endpoint + kullanıcı adı + parolayı al.
- Sunucuda `.env`'e ekle (parolada `@` varsa `%40` diye yüzde-kodla):

```
FETCH_PROXY=http://KULLANICI:PAROLA@gw.dataimpulse.com:823
FETCH_BLOCK_ASSETS=
FETCH_CDP_URL=
```

`FETCH_BLOCK_ASSETS` şimdilik BOŞ — Görev 5'te proxy tek başına doğrulandıktan
sonra açılacak. `FETCH_CDP_URL` boş kalır: sunucuda gerçek Chrome yok, akış paket
Chromium yoluna düşer (`_fetch_locked` bu yedeklemeyi kendi yapıyor).

```bash
chmod 600 ~/novel-cevirmen/.env
```

- [ ] **Adım 3: Tailscale kur ve HTTPS'i aç**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve --bg 8000
tailscale status --json | grep DNSName
```

Çıkan `https://<makine>.<tailnet>.ts.net` adresi telefondan kullanılacak adres.
Düz IP KULLANILMAZ: Service Worker ve Cache API yalnız güvenli bağlamda çalışır,
düz IP'de çevrimdışı kayıt sessizce devre dışı kalır (CLAUDE.md'deki ölçüm).

`tailscale funnel` ÇALIŞTIRILMAZ — sunucu public'e açılmaz.

- [ ] **Adım 4: systemd servisini kur**

```bash
sudo tee /etc/systemd/system/novel-cevirmen.service > /dev/null <<'EOF'
[Unit]
Description=Novel Cevirmen
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/novel-cevirmen
ExecStart=/home/ubuntu/novel-cevirmen/.venv/bin/python app/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now novel-cevirmen
systemctl status novel-cevirmen
```

`User` ve yollar dağıtıma göre değişir (Contabo'da genelde `root` ya da açtığın
kullanıcı). Günlükler: `journalctl -u novel-cevirmen -f`.

- [ ] **Adım 5: Sunucu ayakta mı doğrula**

```bash
curl -s localhost:8000/api/books | head -c 200
```

Beklenen: kitap listesi JSON'u (8 kitap). Boş dönerse `chapters.db` kopyalanmamış
ya da yanlış yerde demektir.

---

### Görev 5: Canlı doğrulama ve trafik ölçümü

**Dosyalar:** kod değişikliği yok.

Sıralama load-bearing: proxy ile engelleme AYNI ANDA açılırsa, çekim bozulduğunda
hangisinin suçlu olduğu bilinemez.

- [ ] **Adım 1: Proxy'yi TEK BAŞINA sına (asıl sınav)**

`FETCH_BLOCK_ASSETS` boşken, sunucuda tek bir bölüm çek:

```bash
curl -s "localhost:8000/api/chapter?url=https://freewebnovel.com/novel/shadow-slave/chapter-382&refetch=1" \
  | head -c 400
```

**Beklenen:** Türkçe çeviri döner.

**`error_class: CloudflareChallenge` dönerse:** proxy CF'i geçemiyor. Sırasıyla
dene: (a) DataImpulse panelinden farklı ülke/oturum, (b) Evomi ($0,49/GB) gibi
başka sağlayıcı, (c) `FETCH_HEADLESS=0` ile bir kez elle çözüm (sunucuda Xvfb
gerekir). Üçü de olmazsa proxy yolu bu site için kapalı demektir — plan durur ve
scraping API alternatifi yeniden değerlendirilir.

- [ ] **Adım 2: Proxy kullanımını panelden doğrula**

DataImpulse panelinde tüketilen trafiği not et (bir bölümün kaç MB olduğunu
gösterir — engelleme öncesi taban ölçüm).

- [ ] **Adım 3: Kaynak engellemeyi aç**

```bash
sed -i 's/^FETCH_BLOCK_ASSETS=$/FETCH_BLOCK_ASSETS=1/' ~/novel-cevirmen/.env
sudo systemctl restart novel-cevirmen
```

- [ ] **Adım 4: Engelleme ile yeni bir bölüm çek**

```bash
curl -s "localhost:8000/api/chapter?url=https://freewebnovel.com/novel/shadow-slave/chapter-383&refetch=1" \
  | head -c 400
```

Türkçe çeviri dönmeli. Dönmüyorsa engelleme CF'i bozmuştur → `FETCH_BLOCK_ASSETS`
boşa çevir, proxy'li ama engellemesiz devam et (aylık ~$1, hâlâ kabul edilebilir).

Panelden trafiği tekrar kontrol et: bölüm başına düşüş görünmeli.

- [ ] **Adım 5: Telefondan uçtan uca doğrula**

- Telefonda Tailscale açık, `https://<makine>.<tailnet>.ts.net` adresine git.
- Ayarlar panelinde model seçimi görünüyor mu (sunucu ayarı okunuyor mu).
- Bir bölüm aç, okunuyor mu.
- Uygulamayı kapat, uçak moduna al, aç — indirilmiş bölüm açılıyor mu
  (Service Worker çalışıyor, yani güvenli bağlam doğru).

- [ ] **Adım 6: Ev bilgisayarını devreden çıkar**

- Telefonda birkaç gün sunucu üzerinden oku.
- `chapters.db` için düzenli yedek kur (Oracle hesabı geri alınırsa veri kaybı
  olmasın):

```bash
(crontab -l 2>/dev/null; echo "0 4 * * * cp ~/novel-cevirmen/cache/chapters.db ~/yedek-chapters-\$(date +\%u).db") | crontab -
```

Haftanın gününe göre 7 kopya döner.

- [ ] **Adım 7: Bir hafta sonra gerçek gideri ölç**

DataImpulse panelinden haftalık trafiği oku, 4 ile çarp → gerçek aylık gider.
Tahmin ~150 MB/ay (≈$0,15). Belirgin sapma varsa engellemenin çalışıp
çalışmadığını `journalctl` üzerinden kontrol et.

---

### Görev 6: Dokümantasyonu güncelle

**Dosyalar:**
- Değiştir: `CLAUDE.md` (Ortam değişkenleri tablosu)
- Değiştir: `KURULUM.md` (bulut kurulum bölümü ekle)

- [ ] **Adım 1: `CLAUDE.md` ortam değişkenleri tablosuna iki satır ekle**

| Değişken | Zorunlu | Ne işe yarar |
satırlarının arasına:

```markdown
| `FETCH_PROXY` | Hayır | Çekimi residential proxy üzerinden çıkarır. **Bulut sunucuda ŞART** — Cloudflare veri merkezi IP'lerini reddeder (ölçüm: VPS IP'sinde challenge'ların ~%5'i geçiliyor). Biçim `http://kullanici:parola@host:port`; parolada `@` varsa yüzde-kodla. Boşsa doğrudan çıkılır |
| `FETCH_BLOCK_ASSETS` | Hayır | `1` → roman çekerken resim/font/medya indirilmez. Proxy trafiğini ~10 kat düşürür (bölüm başına ~2 MB → ~300 KB). `script`/`stylesheet` ASLA engellenmez: CF challenge JS ile çözülür. Manga yolu etkilenmez (`_extract_html`'den geçmez) |
```

- [ ] **Adım 2: `KURULUM.md` sonuna "Bulut sunucu" bölümü ekle**

Görev 3, 4 ve 5'in adımlarını sırayla özetle. Bu, Windows-ikinci-PC kurulumunun
yerini ALMAZ, yanına eklenir — iki dağıtım biçimi de geçerli kalır.

- [ ] **Adım 3: Testler hâlâ yeşil**

Çalıştır: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Beklenen: 550 passed.

---

## Uygulama sırası ve bağımlılıklar

1. **Görev 1 ve 2** ev makinesinde yapılır, sunucu gerekmez. Bağımsızdırlar ama
   sırayla yapılmaları önerilir (ikisi de `fetch.py`'ye dokunuyor).
2. **Görev 3** Oracle kapasitesine bağlı — belirsiz süre alabilir. Görev 1-2 bu
   beklerken bitirilebilir.
3. **Görev 4** Görev 1-3'ün hepsini gerektirir.
4. **Görev 2.5 planın KARAR NOKTASIDIR** ve sunucudan ÖNCE gelir: proxy
   Cloudflare'i geçemezse plan orada durur, scraping API alternatifi yeniden
   değerlendirilir. Bu sıralama kayıp tavanını $5'te tutar — sunucu kirası ve
   kurulum emeği henüz harcanmamış olur. Görev 5 artık bir karar noktası değil,
   sunucuda aynı sonucun alındığını teyit eden doğrulamadır.
5. **Görev 6** en sonda.
