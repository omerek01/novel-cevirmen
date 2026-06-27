# Tasarım Dokümanı: Kişisel Web Roman Çeviri Okuyucusu

> Office-hours çıktısı — 2026-06-22. Yol 1 (kişisel kullanım + öğrenme).

## Amaç
Telefonda, **novelbin.me** (veya .co) üzerindeki İngilizce romanları kopyala-yapıştır
olmadan, **isimleri bozmadan** Türkçe okumak.

## Hedef DEĞİL
Satmak, başkalarına açmak, çok-site desteği (şimdilik sadece novelbin), mükemmel UI.

## Çözdüğü 3 dert
1. Telefonda manuel kopyalama yok → backend bölümü kendi çeker.
2. İsimler Türkçeye çevrilmez → sözlük + isim-koruyan prompt.
3. "Sonraki bölüm" tek tıkla otomatik.

## Mimari (A — Mobil PWA)
```
[Telefon tarayıcı / PWA]
        │  URL gönder  /  "sonraki bölüm"
        ▼
[Backend API]
   1. Çekme katmanı → Cloudflare'i aşıp bölüm metnini al
   2. Sözlük motoru → bu roman için kayıtlı isimler/terimler
   3. Çeviri → LLM'e (metin + sözlük + "isimleri çevirme" talimatı)
   4. Yeni isim algıla → sözlüğe öner/kaydet
        ▼
[Temiz okuma ekranı]  +  [Sözlük düzenleme ekranı]
```

## Bileşen kararları

### 1. Çekme katmanı (en riskli parça — hazırı kullan)
- novelbin **Cloudflare arkasında** (saf fetch = 403). Saf istek çalışmaz.
- novelbin.me, `lncrawl` (lightnovel-crawler) tarafından **açıkça desteklenen** site.
- Öneri: **FlareSolverr** (Cloudflare'i headless tarayıcıyla çözen proxy) + `BeautifulSoup`
  ayrıştırma. Alternatif: `lncrawl`'ın novelbin modülünü ödünç al.

### 2. Sözlük & isim-koruma motoru (kalp)
- Roman başına `glossary.json`: `{ "Kim Dokja": "Kim Dokja", "Sky": "Sky" }` (kaynak → korunacak hali).
- LLM sistem talimatı: *"Bu sözlükteki özel isimleri ASLA çevirme. Yeni özel isim
  görürsen `detected_names` alanında döndür."*
- LLM yapılandırılmış çıktı: `{ translation: "...", detected_names: ["Han Sooyoung"] }`.
- Yeni isimler kullanıcıya "sözlüğe ekle?" diye sunulur; manuel terim de eklenebilir.

### 3. Çeviri
Kendi API anahtarın — **Gemini Flash** (çok ucuz, EN→TR iyi). Abonelik yok.

### 4. Sonraki bölüm
Çekme katmanı sayfadaki "next chapter" linkini de döndürür; "sonraki" deyince çeker.

### 5. ePub (Faz 3)
Çevrilmiş bölümleri biriktir, `epub` kütüphanesiyle dosya üret.

## Önerilen stack
- **Backend:** Python + FastAPI (FlareSolverr/lncrawl Python uyumlu).
- **Frontend:** Vite + React, mobil-öncelikli PWA (okuma ekranı + sözlük ekranı).
- **Depolama:** Başta dosya/SQLite yeter.
- **LLM:** Gemini API (kendi anahtarın).

## Yol haritası
- **Faz 0 — Çekirdek kanıtı:** novelbin'den tek bölüm çek (FlareSolverr) → Gemini ile
  isim-koruyan Türkçe çıktıyı terminalde bastır. UI yok. *Bu çalışırsa proje çalışır.*
- **Faz 1 — Okuma + sonraki bölüm:** Basit PWA, URL ver → oku → sonraki bölüm.
- **Faz 2 — Sözlük:** Otomatik isim algılama + düzenleme ekranı.
- **Faz 3 — ePub + cila.**

## Riskler
1. **Cloudflare kırılganlığı** — novelbin korumayı sıkılaştırırsa çekme bozulur.
   Azaltma: FlareSolverr/lncrawl güncel tut.
2. **Yasal gri alan** — kişisel kullanımda sorun yok; **yayınlama/satma yapma**.
3. **API maliyeti** — uzun romanlarda token birikir; Gemini Flash ile düşük, yine de izle.

## İlk somut adım
Faz 0: FlareSolverr çalıştır → bir novelbin bölüm URL'iyle test (HTML geliyor mu?) →
gelen metni Gemini'ye "isimleri koru" talimatıyla gönder → terminalde Türkçe çıktıyı gör.

## Kaynaklar
- lncrawl (novelbin destekli): https://github.com/lncrawl/lightnovel-crawler
- Seraph Novel DL (Cloudflare bypass): https://github.com/HyakuAr/Seraph-Novel-DL
- web-novel-scraper: https://pypi.org/project/web-novel-scraper/
