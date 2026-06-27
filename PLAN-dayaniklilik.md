# Plan: Dayanıklılık Fazı (Faz 5)

> Bağlam: Faz 4 (okuma deneyimi) tamamlandı. Çalışma ağacına ayrıca sunucu-taraflı
> arka plan toplu çeviri (`jobs.py`/`pipeline.py`) eklendi. Bu plan, çekme/çeviri
> kırılınca uygulamanın **sessizce ölmesini** giderir: okuma ortasında graceful
> hata, ve gece-çalışan bulk işinin restart/uyku/clearance-bayatlamasına dayanması.
> Kişisel kullanım; LAN + paylaşılan SQLite. Mod: HOLD SCOPE (kapsam kilitli).

## Amaç
Bir bölüm çekilemeyince okuduğun yeri kaybetmemek, ne olduğunu ve ne yapacağını
anlamak; uzun bir toplu çeviriyi başlatıp sunucu uyusa/restart olsa bile kaldığı
yerden sürdürebilmek.

## Hedef DEĞİL
- Yeni Cloudflare bypass mekanizması (FlareSolverr/lncrawl). Playwright kalıcı profil
  zaten CF'i çözüyor — ikinci bypass GEREKSİZ (premise düzeltmesi, aşağıda).
- Çok-kaynak failover, indirme-geçmişi UI'ı, hesap/bulut senkron.
- Çeviri kalitesi / sözlük mantığı değişikliği.

## Premise düzeltmesi (neden "Cloudflare retry ekle" DEĞİL)
`fetch.py` halihazırda olgun: Playwright kalıcı profil + `cf_clearance` yeniden
kullanımı, stealth JS, üstel geri-çekilmeyle retry (geçici hatalar), kalıcı (CF
challenge / origin 52x) vs geçici ayrımı, `FETCH_HEADLESS=0` elle-çöz talimatlı
mesajlar. TODOS'un "lncrawl/FlareSolverr" maddesi **bayat**. Gerçek boşluk çekme
katmanında değil; **(a) hatanın reader'da sunumu** ve **(b) bulk işinin kalıcılığı**.

## Çözülen dertler
1. **Okuma ortasında çekim patlayınca son bölümü kaybetme:** `loadChapter` fetch'ten
   önce `readerBody`'yi gizliyor → hata gelince okunan metin yok oluyor, footer nav
   kapanıyor, geri dönüş yok.
2. **Bulk gece-ölümü:** iş bellek-içi (`_JOBS`); sunucu uyku/restart'ta sessizce
   kaybolur, istemci polling 404 alır, resume yok.
3. **Clearance bulk ortasında dolması:** headless bulk `FETCH_HEADLESS=0` elle-çözüm
   yapamaz → tüm run kalıcı hatayla ölür, ne olduğu net değil.
4. **Gözlemlenebilirlik:** job lifecycle log'u yok; `_prune` sonrası hata izi kaybolur.

---

## Kapsam (özellikler)

### R1 — Reader graceful-failure UX
- `loadChapter`: fetch BAŞARILI olana kadar mevcut bölümü **gizleme**. Yeni `isLoading`
  durumunu üst banner/spinner ile göster; `readerBody`'yi yalnızca `renderChapter`
  içinde (başarıda) değiştir.
- `renderError`: yıkıcı-olmayan **inline hata kartı** — son render edilen bölüm görünür
  kalır; kart "Tekrar dene" + (önceki bölüm yüklüyse) footer nav korunur.
- Hata sınıfına göre afordans: kalıcı CF challenge → `FETCH_HEADLESS=0` ile elle-çöz
  rehberi belirgin; geçici/network → "biraz sonra tekrar dene"; origin 52x → "kaynak
  sitenin sorunu". Mesaj sunucudan (`err.detail`) gelir; sınıf ipucu HTTP koduyla
  (502 geçici/CF, 503 çeviri, 500 yapılandırma) verilir.
- Etki alanı: `app/web/app.js`, `app/web/style.css`. Şema yok.

### R2 — Bulk job kalıcılığı (SQLite) + resume + single-flight
- Yeni `jobs` tablosu (kalıcı kaynak doğruluk); `_JOBS` bellek-içi dict yalnızca
  çalışan thread'in sıcak tutamağı olur, durum SQLite'a **her bölümden sonra checkpoint**
  edilir.
- **Checkpoint:** her bölüm bitince `cursor_url` (sıradaki url), `done`, `translated`,
  `state`, `message`, `updated_at` UPDATE edilir. Restart sonrası ilerleme kaybolmaz.
- **Single-flight:** `start_bulk`, aynı `slug` için `state='running'` satır varsa yeni
  iş açmaz; mevcut `job_id`'yi döndürür. (Fetch zaten serileştirildiği için paralel
  işin faydası yok; çift-sayım/çekişme önlenir.)
- **Resume:** sunucu açılışında `state='running'` satırlar `state='interrupted'`
  işaretlenir; istemci/endpoint `cursor_url`'den `count-done` kalan ile devam ettirebilir
  ("Devam et" düğmesi). 404 yerine anlamlı durum döner.
- **Connection kuralı:** SQLite bağlantıları thread-paylaşımsız → job thread'i KENDİ
  bağlantısını açar (`check_same_thread` tuzağı). Mevcut `cache`/`library` deseniyle
  hizalı; testte doğrulanır.
- Etki alanı: `app/core/jobs.py`, `app/core/db.py` (jobs tablosu + migration),
  `app/server.py` (resume endpoint + açılış taraması), `app/web/app.js` (resume UI).

### R3 — cf_clearance bayatlama → job duraklatma
- Bulk içinde kalıcı CF challenge `FetchError`'ı yakalanınca iş `state='paused'` +
  aksiyon mesajı: "Cloudflare doğrulaması gerekiyor; sunucuyu `FETCH_HEADLESS=0` ile
  başlatıp pencerede çözün, sonra Devam et." (Sessiz `error` yerine kurtarılabilir hal.)
- `cursor_url` korunur → çözümden sonra aynı yerden resume.
- Etki alanı: `app/core/jobs.py`, `app/web/app.js`.

### R4 — Gözlemlenebilirlik (job lifecycle log)
- Yapısal log (Python `logging`): job start/checkpoint(periyodik)/done/error/stopped/
  paused — `job_id`, `slug`, `done/total`, `state`, son hata. Gece çöken run iz bırakır.
- Etki alanı: `app/core/jobs.py`.

### R5 — Test + teknik borç
- `jobs`/`pipeline` birim testleri: `pipeline.get_or_translate` (cache-isabeti /
  refresh / hata yayılımı), `jobs._run` (stop bayrağı / `next_url` sonu / hata→state /
  checkpoint yazımı / resume), single-flight reddi. Sahte pipeline ile.
- `DB_PATH` enjekte edilebilir hale getir (mevcut TODOS borcu) → jobs testleri geçici
  DB'ye yazsın, monkeypatch gerekmesin.
- Etki alanı: `tests/test_jobs.py`, `tests/test_pipeline.py`, `app/core/db.py`.

---

## Veri modeli — `jobs` tablosu
```
jobs(
  id           TEXT PRIMARY KEY,   -- uuid4 hex
  slug         TEXT NOT NULL,
  start_url    TEXT NOT NULL,
  cursor_url   TEXT,               -- sıradaki işlenecek url (checkpoint)
  count        INTEGER NOT NULL,
  done         INTEGER NOT NULL DEFAULT 0,
  translated   INTEGER NOT NULL DEFAULT 0,
  state        TEXT NOT NULL,      -- running|done|stopped|error|paused|interrupted
  message      TEXT,
  created_at   REAL NOT NULL,
  updated_at   REAL NOT NULL
)
```
Migration: tablo yoksa `CREATE TABLE IF NOT EXISTS`; mevcut `db.ensure_column`
deseni sütun eklemeleri için kullanılır (geriye uyumlu, idempotent). `chapters`/`books`
şemasına dokunulmaz.

## Veri akışı — bulk job durum makinesi
```
            start_bulk(slug,start_url,count)
                       │  (single-flight: running varsa onu döndür)
                       ▼
   ┌──────────────► running ──────────────────────────────┐
   │                  │ her bölüm: pipeline.get_or_translate │
   │                  │   + SQLite checkpoint(cursor,done)    │
   │ resume           ├─ next_url yok ───────────► done       │
   │ (Devam et)       ├─ stop bayrağı ───────────► stopped    │
   │                  ├─ kalıcı CF challenge ────► paused ─────┤ (clearance çöz → resume)
   │                  └─ FetchError/Translate ───► error       │
   │                                                           │
   └──── sunucu açılışı: running → interrupted ◄───────────────┘
                              (resume ile running'e döner)
```

## Veri akışı — reader hata yolu (R1)
```
loadChapter(url)
  │ önceki bölüm GÖRÜNÜR kalır (gizleme yok)
  ▼ fetch /api/chapter
  ├─ 200 ──► renderChapter (readerBody'yi DEĞİŞTİR, footer nav güncelle)
  └─ hata ─► renderError inline kart (son bölüm korunur)
              ├─ 502 + CF challenge ─► "FETCH_HEADLESS=0 ile çöz" rehberi
              ├─ 502 origin 52x ─────► "kaynak sitenin sorunu, bekle"
              ├─ 502 geçici/network ─► "biraz sonra tekrar dene"
              └─ 503 çeviri / 500 ──► detay + Tekrar dene
            footer nav: önceki yüklü bölüm varsa AKTİF kalır
```

## Failure modes / edge cases
| # | Durum | Şu an | R-sonrası |
|---|---|---|---|
| 1 | Okuma ortasında çekim patlar | readerBody gizli → metin kaybolur | son bölüm korunur, inline hata + nav |
| 2 | Sunucu bulk ortasında restart | iş kaybolur, 404 | `interrupted` + cursor'dan resume |
| 3 | cf_clearance bulk ortasında dolar | tüm run `error`, sessiz | `paused` + elle-çöz rehberi + resume |
| 4 | Aynı kitaba 2x bulk tıklama | 2 thread çekişir, çift sayım | single-flight: mevcut işi döndür |
| 5 | İstemci kapalıyken iş biter | sonuç yalnızca bellekte, prune'da gider | SQLite'ta kalıcı, sonra okunur |
| 6 | Job thread DB'yi başka thread bağlantısıyla yazar | tanımsız (paylaşımlı conn) | thread-yerel bağlantı, testli |
| 7 | Resume sırasında bölümler zaten cache'te | yeniden çevirir (gereksiz API) | cache-isabeti → atlar (pipeline mevcut) |

## Migration güvenliği / rollback
- Yalnızca yeni tablo + (gerekirse) `ADD COLUMN`; mevcut `chapters.db` bozulmaz.
- `state` enum'u TEXT (şema-esnek); yeni durum eklemek migration gerektirmez.
- Rollback: `jobs` tablosu bağımsız; düşürmek diğer özellikleri etkilemez. Bellek-içi
  geri dönüş mümkün (kod geri alınırsa tablo aylak kalır, zarar yok).

## Test planı
- Backend (pytest): R5'teki jobs/pipeline birim testleri + jobs migration idempotensi
  (PRAGMA+CREATE 2x) + checkpoint roundtrip + single-flight reddi + resume-cursor.
- `DB_PATH` enjekte → tüm yeni testler geçici DB.
- Frontend (R1/R3 manuel QA): çekim hatasını tetikle (geçersiz url / FETCH kapalı),
  son bölümün korunduğunu, inline kartı, nav'ın aktif kaldığını, CF-rehberini doğrula;
  telefon + masaüstü.

## Riskler
1. **Thread + SQLite bağlantısı (R2):** paylaşımlı bağlantı `check_same_thread` hatası
   verir. Azaltma: job thread'i kendi bağlantısını açar; testte doğrula.
2. **Checkpoint yazım sıklığı:** her bölümde UPDATE — bölüm başına bir çeviri (saniyeler)
   yanında ihmal edilebilir; WAL/kısa transaction. Risk düşük.
3. **Resume çiftleme:** açılış taraması ile manuel "Devam et" aynı işi iki kez
   başlatabilir. Azaltma: resume de single-flight'tan geçer.

## Kapsam DIŞI (TODOS.md'ye)
- FlareSolverr/lncrawl ikinci bypass (premise gereği kesildi).
- Otomatik cf_clearance yenileme zamanlayıcısı, çok-kaynak failover, indirme-geçmişi UI.
- Bölüm-içi tam-metin arama / swipe (Faz 4'te zaten eklendi).

## İlk somut adım / sıra
R1 (reader graceful-failure) — tamamen frontend, en hızlı hissedilen kazanç, şema yok.
Sonra R5 (DB_PATH enjekte — R2 testlerinin ön koşulu), R2 (jobs tablosu + checkpoint +
single-flight + resume), R3 (paused/clearance), R4 (log). En son uçtan uca QA.

---

# GSTACK REVIEW REPORT — /plan-ceo-review

> Hat: CEO (tek ses — Codex kurulu değil → degradasyon: `subagent-only` da
> çağrılmadı; bu kişisel araçta tek-ses kabul edildi). Premise: kullanıcı
> "Dayanıklılık fazı (tam)" yönünü doğrudan seçti → ONAYLI. Mod: HOLD SCOPE.
> Yaklaşım: B (tam dayanıklılık omurgası). Önce mevcut plansız iş 3 commit'e
> ayrıştırıldı (mimari `0db64e4`'te izole), sonra bu ileriye-dönük plan üretildi.

## Runs / Status
| Aşama | Sonuç |
|---|---|
| Sistem denetimi | Kirli ağaç: onaylı Faz 4 + ertelenmiş UI + plansız bulk refactor tek blob'da |
| Ayrıştırma | 3 commit (mimari / kod+test / docs), ağaç temiz, 36 test yeşil |
| Mimari inceleme (bulk) | Sağlam; P1 (restart kalıcılığı) açık karar, P2/P3/P4 ucuz kazanç |
| İleriye dönük | Premise rafine (FlareSolverr kesildi); R1-R5 kapsam HOLD ile kilitlendi |

## Decision Audit Trail
| # | Karar | Sınıf | Gerekçe | Reddedilen |
|---|---|---|---|---|
| 1 | Plansız blob'u 3 commit'e ayrıştır, mimariyi izole et | İki-yön | İncelenebilirlik + bisect + rollback | Tek commit / geri alma |
| 2 | İşi olduğu gibi koru (sepya/swipe/find dahil) | İki-yön | Çalışan kod, completeness-ucuz | Ertelenmişleri geri alma |
| 3 | Sonraki faz = Dayanıklılık | İki-yön | En yüksek-frekanslı gerçek dert | Bulk-only / teknik borç |
| 4 | FlareSolverr/lncrawl KESİLDİ | İki-yön | Playwright profil zaten CF çözüyor; subtraction | İkinci bypass katmanı |
| 5 | Yaklaşım B (UX + bulk kalıcılık) | İki-yön | A bulk vaadini kırık bırakır; tam kapsam ucuz | A (UX-only) |
| 6 | Mod HOLD SCOPE | — | Dayanıklılığın doğası rigor, dream değil | EXPANSION |
| 7 | Bulk durumu SQLite + checkpoint + resume | İki-yön | "Restart'a dayan" vaadini gerçekten verir | Bellek-içi koru |

## VERDICT
APPROVED — uygulamaya hazır. Kritik blocker yok. Sıra: R1 → R5 → R2 → R3 → R4 → QA.
Uygulamada baştan ele alınacaklar: reader'da fetch-öncesi gizlemeyi kaldır (R1),
job thread'i kendi SQLite bağlantısını açsın (R2), single-flight resume'da da geçerli.

NO UNRESOLVED DECISIONS
