# B?l?m ba?laml? ?eviri uygulama plan?

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Bu oturumda g?revler s?rayla uygulan?r; ba??ms?z son inceleme yap?l?r.

**Goal:** Kaynak ba?l? ?zet/terim analiziyle yaln?z ?eviri ?retmek ve her onar?m?n etkisini izlemek.
**Architecture:** ceviri_baglam.py analiz/?zet do?rulamas?; ceviri_izleri.py s?n?rl? SQLite deney kay?tlar?; translate.py mevcut ak???n entegrasyonu; pipeline/cache N-1 kayna??. Yeni ba??ml?l?k yok.
**Tech Stack:** Python, FastAPI, SQLite, mevcut Gemini/Vertex SDK, pytest/Playwright.
**Spec:** ../specs/2026-10-10-roman-baglam-design.md

## Global Constraints

- 7cdc6a0 taban?, roman-baglam ayr? a?ac?; ana geli?tirme korunur.
- Kod/yorum/belge T?rk?e; yaln?z novel-cevirmen alt?nda yaz?m.
- Se?ili zincir korunur; CEVIRI_ANALIZ=0 eski yol; cached okuma ?cretsiz.
- Kaynak > ?zet; exact N-1; onays?z aday kal?c? kural de?ildir.
- URL ba??na 5 iz; ba?ar?s?z ?eviri eski chapter/ar?ive yaz?lmaz; gizli anahtar yok.

## Review Focus

1. ?nceki URL ba?ka kitab?/gelece?i g?steriyor: reddet, yaln?z exact N-1.
2. ?zeti olan N-1 kayna?? de?i?iyor: hash uyumsuzlu?unda yeniden ?zetle.
3. Analiz kaynakta olmayan terim/al?nt? ?retiyor veya STOP yok: kaydetme.
4. Onar?m iyi kar??l??? daha k?t? hale getiriyor: ?nce/sonras? ve boyut bazl? bulgu korunur.
5. Birden fazla ?eviri e?zamanl?: iz/ba?lam kullan?c?lar? kar??maz.

### 1. Kaynak ba?l? b?l?m analizi
Files: app/core/ceviri_baglam.py; tests/test_ceviri_baglam.py.
Interfaces: analiz(text, sozluk, kosullar, onceki_ozet, uret)->dict; ozetle(text,uret)->dict. uret(user,system,asama)->(response,model).
- [ ] ?nce reddetme/kapsam/al?nt?/s?n?r/aktif s?zl?k ?st?nl??? testleri, RED.
- [ ] En fazla 6 ?zet maddesi/1800 karakter/30 terim, tamamlanm?? STOP ve kaynak al?nt?s? do?rulamas?; GREEN.
- [ ] Ayr? analiz promptu, k?sa stil ve yaln?z translation JSON talimat?; dok?mantasyon.
- [ ] Tek ama?l? commit.

### 2. N-1 ba?lam? ve iz depolama
Files: app/core/cache.py; app/core/ceviri_izleri.py; tests/test_ceviri_baglam.py; scripts/ceviri_iz_incele.py.
Interfaces: cache.onceki_kaynak(book_slug,prev_url,chapter_no)->dict|None; ozet_oku/yaz(url,source,summary); iz_kaydet(id,url,payload); iz_oku(url).
- [ ] Yanl?? kitap/numara/bo?luk/kaynak de?i?imi/son5 iz testleri RED.
- [ ] Eklemeli iki yeni tablo, kaynak ba?lam? ve salt-okunur inceleme arac? GREEN.
- [ ] Commit.

### 3. ?eviri ?retim entegrasyonu
Files: app/core/translate.py; app/core/pipeline.py; tests/conftest.py; tests/test_ceviri_baglam_akis.py; .env.example.
Interfaces: translate_chapter mevcut arg?manlar? + book_slug/bolum_url/onceki_bolum keyword-only; i? implementation trace dict. Her iki pipeline metin yolu ayn? ba?lam? verir.
- [ ] Analiz ?nce ?al???r / yaln?z ?eviri JSON / aday kap?s? / eski yol / failed trace / pipeline testleri RED.
- [ ] N-1 ?zeti kaynaktan tembel olu?tur, analiz, translation-only talimat, kaynak metni eksiksiz ?evir, ara a?amalar? kaydet; GREEN.
- [ ] Commit.

### 4. Boyut bazl? denetim ve onar?m kan?t?
Files: app/core/ceviri_kalite.py; tests/test_ceviri_kalite.py; docs/CEVIRI-KALITE.md.
- [ ] Kaynak ba?l? anlam/ak?c?l?k bulgusu, d???k g?ven, ?nce/sonra ve failed trace testleri RED.
- [ ] v2 bulgu/onar?m kan?t?; ?slup tercihi otomatik onar?ma gitmez, mevcut v1 kabul edilir; GREEN.
- [ ] Commit.

### 5. Kar??la?t?rma ve do?rulama
Files: scripts/roman_baglam_kiyas.py; tests/test_roman_baglam_kiyas.py; reports/roman-baglam-uygulama/RAPOR.md.
- [ ] Ayn? kaynak/model/s?zl?k snapshot?, analiz a??k/kapal?, onar?m a??k/kapal?, canl? DB yaz?ms?z deney ve provenance testleri.
- [ ] 961/957 ve ikinci kitap ?rnekleri; ham ??kt?lar? incele; sonucu kaynak/ak?c?l?k/terminoloji/s?re/token olarak ayr? raporla.
- [ ] Tam pytest tests -q; NOVEL_TARAYICI_TEST=1 pytest tests/tarayici; diff/kaynak incelemesi.
- [ ] Yeni ba??ms?z son inceleme bulgular?n? gider, yerel commit; push/da??t?m kullan?c? onay? bekler.
