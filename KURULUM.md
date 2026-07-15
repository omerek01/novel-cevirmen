# Novel Çevirmen — Diğer Bilgisayara Kurulum (7/24 Tailscale Sunucusu)

Bu kılavuz, backend'i **ikinci bir Windows bilgisayara** taşıyıp Tailscale üzerinden
telefondan erişmek içindir. Mimari: backend o bilgisayarda çalışır, Tailscale özel
ağında telefon + bilgisayar birbirini görür (public internete kapalı, güvenli).

> **Kullanım modu:** "İhtiyaç anında açarım." Bilgisayar kapalıyken erişilemez;
> açıp giriş yapınca her şey otomatik başlar (~1-2 dk). Adım 7 bunu kurar.

---

## Önkoşullar (diğer bilgisayarda)

1. **Windows 10/11**
2. **Google Chrome** kurulu (freewebnovel'in Cloudflare'ini aşmak için şart)
3. **Python 3.12** — https://www.python.org/downloads/
   - Kurulumda **"Add python.exe to PATH"** kutusunu işaretle.
4. **Tailscale** — https://tailscale.com/download/windows
   - Kurduktan sonra **bu projedeki ile AYNI hesapla** giriş yap (`m.omerek.01@...`).

---

## Adım 1 — Tailscale'i kur ve giriş yap

Tailscale'i kur, aynı hesapla oturum aç. Doğrula (PowerShell):

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" ip -4
```

Bir `100.x.x.x` adresi vermeli. **Bu adresi not al** — telefondan buraya bağlanacaksın.
(Telefonundaki Tailscale uygulaması da aynı hesapta açık olmalı.)

## Adım 2 — Proje klasörünü kopyala

`novel-cevirmen` klasörünü bu bilgisayardan diğerine taşı (USB / ağ / Tailscale Taildrop).

**Kopyalarken DAHİL ET:** tüm kod + `requirements.txt` + **`.env`** (gizli; API
anahtarların burada, git ile gelmez, mutlaka elle kopyala).

**Kopyalama, taşımayı hızlandırmak için ATLA** (diğer bilgisayarda yeniden oluşacak):
`.venv\`, `cache\`, `__pycache__\`, `.git\` (istersen).

> `.env` yoksa çeviri çalışmaz. Kontrol: klasörde `.env` dosyası görünüyor mu?

## Adım 3 — Sanal ortam ve bağımlılıklar

Proje klasöründe PowerShell aç:

```powershell
cd C:\...\novel-cevirmen
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Son komut Playwright'ın kendi tarayıcısını indirir (CF cookie profili için kullanılır).

## Adım 4 — İlk çalıştırma

```
start.bat
```

Açılınca:
- Bir **Chrome penceresi** açılır (CDP, 9222). **KAPATMA.**
- Sunucu başlar; pencerede 3 adres görünür (Tailscale / Wi-Fi / localhost).
- freewebnovel'de ilk Cloudflare çıkarsa, açılan Chrome'da **bir kez** "I'm human"
  doğrulamasını geç; sonrası otomatik.

## Adım 5 — Telefondan eriş

Telefonda **Tailscale açıkken** tarayıcıdan:

```
http://<diger-bilgisayarin-tailscale-ip>:8000
```

(Adım 1'de not aldığın `100.x.x.x`.) PWA olarak "Ana ekrana ekle" diyebilirsin.

## Adım 6 — (Önerilir) Windows Güvenlik Duvarı izni

İlk çalıştırmada Windows "izin ver" sorarsa **Özel ağlar** için izin ver. Sormazsa
ve telefondan açılmıyorsa, 8000 portuna gelen bağlantıya izin ver (PowerShell, yönetici):

```powershell
New-NetFirewallRule -DisplayName "NovelLink 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000
```

## Adım 7 — Açılışta otomatik başlatma

Böylece bilgisayarı her açıp giriş yaptığında `start.bat` kendiliğinden çalışır:

1. `Win + R` → `shell:startup` → Enter (Başlangıç klasörü açılır).
2. `start.bat` dosyasına **sağ tık → Kısayol oluştur**.
3. Oluşan kısayolu **Başlangıç klasörüne** taşı.

Artık: bilgisayarı aç → giriş yap → 1-2 dk içinde sunucu + Chrome hazır → telefondan gir.

---

## Sorun Giderme

| Belirti | Çözüm |
|---|---|
| Telefondan açılmıyor | Telefonda Tailscale açık mı? Bilgisayar açık mı? Doğru `100.x.x.x` mi? Adım 6 (firewall). |
| "Çevirmiyor / CF" hatası | `start.bat` ile açılan gerçek Chrome penceresi açık mı? Bir kez CF doğrulaması yapıldı mı? |
| Çeviri boş/hata | `.env` kopyalandı mı, içinde Gemini anahtarı var mı? |
| `playwright` hatası | `.\.venv\Scripts\python.exe -m playwright install chromium` tekrar çalıştır. |

## Güvenlik notu

Sunucu yalnızca senin Tailscale ağındaki cihazlardan erişilebilir; public internete
**kapalı**. Bu yüzden ayrı şifreye gerek yok. Tailscale hesabına başka cihaz/kişi
eklemediğin sürece kimse erişemez.
