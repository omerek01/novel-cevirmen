# PLAN — Buluta Taşıma (cihazsız 7/24 sunucu)

**Tarih:** 2026-09-11 · **Durum:** UYGULANDI (2026-09-12)

---

## SONUÇ — gerçekleşen mimari (aşağıdaki tasarımdan FARKLI)

Uygulama sırasında iki ölçüm tasarımın temel varsayımlarını çürüttü. Aşağıdaki
bölümler tarihsel kayıt olarak duruyor; **bugünkü gerçek** budur:

| Tasarımda | Gerçekleşen |
|---|---|
| Sunucuda Playwright + Chromium çalışacak | **Chromium kurulmadı**, gerekmiyor |
| Residential proxy ŞART (CF veri merkezi IP'sini reddediyor) | **Proxy gerekmedi** — engel IP değil TLS'ti |
| Aylık ~$0,15 proxy gideri | **₺0** |
| Sunucu: Oracle Free (ARM) ya da Contabo | **Google Cloud e2-micro** (Oracle kaydı reddedildi) |
| Bölüm çekimi ~2 MB / 68 sn | **~60 KB / 0,5 sn** |

**Bulgu 1 — Cloudflare bölüm sayfalarını korumuyor.** Koruma ANA SAYFADA. 5 kitap
x 12 bölüm ölçüldü (bölüm 4'ten 1880'e): hepsi HTTP 200, ayrıştırılan metin
önbellektekiyle birebir aynı. Playwright bu iş için gereksizmiş.

**Bulgu 2 — sunucudaki 403'ün sebebi IP değil TLS parmak iziydi.** Beş ayrı
ülkeden beş residential proxy IP'si denendi, **beşi de 403** (0/5). Aynı anda ev
makinesinden (Windows) aynı URL 200 veriyordu. Fark: Linux OpenSSL'in JA3 imzası.
`curl_cffi` ile Chrome TLS imzası taklit edilince sunucudan da 200 geldi, proxy
olmadan. Bu, aşağıdaki "Kısıt" bölümünün (veri merkezi IP'si reddediliyor)
kısmen yanlış olduğunu gösterir: reddedilen IP değil, istemci imzasıydı.

**Proxy parası boşa gitmedi ama kullanılmıyor:** DataImpulse'taki $5 trafiği
süresiz duruyor, `.env`'de satır yorumlanmış hâlde (silinmedi). Site ileride
korumayı bölümlere yayarsa geri açılabilir.

Güncel dağıtım bilgisi ve bedava katman şartları: `CLAUDE.md` → "Bulut sunucu".

---

## Amaç

Backend'i evdeki bilgisayardan çıkarıp bir bulut sunucuda 7/24 çalıştırmak. Hedef:
telefondan her an erişilebilsin, evde hiçbir cihaz açık kalmasın, aylık gider
mümkün olduğunca sıfıra yakın olsun.

## Kısıt: Cloudflare, veri merkezi IP'sini reddediyor

Projenin buluta OLDUĞU GİBİ taşınamamasının tek sebebi `fetch.py`. Kaynak siteler
(freewebnovel, novelbin) Cloudflare arkasında ve CF 2026 itibarıyla öncelikli olarak
**IP itibarına** bakıyor: veri merkezi ASN'lerinden gelen istek, parmak izi ne kadar
iyi taklit edilirse edilsin otomatik olarak en yüksek risk skoruna alınıyor. Ölçülen
oran: VPS IP'sinden stealth Playwright, CF challenge'larının ancak **~%5'ini** geçiyor.

Bugünkü kurulumun çalışmasının sebebi teknik üstünlük değil, evdeki **residential
IP**. Yani "ucuz VPS kirala, kodu taşı" yaklaşımı kod hatasıyla değil, IP itibarıyla
çöker — ve bu, hiçbir stealth ayarıyla düzelmez.

**Çözüm:** fetch trafiğini residential proxy üzerinden çıkarmak. Projenin geri kalanı
(çeviri, önbellek, PWA sunma) IP itibarına duyarlı DEĞİL; Gemini API zaten buluttan
çağrılıyor ve önbellek isabetinde hiç ağ isteği yok.

**Değerlendirilip elenen alternatif:** scraping API (ZenRows 5.000 kredi/ay bedava).
CF korumalı siteler "premium istek" sayılıp istek başına 10-25 kredi harcıyor, yani
bedava katman ~200-500 bölüm/ay ediyor. Ölçülen gerçek hacim (aşağıda) 422-500
bölüm/ay, yani tam sınırda — bedava katman ilk ay tükenir. Üstelik `fetch.py`'nin
CF çözme ve site-özel ayrıştırma mantığı yeniden yazılırdı. Proxy yolu hem daha ucuz
hem mevcut kodu koruyor.

## Ölçülen hacim (2026-09-11, üretim önbelleğinden)

| ölçüt | değer |
|---|---|
| son 30 günde çevrilen bölüm | 422 |
| kullanıcı beyanı | ~500/ay |
| toplam bölüm | 667 (649 metin + 18 manga) |
| kitap | 8 |
| `chapters.db` | 11,7 MB |
| `cache/media` | 125 MB |
| `cache/` toplam | 1,1 GB (gerisi Chrome profilleri — taşınmaz) |

## Mimari

```
[Telefon] ──Tailscale HTTPS──► [Bulut sunucu · Linux]
                                   ├── FastAPI + SQLite + PWA   (değişmez)
                                   ├── Playwright ──proxy──► kaynak site   (YENİ)
                                   └── Gemini API               (değişmez)
```

Tek sunucu, bugünkü tek-süreç mimarisi korunuyor. Toplu çeviri işleri (`jobs.py`)
bellek-içi olmaya devam eder; sunucu 7/24 ayakta olduğu için bugünkü "yeniden başlarsa
iş kaybolur" kısıtı pratikte ortadan kalkar.

### Linux uyumluluğu — ölçüldü, sorun yok

Tarandı ve platforma özgü kod BULUNAMADI:

* `sys.platform` / `os.name` / `winreg` / sabit `C:\` yolu kullanan kod yok.
* `server.py`'deki `mimetypes.add_type` çağrıları Windows kayıt defteri hatasını
  düzeltmek için eklenmişti; Linux'ta zararsız (zaten doğru olanı ekliyor).
* `uvicorn.run(host="0.0.0.0", port=8000)` — değişiklik gerekmez.
* `import_translate._FONT_CANDIDATES` zaten Linux yolunu içeriyor
  (`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`) → `fonts-dejavu` paketi yeter.
* Playwright ARM64/Debian'ı resmen destekliyor (Oracle'ın ARM sunucusu için şart).

Taşınmayacak tek şey `scripts/start_chrome_cdp.py` (Windows Chrome'u CDP ile açar).
Sunucuda `FETCH_CDP_URL` boş kalır, akış paket Chromium + kalıcı profil yoluna düşer —
`fetch.py` bu yedeklemeyi zaten kendi yapıyor.

## Kod değişiklikleri

İkisi de küçük ve TDD ile yapılacak. Varsayılan davranış DEĞİŞMEZ: her iki özellik de
ortam değişkeniyle açılır, yani geliştirme makinesindeki kurulum aynen çalışmaya
devam eder.

### 1. `FETCH_PROXY` desteği

Playwright'ın kalıcı-profil başlatmasına `proxy=` parametresi eklenir. Değişken boşsa
bugünkü davranış birebir korunur.

Kapsam: `fetch.py` içindeki tarayıcı başlatma noktaları. `refresh_clearance` da aynı
yoldan geçtiği için CF cookie tazeleme proxy üzerinden çalışır — ayrıca iş gerekmez.

Test: proxy değişkeni verilince `launch_persistent_context`'e geçtiğini, verilmeyince
hiç geçmediğini doğrulayan birim testi (ağa çıkmaz, başlatma sahtelenir).

### 2. Kaynak engelleme (`FETCH_BLOCK_ASSETS`)

Roman sayfası çekilirken `image`, `font`, `media` istekleri iptal edilir.
`document`, `script`, `stylesheet` GEÇER — CF challenge JavaScript gerektirir, script
engellenirse challenge hiç çözülemez.

Gerekçe ölçüm: bugün Playwright her bölüm sayfasında sitenin reklamlarını, logosunu ve
fontlarını da indiriyor; oysa koddan yalnızca `#article` metni alınıyor. Kapak da
etkilenmez — `_kapak_adresi` HTML'den yalnızca ADRESİ okur, resmi indirmez.

Etki: bölüm başına ~2 MB → ~300 KB. Proxy GB başına ücretlendirildiği için bu, aylık
gideri **10 kat** düşürür (aşağıdaki maliyet tablosu).

Test: engelleme açıkken resim isteğinin iptal edildiğini, script/document isteğinin
geçtiğini doğrulayan birim testi.

## Taşınacak veri

**Gider:** `chapters.db` (11,7 MB), `cache/media/` (125 MB), `.env` (elle — git'e
girmez).

**Gitmez:** `.venv/`, `cache/.pw-profile*`, `cache/.chrome-cdp`, `__pycache__/`.
Toplam ~950 MB; hepsi sunucuda yeniden oluşur. CF cookie profili sıfırdan kurulur,
`refresh_clearance` ilk çekimde halleder.

## Sunucu

**Birinci tercih: Oracle Cloud Free Tier** (ARM Ampere, aylık ₺0). 2026'da bedava
katman 4 OCPU/24 GB'dan **2 OCPU/12 GB**'a indirildi; bu proje için hâlâ fazlasıyla
yeterli. Riskler gerçek ve kabul edildi: ARM kapasitesi sık sık "out of capacity"
veriyor (yer bulmak günler sürebilir) ve atıl hesaplar geri alınabiliyor.

**Yedek: Contabo** (€4,5/ay, 4 vCPU / 6-8 GB NVMe). Kapasite ve hesap riski yok.

Kod tarafı ikisinde de AYNI; yalnız kurulum adımları değişir (Oracle'da ek olarak
güvenlik listesi/iptables ayarı gerekir).

Süreç: önce Oracle'da yer aranır, çıkmazsa Contabo'ya düşülür.

### Servis

`start.bat` yerine **systemd** birimi: açılışta otomatik başlar, çökerse yeniden
kalkar, günlükler `journalctl`'e gider. Bugünkü "bilgisayarı açınca elle başlat"
adımı tamamen kalkar.

## Erişim ve güvenlik

Tailscale'de KALIR, public internete AÇILMAZ. Telefonda zaten kurulu ve HTTPS adresi
MagicDNS'ten geliyor; çevrimdışı kayıt (Service Worker + Cache API) güvenli bağlam
gerektirdiği için bu şart — düz IP'de çalışmaz (bkz. CLAUDE.md'deki ölçüm tablosu).

Sunucuyu internete açmak hem gereksiz (tek kullanıcı) hem de projenin "sadece kişisel
kullanım" çerçevesini bozar.

`.env` sunucuda 0600 izinle durur. API anahtarları git'e girmez, komut satırında
argüman olarak geçilmez.

## Maliyet (500 bölüm/ay)

| kalem | tutar |
|---|---|
| Sunucu (Oracle Free) | ₺0/ay |
| Sunucu (Contabo yedek) | €4,5/ay |
| Proxy, kaynak engellemeli (~150 MB/ay) | **~$0,15/ay** |
| Proxy, engellemesiz (~1 GB/ay) | ~$1/ay |
| Gemini | ₺0 (bedava katman + anahtar havuzu) |

Proxy sağlayıcı: **DataImpulse** — $1/GB düz tarife, $5 minimum yükleme, trafik
süresiz. $5, engellemeli kullanımda ~2,5 yıl yeter. (Alternatif: Evomi $0,49/GB.)

Kaynak engelleme bu yüzden opsiyonel değil, paketin ana parçası.

## Kapsam dışı

**Manga.** Kullanıcı kullanmıyor (667 bölümün yalnız 18'i, hiçbiri aktif okuma
değil). `manga_fetch.py` sayfa görsellerini GERÇEKTEN indirdiği için kaynak engelleme
o yolu bozar; bu yüzden engelleme yalnız roman yoluna uygulanır ve manga sunucuda
devre dışı kalır. Manga kodu SİLİNMEZ — geri dönüşü zor bir iş, ayrıca istenirse
ayrı bir görev olarak yapılır.

## Riskler

| risk | etki | önlem |
|---|---|---|
| Oracle'da ARM kapasitesi bulunamaz | gecikme | Contabo'ya düş (kod aynı) |
| Proxy + CF beklenenden zayıf geçer | çekim başarısız | önce TEK bölümle canlı doğrulama; başarısızsa Evomi/başka sağlayıcı dene |
| Proxy trafiği tahminden yüksek | gider artar | engelleme sonrası ilk hafta trafiği ölç |
| Oracle atıl hesabı geri alır | sunucu kaybı | `chapters.db` düzenli yedeklenir |

## Doğrulama sırası

1. Birim testler (proxy + engelleme), `tests/` yeşil.
2. Yerelde proxy ile TEK bölüm çekimi — CF geçiliyor mu.
3. Sunucuda TEK bölüm çekimi — asıl sınav (veri merkezi + proxy birlikte).
4. Telefondan HTTPS erişimi + çevrimdışı kayıt kontrolü.
5. Bir haftalık trafik ölçümü → gerçek aylık gider.
