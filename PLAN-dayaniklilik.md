<!-- /autoplan restore point: /c/Users/OMEREK/.gstack/projects/novel-cevirmen/faz-sonraki-plan-autoplan-restore-20260627-191406.md -->
# Plan: Dayanıklılık Fazı (Faz 5)

> Bağlam: Faz 4 (okuma deneyimi) tamamlandı. Çalışma ağacına ayrıca sunucu-taraflı
> arka plan toplu çeviri (`jobs.py`/`pipeline.py`) eklendi. Bu plan, çekme/çeviri
> kırılınca uygulamanın **sessizce ölmesini** giderir: okuma ortasında graceful
> hata, ve gece-çalışan bulk işinin restart/uyku/clearance-bayatlamasına dayanması.
> Kişisel kullanım; LAN + paylaşılan SQLite. Mod: HOLD SCOPE.
>
> **autoplan revizyonu (subagent-only çift-ses):** R2 çift-kaynaktan (`_JOBS` dict +
> SQLite) **SQLite tek-doğruluk-kaynağına** indirildi; açılışta **auto-resume**;
> CF hatası **tipli**; **WAL** açıldı; istemci için **job keşif endpoint'i**; R1
> reader UX somutlaştırıldı; R5'in bayat DB_PATH çerçevesi düşürüldü.

## Amaç
Bir bölüm çekilemeyince okuduğun yeri kaybetmemek, ne olduğunu ve ne yapacağını
anlamak; uzun bir toplu çeviriyi başlatıp sunucu uyusa/restart olsa bile kaldığı
yerden (otomatik) sürdürebilmek.

## Hedef DEĞİL
- Yeni Cloudflare bypass mekanizması (FlareSolverr/lncrawl). Playwright kalıcı profil
  zaten CF'i çözüyor — ikinci bypass GEREKSİZ (premise düzeltmesi; çift-ses CONFIRMED).
- Çok-kaynak failover, indirme-geçmişi UI'ı, hesap/bulut senkron.
- Çeviri kalitesi / sözlük mantığı değişikliği.
- Çoklu eşzamanlı bulk iş (fetch global kilitle seri koşar → tek aktif iş zaten yeterli).

## Premise düzeltmesi (neden "Cloudflare retry ekle" DEĞİL)
`fetch.py` halihazırda olgun: Playwright kalıcı profil + `cf_clearance` yeniden
kullanımı, stealth JS, üstel geri-çekilmeyle retry (geçici hatalar), kalıcı (CF
challenge / origin 52x) vs geçici ayrımı, `FETCH_HEADLESS=0` elle-çöz talimatlı
mesajlar. TODOS'un "lncrawl/FlareSolverr" maddesi **bayat**. Gerçek boşluk çekme
katmanında değil; **(a) hatanın reader'da sunumu** ve **(b) bulk işinin kalıcılığı**.

**Mevcut kalıcı önbellek zaten yarı-dayanıklı:** `pipeline.get_or_translate` cache
isabetinde fetch/çeviri yapmaz; cache `next_url`'i saklar. Bir bulk ölürse, yeniden
başlatma ilk önbeklenmemiş bölüme kadar saf cache-okuması olarak ilerler (saniyeler).
Bu yüzden R2'nin gerçek değeri **mimari değil**: "nerede durdun" + "tek tıkla/otomatik
devam". Tasarım buna göre minimal tutuldu (job-framework DEĞİL, tek durum satırı).

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
- `loadChapter`: fetch BAŞARILI olana kadar mevcut bölümü **gizleme**. `readerBody`/
  `readerFooter` yalnızca `renderChapter` içinde (başarıda) değişir.
- **Yükleme göstergesi eyleme yakın:** `#status` global slotu yerine, basılan nav
  butonu "Yükleniyor…" + `disabled` olur; yükleme penceresinde nav/swipe kilitlenir
  (çift-tetik/yarış önlenir). (Design 2.1)
- **Ayrı `#readerError` elemanı** (`#status`'tan bağımsız; `<p>` içine `<div>` enjekte
  etme geçersizliği kalkar): footer'ın hemen ÜSTÜNE sticky kart. Hata, eylemin olduğu
  yere (dip/parmak hizası) yakın görünür — tepedeki global slot değil. (Design 1.1)
- Son render edilen bölüm görünür kalır; footer hata yolunda DOKUNULMAZ (eski
  `currentNext`/`currentPrev` korunur, yeniden hesaplanmaz). (Design 3.2/4.1)
- **Sınıfa-göre birincil eylem** (retry-çıkmazını kırar): CF challenge'da birincil eylem
  "Tekrar dene" DEĞİL, "Nasıl çözülür" rehberi; "Tekrar dene" ikincil. Geçici/network →
  "Tekrar dene" birincil. Tekrarlayan başarısızlık (N≥2) → mesaj eskalasyonu. (Design 3.1)
- **Cihaz-farkında CF mesajı:** telefonda ham `FETCH_HEADLESS=0` shell komutu işe
  yaramaz → geniş ekranda komut, dar ekranda "Bu bölüm masaüstünde doğrulama gerektiriyor"
  + kitabı sonra-oku işareti. (Design 5.4)
- **Boş/kısmi çeviri durumu:** `renderChapter` boş/çok-kısa `translation` → boş-durum
  kartı ("Bölüm boş geldi, yeniden çevir"). 200-ama-boş sessiz başarısızlığı kapatır. (Design 2.2)
- Erişilebilirlik: hata kartı `role="alert"`; loading `aria-live="polite"`; kart açılınca
  odak birincil eyleme; butonlar ≥44px; spinner `@media (prefers-reduced-motion: reduce)`
  ile statik göstergeye düşer. (Design 5.1/5.2/5.3)
- Etki alanı: `app/web/app.js`, `app/web/index.html`, `app/web/style.css`. Şema yok.

### R2 — Bulk job kalıcılığı (SQLite TEK kaynak) + auto-resume + single-flight
> autoplan: çift-ses (CEO + Eng) bağımsız olarak `_JOBS`+SQLite çift-kaynağını fazla
> buldu. SQLite tek-doğruluk-kaynağı; bellekte yalnız stop sinyali.
- Yeni `jobs` tablosu = **tek doğruluk kaynağı** (durum/ilerleme/mesaj/cursor hepsi
  tabloda). `_JOBS` dict KALDIRILIR. Bellekte yalnızca `_STOP: dict[str, threading.Event]`
  (stop runtime sinyali; kalıcı olması gerekmez, restart'ta thread zaten yok). (Eng B12)
- `get_status(job_id)` → tek `SELECT ... WHERE id=?`. Dict-birleştirme/drift/prune-fallback yok.
- **Checkpoint:** her bölüm bitince `cursor_url`, `done`, `translated`, `state`, `message`,
  `updated_at` UPDATE. `cursor_url` satır oluşturulurken `start_url` ile başlatılır
  (ilk checkpoint'ten önce crash'te NULL kalmaz). (Eng B3/B4)
- **Resume aynı satırı sürdürür:** `_run(job_id, start_done, start_translated)`, döngü
  `range(start_done, count)`; `done`/`translated` SQLite'tan geri yüklenir (sıfırdan
  job AÇMAZ; "0/7" yerine doğru ilerleme). (Eng B3)
- **Single-flight (atomik):** slug-by-running SELECT + INSERT tek `with _LOCK:` bloğunda;
  ek emniyet `CREATE UNIQUE INDEX ... ON jobs(slug) WHERE state='running'`. (Eng B6)
- **Auto-resume (açılışta):** server başlarken `running` satırlar bulunur; single-flight
  koruması altında `interrupted`'tan otomatik yeniden başlatılır (manuel "Devam et"
  yedek kalır). Reboot 2am'de tetiklense bile gece-run'ı sürer. (Eng B10; Risk #3 revize)
- **Job keşif endpoint'i:** `GET /api/book/{slug}/job` → o kitabın en son
  running/interrupted/paused işini döndürür. İstemci reload/başka cihaz job_id'yi
  closure'da kaybetse de resume tıklanabilir. (Eng B7)
- **Connection:** bağlantı `_run` gövdesinin İÇİNDE açılır (request thread'inden taşınmaz
  → `ProgrammingError` yok). Merkezi `db.connect()` (R5/WAL) kullanılır. (Eng B2)
- Etki alanı: `app/core/jobs.py`, `app/core/db.py`, `app/server.py`, `app/web/app.js`.

### R3 — cf_clearance bayatlama → tipli hata → job duraklatma
- **Tipli CF hatası (önkoşul):** `fetch.py`'ye `class CloudflareChallenge(FetchError)`;
  `_fetch_locked` challenge dalında onu fırlatır. jobs `except CloudflareChallenge →
  paused`, `except FetchError → error`. Türkçe-mesaj substring eşleştirmesi YOK (kırılgan). (Eng B9)
- `paused` + aksiyon mesajı (cihaz-farkında, R1 ile aynı metin kaynağı). `cursor_url`
  korunur → çözümden sonra resume.
- **[TASTE — kapıda] Restart'sız clearance tazeleme:** sunucuyu `FETCH_HEADLESS=0` ile
  restart etmek yerine, `fetch_chapter(headless=False)`'ı tek bölüm için tetikleyen
  `POST /api/clearance/refresh` endpoint'i (masaüstünde görünür pencere açar, cookie
  profile yazılır). Restart gerektirmez. CEO + Design 5.4 önerdi. (Öneri: EKLE.)
- Etki alanı: `app/core/fetch.py`, `app/core/jobs.py`, `app/server.py`, `app/web/app.js`.

### R4 — Gözlemlenebilirlik (job lifecycle log)
- Yapısal log (Python `logging`): job start/checkpoint(periyodik)/done/error/stopped/
  paused/auto-resume — `job_id`, `slug`, `done/total`, `state`, son hata. Gece çöken/
  resume olan run iz bırakır.
- Etki alanı: `app/core/jobs.py`.

### R5 — Test + WAL + kütüphane durum rozeti
> autoplan: R5'in "DB_PATH enjekte edilebilir yap" çerçevesi BAYAT — `db.db_path()` +
> `NOVEL_DB_PATH` zaten var. O madde düşürüldü.
- **WAL (yeni, B1):** `db.py`'ye merkezi `connect()` — `PRAGMA journal_mode=WAL` +
  `PRAGMA busy_timeout=10000`. `cache`/`library`/`jobs` tüm bağlantıları buna bağlanır.
  DB yerel diskte (LAN yalnız HTTP) → WAL güvenli. 4 yazar + telefon polling kilidini çözer.
- **Kütüphane durum rozeti (R2 UI, Design 2.3/4.2):** kitap kartında job rozeti
  (running done/total · interrupted · paused) + "Devam et" + tamamlanma bildirimi.
  Backend kadar somut UI yüzeyi.
- Testler (pytest, hepsi `NOVEL_DB_PATH` geçici DB):
  - `pipeline.get_or_translate`: cache-isabeti / refresh / hata yayılımı.
  - `jobs._run`: stop (Event) / `next_url` sonu / hata→state / checkpoint yazımı.
  - **Resume yeniden-tabanlama** (`range(start_done,count)`, done/translated geri yükleme). (B3)
  - **Idempotent resume:** checkpoint-arası crash → resume → bölüm yeniden işlenir ama
    `done` çift artmaz, API çağrılmaz (cache hit). (B8)
  - **Single-flight reddi** + partial unique index. (B6)
  - **CloudflareChallenge → paused vs FetchError → error** ayrımı. (B9)
  - **Kilit çekişmesi:** checkpoint UPDATE döngüsü + eşzamanlı `set_position`/okuma →
    `database is locked` regresyonu (WAL doğrulaması). (B1/B11)
  - Keşif endpoint'i `GET /api/book/{slug}/job` + interrupted/paused 404-değil. (B7)
- Etki alanı: `tests/test_jobs.py`, `tests/test_pipeline.py`, `tests/test_db_wal.py`,
  `app/core/db.py`, `app/web/app.js`+`index.html` (rozet).

---

## Veri modeli — `jobs` tablosu
```
jobs(
  id           TEXT PRIMARY KEY,   -- uuid4 hex
  slug         TEXT NOT NULL,
  start_url    TEXT NOT NULL,
  cursor_url   TEXT NOT NULL,      -- oluşturmada = start_url; checkpoint günceller
  count        INTEGER NOT NULL,
  done         INTEGER NOT NULL DEFAULT 0,
  translated   INTEGER NOT NULL DEFAULT 0,
  state        TEXT NOT NULL,      -- running|done|stopped|error|paused|interrupted
  message      TEXT,
  created_at   REAL NOT NULL,
  updated_at   REAL NOT NULL
)
-- single-flight: aynı kitapta iki çalışan iş olamaz
CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_running ON jobs(slug) WHERE state='running';
```
Migration: `CREATE TABLE IF NOT EXISTS` + `CREATE UNIQUE INDEX IF NOT EXISTS`; sütun
eklemeleri `db.ensure_column` (idempotent). `chapters`/`books` şemasına dokunulmaz.
Açılış taraması, tabloyu lazy-create eden `connect()`'ten SONRA çalışır (tablo-yok
`OperationalError`'ı önler). (Eng B13)

## Veri akışı — bulk job durum makinesi (SQLite tek kaynak)
```
            start_bulk(slug,start_url,count)   [tek _LOCK: SELECT running? + INSERT]
                       │  (single-flight: running varsa onu döndür)
                       ▼
   ┌──────────────► running ──────────────────────────────┐
   │   _run: her bölüm pipeline.get_or_translate           │
   │         + SQLite checkpoint(cursor,done,translated)   │
   │   stop = threading.Event (bellekte, kalıcı değil)     │
   │                  ├─ next_url yok ───────────► done     │
   │                  ├─ Event.set() ────────────► stopped  │
   │ auto-resume      ├─ CloudflareChallenge ────► paused ──┤ (clearance çöz → resume)
   │ (açılış,         └─ FetchError/Translate ───► error    │
   │  single-flight)                                        │
   └──── sunucu açılışı: running → interrupted → auto-resume ┘
           (range(start_done,count); manuel "Devam et" yedek)
```

## Veri akışı — reader hata yolu (R1)
```
loadChapter(url)   [nav butonu "Yükleniyor…" + disabled; swipe kilitli]
  │ önceki bölüm + footer GÖRÜNÜR kalır (gizleme yok)
  ▼ fetch /api/chapter
  ├─ 200 ──► renderChapter (readerBody + footer'ı DEĞİŞTİR)
  │           └─ boş/çok-kısa translation → boş-durum kartı
  └─ hata ─► #readerError sticky kart (footer'ın ÜSTÜ, dokunulmaz footer korunur)
              ├─ 502 CloudflareChallenge → birincil "Nasıl çözülür" (cihaz-farkında)
              │                            ikincil "Tekrar dene"
              ├─ 502 origin 52x ─────► "kaynak sitenin sorunu, bekle"
              ├─ 502 geçici/network ─► birincil "Tekrar dene" (N≥2 → eskalasyon)
              └─ 503 çeviri / 500 ──► detay + Tekrar dene
            role="alert", odak birincil eyleme, butonlar ≥44px, reduced-motion
```

## Failure modes / edge cases
| # | Durum | Şu an | R-sonrası |
|---|---|---|---|
| 1 | Okuma ortasında çekim patlar | readerBody gizli → metin kaybolur | son bölüm korunur, footer-üstü sticky hata kartı |
| 2 | Sunucu/PC bulk ortasında reboot (2am) | iş kaybolur, 404 | açılışta `interrupted`→auto-resume (single-flight) |
| 3 | cf_clearance bulk ortasında dolar | tüm run `error`, sessiz | tipli `CloudflareChallenge`→`paused`+rehber+resume |
| 4 | Aynı kitaba 2x bulk / eşzamanlı | 2 thread çekişir, çift sayım | single-flight (_LOCK + partial unique index) |
| 5 | İstemci reload / başka cihaz | job_id closure'da kaybolur | `GET /api/book/{slug}/job` keşif endpoint'i |
| 6 | İstemci kapalıyken iş biter | bellekte, prune'da gider | SQLite tek kaynak, kalıcı; rozet/bildirim |
| 7 | checkpoint-arası crash | — | idempotent: resume cache-hit, `done` çift artmaz |
| 8 | Bulk checkpoint + telefon set_position eşzamanlı | `database is locked` riski | WAL + busy_timeout |
| 9 | CF challenge telefonda | ham shell komutu eylemsiz | cihaz-farkında mesaj + sonra-oku |
| 10| 200-ama-boş çeviri | sessiz boş gövde | boş-durum kartı |

## Migration güvenliği / rollback
- Yalnızca yeni `jobs` tablosu + partial unique index + merkezi `connect()` (WAL pragma).
  Mevcut `chapters.db` bozulmaz; `chapters`/`books` şeması sabit.
- `state` TEXT (şema-esnek); yeni durum migration gerektirmez.
- Rollback: `jobs` tablosu bağımsız; düşürmek diğer özellikleri etkilemez. WAL geri
  alınırsa `journal_mode=DELETE`'e dönülür (veri kaybı yok).

## Riskler
1. **Thread + SQLite (R2):** bağlantı `_run` İÇİNDE açılır; request thread'inden taşınmaz.
   Merkezi `connect()` + WAL + busy_timeout. Testte kilit-çekişmesi doğrulanır. (B1/B2)
2. **Checkpoint sıklığı:** bölüm başına bir UPDATE; çeviri (saniyeler) yanında ihmal
   edilebilir. WAL ile yazar okuyucuyu bloklamaz.
3. **Auto-resume çiftleme:** açılış auto-resume + manuel "Devam et" aynı işi başlatabilir.
   Azaltma: ikisi de single-flight'tan (partial unique index) geçer → atomik koruma. (B6/B10)
4. **Boş cursor:** `cursor_url` oluşturmada `start_url` ile başlatılır → ilk checkpoint
   öncesi crash'te de geçerli devam noktası. (B4)

## Kapsam DIŞI (TODOS.md'ye)
- FlareSolverr/lncrawl ikinci bypass (premise; çift-ses CONFIRMED).
- Otomatik cf_clearance yenileme zamanlayıcısı, çok-kaynak failover, indirme-geçmişi UI.
- Çoklu eşzamanlı bulk iş (fetch seri koşar → gereksiz).

## İlk somut adım / sıra
R1 (reader graceful-failure) — tamamen frontend, en hızlı hissedilen kazanç, şema yok.
Sonra R5-WAL (`connect()` — R2'nin önkoşulu), R3-tip (`CloudflareChallenge` — R3'ün
önkoşulu), R2 (jobs tablosu + checkpoint + single-flight + auto-resume + keşif endpoint),
R3 (paused + [taste] clearance endpoint), R4 (log), kütüphane rozeti, en son uçtan uca QA.

---

# GSTACK REVIEW REPORT — /autoplan

> Hat: CEO → Design → Eng (DX atlandı: kişisel araç, harici geliştirici/API tüketicisi
> yok). Codex kurulu değil → çift-ses bağımsız Claude subagent'lerine düştü
> (degradasyon: source = `subagent-only`). Premise (Dayanıklılık fazı + yaklaşım B +
> HOLD + FlareSolverr kesimi) kullanıcı tarafından önceki turda onaylandı → kapı geçildi.
> Mod: HOLD SCOPE — bulgular kapsamı genişletmedi, mevcut feature'ı kurşun-geçirmez yaptı
> (tek-kaynak sadeleştirmesi kapsamı AZALTTI).

## Runs / Status
| Faz | Ses | Sonuç |
|---|---|---|
| CEO | subagent (Codex N/A) | Premise CONFIRMED; R2 fazla-mühendislik flagged; DB_PATH bayat |
| Design | subagent (Codex N/A) | 2 kritik (kart konumu, retry-çıkmazı) + 8 yüksek (a11y/UI özgüllük) |
| Eng | subagent (Codex N/A) | 7 yüksek (WAL, çift-kaynak, resume, prune, keşif, CF-tip, auto-resume) |

## Konsensüs (subagent-only → tek-ses; Codex N/A = CONFIRMED değil; tek kritik bulgu yine de flagged)
| Boyut | Claude | Codex | Sonuç |
|---|---|---|---|
| CEO: premise geçerli (FlareSolverr kesimi) | Evet | N/A | tek-ses CONFIRMED |
| CEO: kapsam kalibrasyonu | R2 fazla-mühendislik | N/A | flagged → auto-fix (tek-kaynak) |
| Design: bilgi hiyerarşisi (hata konumu) | Kritik | N/A | flagged → auto-fix |
| Design: eksik durumlar (retry-çıkmazı/paused/boş) | Kritik/Yüksek | N/A | flagged → auto-fix |
| Design: a11y (dokunma/reduced-motion/aria) | Yüksek | N/A | flagged → auto-fix |
| Eng: mimari (çift-kaynak vs tek-kaynak) | Yüksek | N/A | flagged → auto-fix |
| Eng: WAL / kilit çekişmesi | Yüksek | N/A | flagged → auto-fix |
| Eng: CF hatası tipsiz | Yüksek | N/A | flagged → auto-fix |
| Eng: auto-resume vs manuel | Yüksek | N/A | flagged → auto-fix (Risk #3 revize) |

## Cross-Phase Themes (2+ faz bağımsız işaret etti — yüksek güven)
- **Çift-kaynağı bırak → SQLite tek-doğruluk-kaynağı** — CEO (slug-keyed tek satır) + Eng (B12).
- **CF hatası tipli + reader'da sınıfa-göre eylem** — Eng (B9) + Design (3.1/5.4).
- **R2 backend olgun ama UI yüzeyi (resume/paused görünürlüğü) zayıf** — Design (2.3/4.2) + Eng (B7).

## Decision Audit Trail
| # | Faz | Karar | Sınıf | İlke | Gerekçe | Reddedilen |
|---|---|---|---|---|---|---|
| 1 | Eng | R2: SQLite tek-kaynak; `_JOBS` dict → `threading.Event` stop | Taste→kapı | P5,P3 | CEO+Eng örtüştü; drift/prune-fallback eler | Çift-kaynak dict+SQLite |
| 2 | Eng | Açılışta auto-resume (single-flight korumalı) | Taste→kapı | P1,P6 | Reboot-2am gece-run'ı sürsün; çift-başlatma zaten engelli | Yalnız-manuel resume |
| 3 | Eng | `CloudflareChallenge(FetchError)` tipli hata | Mechanical | P1 | substring eşleştirme kırılgan; R3'ün önkoşulu | Mesaj-string match |
| 4 | Eng | Merkezi `db.connect()` + WAL + busy_timeout | Mechanical | P1 | 4 yazar+polling `database is locked`; plan "WAL" iddiası gerçek değildi | DELETE journal |
| 5 | Eng | `GET /api/book/{slug}/job` keşif endpoint'i | Mechanical | P1 | job_id closure'da kaybolur; onsuz resume tıklanamaz | Yalnız closure jobId |
| 6 | Eng | resume `range(start_done,count)` + cursor=start_url init | Mechanical | P1 | "0/7" tutarsızlık; ilk-checkpoint-öncesi NULL | Sıfırdan job |
| 7 | Eng | single-flight: _LOCK SELECT+INSERT + partial unique index | Mechanical | P1 | atomik olmayan SELECT+INSERT | Yalnız dict lock |
| 8 | Design | Ayrı `#readerError` sticky kart (footer üstü), footer dokunulmaz | Mechanical | P5,P1 | `#status` loading+error+geçersiz `<p><div>`; dip kullanıcı tepeyi görmez | Global #status slotu |
| 9 | Design | Sınıfa-göre birincil eylem (CF→rehber, geçici→retry) | Mechanical | P1 | CF'de retry beyhude; çıkmaz döngü | Tek "Tekrar dene" |
| 10| Design | Cihaz-farkında CF mesajı (telefon vs masaüstü) | Mechanical | P1 | telefon shell komutu çalıştıramaz | Tek ham komut |
| 11| Design | a11y: ≥44px, reduced-motion, role=alert, odak; boş-durum kartı | Mechanical | P1 | erişilebilirlik + sessiz boş yanıt | Atla |
| 12| Design+Eng | Kütüphane kartı job durum rozeti + Devam et + bildirim | Mechanical | P1 | resume/paused görünürlüğü; backend kadar somut UI | Tek-cümle "Devam et" |
| 13| CEO | R5'in "DB_PATH borcu" çerçevesi düşürüldü | Mechanical | P4 | `db.db_path()`+`NOVEL_DB_PATH` zaten var | Bayat borç |
| 14| CEO+Design | [TASTE] R3 restart'sız clearance-refresh endpoint | Taste→kapı | P2 | restart ağır; blast-radius içi küçük | Yalnız server restart |

## Taste Decisions (kapıda — kullanıcı onayı)
- **T1 — R2 tek-kaynak (SQLite) vs çift-kaynak (dict+SQLite).** Auto-karar: tek-kaynak.
  Yarı kod, drift yok. (Senin orijinal planın çift-kaynaktı.)
- **T2 — Açılışta auto-resume vs yalnız-manuel.** Auto-karar: auto-resume. Reboot-2am
  gece-run'ı sürsün; single-flight çift-başlatmayı engelliyor. (Planın Risk #3'ünü ters çevirir.)
- **T3 — R3 restart'sız clearance-refresh endpoint EKLE vs sadece restart.** Auto-karar:
  EKLE. Küçük, blast-radius içi, telefon-çıkmazını da kısmen hafifletir. (Yeni yüzey.)

## VERDICT
APPROVED — kullanıcı final kapıda onayladı (3 taste kabul). Kritik blocker yok. Sıra:
R1 → R5-WAL → R3-tip → R2 → R3 → R4 → rozet → QA.
Taste kararları RESOLVED: T1 SQLite tek-kaynak (onaylandı), T2 açılışta auto-resume
(onaylandı), T3 restart'sız clearance-refresh endpoint EKLE (onaylandı).

NO UNRESOLVED DECISIONS
