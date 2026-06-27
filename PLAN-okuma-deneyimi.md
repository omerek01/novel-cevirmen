# Plan: Okuma Deneyimi Fazı (Faz 4)

> Bağlam: TASARIM.md Faz 0-3 tamamlandı. Bu plan, mevcut çalışan PWA üzerine
> **okuma deneyimi** cilasını ekler. Kişisel kullanım; "mükemmel UI" hedef değil,
> ama günlük okumada hissedilen sürtünmeleri giderir.

## Amaç
Telefonda uzun romanları okurken kaldığın yeri kaybetmeden, ileri-geri kolayca
gezinerek ve gözü yormayan ayarlarla okumak.

## Hedef DEĞİL
- Yeni kaynak site, yeni çeviri modeli, sözlük/çeviri mantığı değişikliği.
- Backend mimarisinde büyük değişiklik. Mümkün olduğunca frontend + küçük API eklemesi.
- Hesap/çoklu-kullanıcı, bulut senkron (LAN + paylaşılan SQLite yeterli).

## Çözülen dertler
1. **Kaldığın yeri kaybetme:** bölüm ortasında kapatınca aynı yere dönememe.
2. **Geri gidememe:** sadece "sonraki bölüm" var; yanlış bölüme girince geri yok.
3. **Uzun kitapta bölüm bulma:** bölüm listesi uzayınca aranan bölüme inememe.
4. **Okuma konforu:** satır aralığı/kenar boşluğu/tema seçeneği dar.

---

## Kapsam (özellikler)

### E1 — Bölüm-içi okuma ilerlemesi  [T1: HİBRİT]
- Konumu **oran** olarak sakla (`scrollY / (scrollHeight - innerHeight)`), ham px DEĞİL
  (font/satır-aralığı/yön değişince px kayar — E1↔E4 çakışması).
- **Sunucu-taraflı (cihaz-bağımsız):** mevcut bölümün oranını `books` tablosuna
  `current_ratio REAL` olarak yaz; "KALDIĞIN YERDEN DEVAM ET" hem `current_url` hem
  oranı geri yükler. Telefon+masaüstü aynı yerden devam eder. Migration: `_ensure_column`.
- **localStorage offline yedek:** çevrimdışıyken/yazma başarısızsa oranı yerelde tut,
  bağlanınca sunucuya yaz. Tek JSON obje + ~500 LRU budama.
- **Race koruması:** restore `requestAnimationFrame` ile render SONRASI; kaydet throttle
  (~250ms) + `pagehide`/`visibilitychange`'de bir kez; programatik `scrollTo(0,0)`
  sırasında `isRestoring` bayrağıyla kaydı baskıla.
- İlerleme çubuğu: reader-bar alt kenarına sabit, `scaleX()`, `transition` YOK
  (anlık; reduced-motion sorunu doğmaz). Düşük öncelik.
- Etki alanı: `app/web/app.js`, `app/web/style.css`, `app/core/library.py`
  (current_ratio), `app/server.py` (upsert + payload).

### E2 — Önceki bölüm düğmesi  [T3: HİBRİT]
- Okuyucu alt çubuğuna "← ÖNCEKİ BÖLÜM" (ghost/ikincil; next birincil). prev yoksa
  next tam-genişlik. Footer iki-yuva olarak yeniden düzenlenir.
- **prev kaynağı (hibrit):** önce yüklü bölüm listesinden istemci-tarafı türet
  (eski/NULL satırlarda da çalışır), bilinmiyorsa sayfadan çekilen `prev_url`'e düş.
- prev_url çıkarımı: `_next_chapter_url` → `_nav_chapter_url(soup, url, selectors)`
  olarak genelle (DRY); `SITES`/`GENERIC_SITE`'a `prev` selektörleri ekle.
  `#`/`javascript:`/boş elenir (mevcut koruma miras alınır).
- Kalıcılık: `cache` tablosuna `prev_url` sütunu — `_ensure_column` (PRAGMA table_info
  + ALTER, try/except). `get_chapter` SELECT'e sona ekle (`row[8]`), `save_chapter`
  sütun+VALUES, `server` payload zinciri (`chapter["prev_url"]`).
- Not: bazı sitelerde ilk bölümün "prev"i romanın index sayfasıdır; o URL'i çekmek
  `FetchError` verebilir → kişisel kullanımda kabul; "prev her zaman geçerli bölüm
  değildir" beklentisi yazıldı.
- Etki alanı: `app/core/fetch.py`, `app/core/cache.py`, `app/server.py`,
  `app/web/app.js`, `app/web/index.html`, `app/web/style.css`.

### E3 — Bölüme atlama / arama
- Kitap görünümünde bölüm listesinin üstüne arama kutusu; istemci-tarafı filtre
  (başlık + bölüm no). Yeni API yok; `chapterList` zaten yüklü.
- Etki alanı: `app/web/index.html`, `app/web/app.js`, `app/web/style.css`.

### E4 — Okuma ayarları genişletme  [T2: SADELEŞTİRİLDİ]
- Ayar paneline yalnızca **satır aralığı** (sık/normal/seyrek) — 3 durumlu stepper
  (punto deseniyle aynı). Sepya ve kenar boşluğu TODOS'a ertelendi; ikili tema
  toggle'ı dokunulmaz kalır (refactor yok).
- Ön koşul: `reader-body`'deki sabit `line-height` → `--reading-line-height` CSS
  değişkeni; `applySettings()` set eder. Mevcut `settings` objesi geriye-uyumlu
  defaultla genişler.
- Etki alanı: `app/web/app.js`, `app/web/style.css`, `app/web/index.html`.

---

## Mevcut ne var (yeniden kullan)
- `loadChapter`/`renderChapter` (app.js): okuyucu akışı — E1/E2 buraya bağlanır.
- `settings` + `applySettings`/`saveSettings` (app.js): E4 mevcut desene eklenir.
- `_next_chapter_url` (fetch.py): E2 prev için birebir simetrik yardımcı yazılır.
- `cache.save_chapter`/`get_chapter`: E2 prev_url buraya eklenir.
- `renderChapterList` (app.js): E3 filtresi mevcut listeyi süzer.

## Kapsam DIŞI (TODOS.md'ye)
- Kaydırmayla bölüm geçişi (swipe nav) — ayrı, gerekirse sonra.
- Sunucu-tarafı okuma konumu senkronu (cihazlar arası tam senkron) — gerekmiyor.
- Bölüm-içi tam-metin arama — kapsam dışı.

## Test planı
- Backend (yeni saf mantık): `fetch` prev-link çıkarımı için pytest
  (`_prev_chapter_url`/`_parse` prev alanı), `cache` prev_url yaz/oku + migration
  idempotensi. Test altyapısı yok → `pytest` + küçük `tests/` kurulur.
- Frontend (E1/E3/E4 saf-frontend): manuel QA — telefon + masaüstü, açık/koyu/sepya,
  kaldığın yere dönüş, filtre, prev/next sınır durumları (ilk/son bölüm).

## Riskler
1. **cache şema değişimi (E2):** mevcut `chapters.db`'yi bozma. Azaltma: yalnızca
   `ADD COLUMN`, idempotent guard, eski satırlar `NULL` (geriye uyumlu).
2. **prev link site-özel kırılganlık:** bazı sayfalarda prev linki olmayabilir →
   düğme pasif. Azaltma: `next` ile aynı en-iyi-çaba deseni, yoksa gizle.
3. **localStorage anahtar şişmesi (E1):** her bölüm için scroll anahtarı birikir.
   Azaltma: tek JSON objesi + son ~500 bölümle sınırla (LRU benzeri budama).

## İlk somut adım
E1 (scroll persist + ilerleme çubuğu) — tamamen frontend, en hızlı hissedilen kazanç.
Sonra E3 (filtre), E4 (ayarlar), en son E2 (prev — şema dokunuşu içerdiği için).

---

# GSTACK REVIEW REPORT — /autoplan

> Hat: CEO → Design → Eng. DX fazı atlandı (kişisel araç; harici geliştirici/API
> tüketicisi yok). Codex kurulu değil → çift-ses bağımsız Claude alt-ajanlarına
> düştü (degradasyon: source = `subagent-only`). Premise kapısı: kullanıcı yönü
> ("Okuma deneyimi") doğrudan seçtiği için premise (bu faz yapılmaya değer)
> ONAYLI sayıldı.

## CEO Dual Voices — Consensus
| Boyut | Claude | Codex | Konsensüs |
|---|---|---|---|
| 1. Premise geçerli? | Evet (kullanıcı seçti) | N/A | CONFIRMED |
| 2. Doğru problem mu? | Evet, günlük temas noktası | N/A | (tek ses) Evet |
| 3. Kapsam kalibrasyonu | E4 hafif gold-plating | N/A | DISAGREE → taste |
| 4. Alternatifler | E1 sunucu-taraf yeterince tartılmamış | N/A | DISAGREE → taste |
| 5. 6-ay pişmanlık | E1 cihaz-yerel | N/A | DISAGREE → taste |
| 6. Trajektori | Sağlam | N/A | (tek ses) Sağlam |

## Design Litmus — Consensus
| Boyut | Claude | Codex | Konsensüs |
|---|---|---|---|
| Bilgi hiyerarşisi | Sağlam | N/A | CONFIRMED |
| Eksik durumlar (boş/sınır) | E3 boş-sonuç, prev sınırları eksik | N/A | flagged → auto-fix |
| Veri modeli (scroll birimi) | KRİTİK: px değil oran | N/A | flagged → auto-fix |
| Tema modeli (sepya) | KRİTİK: ikili toggle'a sığmaz | N/A | flagged → taste |
| Erişilebilirlik/kontrast | aria-pressed, sepya kontrast | N/A | flagged → auto-fix |
| Panel karmaşıklığı | 4→7 satır şişme | N/A | flagged → auto-fix |

## Eng Dual Voices — Consensus
| Boyut | Claude | Codex | Konsensüs |
|---|---|---|---|
| 1. Mimari sağlam? | Evet | N/A | (tek ses) Evet |
| 2. Migration deseni | CREATE TABLE sütun eklemez → PRAGMA+ALTER | N/A | flagged → auto-fix |
| 3. E2 prev kaynağı | Şema vs istemci-türetme | N/A | DISAGREE → taste |
| 4. Test kapsamı | fetch nav + cache migration | N/A | flagged → auto-fix |
| 5. Güvenlik | Yeni anlamlı yüzey yok | N/A | CONFIRMED |
| 6. Gizli karmaşıklık | sepya, scroll throttle/restore | N/A | flagged → auto-fix |

## Cross-Phase Themes (2+ faz bağımsız işaret etti — yüksek güven)
- **Scroll'u px yerine ORAN sakla** — Design (kritik) + Eng (yüksek). E1↔E4 çakışması.
- **Sepya ikili tema toggle'ına oturmuyor** — Design (kritik) + Eng (yüksek).
- **Scroll race / `scrollTo(0,0)` restore'u eziyor / throttle** — Design + Eng.
- **Eski cache satırları prev_url=NULL** — Design + Eng (E2 prev kaynağı kararını besliyor).

## Decision Audit Trail
| # | Faz | Karar | Sınıf | İlke | Gerekçe | Reddedilen |
|---|---|---|---|---|---|---|
| 1 | CEO | Premise: faz yapılmaya değer | — | P6 | Kullanıcı yönü seçti | — |
| 2 | CEO | E4 kenar boşluğu (margin) → TODOS'a ertele | Mechanical | P3,P5 | Design+CEO ortak: panel şişmesi, YAGNI | Üç-eksenli ayar |
| 3 | CEO | Dayanıklılık genişlemesi (fetch/çeviri hata cilası) → TODOS | Mechanical | P3 | Tema dışı; reader zaten `setStatus` ile hata gösteriyor | Faza ekleme |
| 4 | CEO | İlerleme çubuğu kalsın, düşük öncelik, `transition` yok | Mechanical | P6 | Ucuz, reduced-motion sorunu doğurmaz | Çıkarma |
| 5 | Eng | E1 scroll'u ORAN (`scrollY/(scrollHeight-innerHeight)`) sakla | Mechanical | P1 | Cross-phase kritik; px font/yön değişince kırılır | Ham px |
| 6 | Eng | Restore `requestAnimationFrame` sonrası + kaydet throttle + `pagehide` | Mechanical | P1 | `scrollTo(0,0)` restore'u eziyor; jank | Naif scroll dinleyici |
| 7 | Eng | Migration: `_ensure_column` (PRAGMA table_info + ALTER, try/except) | Mechanical | P5 | `CREATE TABLE IF NOT EXISTS` sütun eklemez | Sadece CREATE gövdesi |
| 8 | Eng | `_next_chapter_url` → `_nav_chapter_url(soup,url,selectors)` genelle | Mechanical | P4 | next+prev tek saf fonksiyon; DRY | Kopya prev fonksiyonu |
| 9 | Eng | `get_chapter`/`save_chapter`/server payload zincirine prev_url ekle | Mechanical | P5 | Pozisyonel `row[8]`, KeyError zinciri | — |
| 10 | Eng | pytest + `tests/`: fetch nav çıkarımı + cache migration idempotensi | Mechanical | P1 | Sıfır test → saf mantık sigortası | Testsiz |
| 11 | Eng | `filterChapters`/`pruneScrollPositions` saf fonksiyonlara çıkar | Mechanical | P4 | Test edilebilir + DRY | Inline mantık |
| 12 | Design | CSS değişkenleri `--reading-line-height`/`--reading-margin` ekle | Mechanical | P5 | E4 ön koşulu; reader-body sabitleri | Sabit değerler |
| 13 | Design | Footer iki-yuva: prev ghost/ikincil, next birincil; prev yoksa next tam-genişlik | Mechanical | P5 | Tek-düğme footer iki düğmeye tanımsız | — |
| 14 | Design | E3 boş-sonuç satırı + input `font-size:1rem` (iOS zoom) | Mechanical | P1 | Eksik durum + mobil hata | — |
| 15 | Design | aria-pressed; sepya paleti kontrast doğrulanmış (≥4.5:1) | Mechanical | P1 | Erişilebilirlik | Göz-kararı palet |

## Taste Decisions (kullanıcıya bırakıldı — kapıda)
- **T1 — E1 okuma konumu nerede saklanır?** Plan: cihaz-yerel localStorage.
  CEO itirazı: paylaşılan SQLite zaten var; çok-cihaz tek kullanıcıda gerçek;
  sunucu-upsert, localStorage LRU budamadan basit olabilir. (Design/Eng yerel'i
  sorun görmedi.) Öneri: **hibrit** — sunucuda bölüm-içi oran sakla (cihaz-bağımsız),
  localStorage offline yedek.
- **T2 — Sepya tema?** Gerçek okuma konforu ama ikili `toggleTheme`'i `setTheme(name)`
  + segmented control'e refactor gerektirir (Design+Eng "kolay değil" dedi).
  Öneri: **dahil et** (refactor ile) — okuma konforu bu fazın özü.
- **T3 — E2 prev kaynağı?** A) sayfadan prev_url + şema sütunu (mevcut plan; eski
  satırlar NULL), B) istemci-tarafı türet (yüklü bölüm listesinden; şema yok ama
  soğuk-açılışta prev bilinmez), C) hibrit (türet-önce, prev_url yedek).
  Öneri: **C (hibrit)** — soğuk-açılışı da çözer, eski satır NULL sorununu da.

## Test Diagram (Eng — Section 3)
| Kod yolu | Tür | Var mı? | Boşluk |
|---|---|---|---|
| fetch nav çıkarımı (next+prev, `#`/`javascript:`/`data-` yedeği) | unit (saf HTML) | yok | pytest yaz |
| cache migration idempotensi (PRAGMA+ALTER, 2x çağrı) | unit | yok | pytest yaz |
| cache prev_url yaz/oku roundtrip + eski satır NULL | unit | yok | pytest yaz |
| `filterChapters(list,q)` / `pruneScrollPositions(map,max)` | unit (Node) | yok | saf fn + minik test |
| E1/E3/E4 görsel + sınır (ilk/son/prev-yok, açık/koyu/sepya) | manuel QA | — | telefon+masaüstü |

## NOT in scope → TODOS
- Swipe ile bölüm geçişi.
- Bölüm-içi tam-metin arama.
- E4 kenar boşluğu (margin) ayarı (panel sadeliği için ertelendi — karar #2).
- Sepya tema (T2 ertelendi; eklenince setTheme(name) + segmented control refactor'u gerekir).
- Dayanıklılık genişlemesi: fetch/çeviri kırılınca zengin hata + cache fallback (karar #3).

## Final Kararlar (kullanıcı onayı — kapı geçildi)
- **T1 → HİBRİT:** sunucu-taraflı `books.current_ratio` (cihaz-bağımsız) + localStorage
  offline yedek. E1 artık küçük backend dokunuşu içerir (library + server).
- **T2 → ERTELE:** sepya + kenar boşluğu TODOS'a; E4 yalnızca satır aralığı. İkili
  tema toggle'ı dokunulmaz (setTheme refactor'u GEREKMEZ).
- **T3 → HİBRİT:** istemci-türetme önce, sayfadan `prev_url` yedek. Şema sütunu yine
  eklenir (yedek için) ama eski/NULL satırlar artık türetmeyle çalışır.

İki şema dokunuşu (`chapters.prev_url`, `books.current_ratio`) aynı `_ensure_column`
deseniyle; her ikisi de migration testine dahil.

## Status
APPROVED — uygulamaya hazır. Kritik blocker yok. Sıra: E1 → E3 → E4 → E2.
Uygulamada baştan ele alınacaklar: scroll'u ORAN sakla + race koruması (E1),
`_ensure_column` migration + payload zinciri (E1 current_ratio & E2 prev_url),
footer iki-yuva + boş/sınır durumları, pytest (fetch nav + iki migration).
