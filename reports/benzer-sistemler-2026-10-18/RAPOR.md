# Benzer sistemler: Firecrawl araştırması ve REA analizi

Tarih: 2026-10-18. Yalnız araştırma ve rapor; kod, veri ya da ayar değişikliği yapılmadı.
Roman metni bu rapora alınmadı. Önceki iki araştırmada (`roman-ceviri-yontemleri-2026-10-10`,
16 Ekim kör nokta planı) incelenen TranslateBooksWithLLMs, ai-novel-translation, BabelDOC,
translation-agent, DelTA ve TransAgents burada tekrar edilmedi.

## Yöntem

- **Firecrawl:** web ve geliştirici araması, bir README çekimi, yedi hizmet için yapılandırılmış
  araştırma işi (her bilgi kaynak adresiyle). İncelenenler: WTR-LAB, OpenNovel, Lexilit,
  TeaNovel, OmniTranslate, auto-novel (n.novelia.cc), ainoveltranslation.com, winlintun/novel-v1.
- **REA:** WTR-LAB'ın herkese açık bir bölüm sayfası kontrollü, girişsiz bir Chrome'da açıldı
  (`capture_browser_scenario`, yalnız sayfa açma + 5 sn bekleme). Ağ yanıtlarının yalnız
  YAPISI (alan adları, türler, uzunluklar, sayılar) çıkarıldı; çeviri metni ve terim içerikleri
  okunmadı/saklanmadı. Betikler `export_web_scripts` ile dışa aktarıldı (133 dosya), okuyucu
  parçası (`2c8e697d4a97450e.js`) `analyze_javascript_application` ile statik olarak
  çözümlendi (kod çalıştırılmadı). Kanıt kimlikleri: yakalama
  `ev_82c59bb2…` (dışa aktarma), statik analiz `ev_b17a20a6…`.

Gözlem / çıkarım / bilinmeyen ayrımı her maddede belirtilir.

## 1. WTR-LAB (REA ile içeriden)

**Gözlem (ağ yanıtı yapısı):**
- Bölüm akışı üç çağrı: `POST /api/reader/get` (istek alanları `translate`, `language`,
  `raw_id`, `chapter_no`, `chapter_id`, `retry`, `force_retry`) → bölüm meta + `content_url`;
  `GET /api/v2/reader/terms/{kitap}.json` → kitap sözlükleri; `GET content_url` → çeviri gövdesi.
- Çeviri gövdesindeki terimler metne YAZILMIYOR: gövdede `※9⛬` biçiminde 82 yer tutucu
  vardı (55 paragraf). Okuyucu kodu bunları terim listesinden doldurur; Bing/Google yolunda
  işaretçiler çeviri öncesi `[n]`'e çevrilip sonra geri alınır (`2c8e…js`, `async function T`).
- Her bölüm gövdesi kendi sözlük damgasını taşıyor: `glossary_data` (o bölümde geçen 13 terim),
  `glossory_hash`, `glossary_build` ve `content_version`.
- Kitap sözlüğü iki katmanlı: küçük bir elle katman (4 kayıt) ve yapay zekâ katmanı (267 kayıt;
  `build`, `config_hash`, `ai_run`, `replacements`). Kayıt biçimi
  `[[karşılık varyantları], kaynak, tür, cinsiyet, geçiş sayısı]`: 137 kaydın 1'den fazla
  karşılık varyantı var; tür 10 farklı değer, cinsiyet 3 değer, son sütun geçiş sıklığı.
- `ai_run.incorrect`: sözlüğün yapay zekâ denetim koşusu yanlış bulduğu kaydı
  `{gerekçe, düzeltilmiş karşılık, düzeltilmiş tür, düzeltilmiş cinsiyet}` ile saklıyor.
- İstemci tarafı terim nesnesi (`F(u,t)`): `type/typeName`, `gender/genderName`, `is_mixed`,
  `glossary_type` (raw/user), kaynak kimliği ve özet.

**Çıkarım:** WTR-LAB sözlük değişikliğini YENİDEN ÇEVİRİ YAPMADAN eski bölümlere uyguluyor
(SSS de "değişiklik önceden okunan bölümlere de canlı uygulanır" diyor). Bunu mümkün kılan,
modelin terimi metne değil yer tutucuya yazmasıdır. Bölüm damgası, bölümün hangi sözlük
sürümüyle üretildiğini ucuzca söyler.

**Bilinmeyen:** yer tutucunun sunucuda nasıl üretildiği (model mi işaretliyor, sonradan mı
ekleniyor), bağlam/özet stratejisi. Hedef dil İngilizce; ek üreten bir dilde nasıl
davrandığı ölçülmedi.

## 2. Diğer sistemler (Firecrawl, belge düzeyi)

| Sistem | Bizde olmayan / farklı olan |
|---|---|
| OmniTranslate | Seçili PASAJI yeniden üret / iyileştir; sözlük değişince eski çevirilerde isteğe bağlı metin değiştirme; seçili Türkçe metnin kaynağını gösterme; terime önem derecesi; iki çeviriyi kullanıcıya oylatma; model seçici |
| ainoveltranslation | Editor AI: çeviri sonrası öneriler tek tek "kabul / atla"; bölüm başına otomatik özet; terim cinsiyet etiketi; önerilen terim 30 sn sonra kendiliğinden onaylanır (durdurulabilir) |
| OpenNovel | Terim türleri (karakter/unvan/terim) + cinsiyet; CSV içe aktarma; sözlük değişince yalnız sonraki bölümler, mevcut bölüm yeniden üretilir (bizimle aynı) |
| TeaNovel | Bölüm kalite puanı "gözden geçir" işareti olarak; terim durumu doğrulandı/inceleme bekliyor (bizde var) |
| Lexilit | Yan yana özgün/çeviri, satır içi düzenleme, terime telaffuz notu |
| auto-novel | Aynı bölümün birden çok çeviri izi (Youdao/GPT/Sakura) ve okurken iz seçme |
| novel-v1 | Hizalanmış eski çevirilerden RAG örnekleri (bizim Faz 4'e benzer; ölçümümüzde kazanç yoktu), parça sınırında paragraf tekrarı denetimi, sürüm farkı (diff) |

Kaynak adresleri araştırma işinin çıktısında her alan için ayrı verildi; hepsi hizmetlerin kendi
belge sayfalarıdır (ör. `wtr-lab.com/en/faq/13/term-replacer`, `docs.readomni.com/...`,
`ainoveltranslation.com/docs/...`). Pazarlama iddiaları (ör. "tüm romanı anlar") ölçüm
sayılmadı.

## 3. NovelLink ile karşılaştırma

Bizde zaten olanlar (kopyalamaya gerek yok): kitap başına sözlük + tür + koşul, otomatik
öneri ve doğrulama, onaylanmadan çeviriye girmeme, iki dilli hizalı okuma, terim etkisi
(`pipeline.terim_etkisi`, bölüm durumu güncel/eski/İngilizce/farklı), kalite/cilalama/onarım
döngüsü, bölüm arşivi ve geri alma, model seçimi, sözlük ön taraması.

Bizde OLMAYANLAR ve önerilen sıra:

**Ö1 — Sözlük değişikliğini eski bölümlerde yerinde uygulama (en yüksek değer).**
Bugün akış: terim düzelt → terim etkisi listesi → bölümleri tek tek yeniden çevir (bölüm başına
40–60 sn + Vertex ücreti). WTR-LAB ve OmniTranslate yeniden çeviri yapmıyor. Türkçede saf yer
tutucu çalışmaz, çünkü ek terime bağlı değişir (ünlü uyumu, ünsüz yumuşaması, kaynaştırma).
Önerilen biçim: terim etkisinde `eski` durumundaki bölümler için, hizalı paragrafta eski
karşılığı ortak Türkçe eşleştiriciyle bul, kökü yeni karşılıkla değiştir, eki yeni köke göre
yeniden üret; özel adlarda kesme işaretli ek (Kovan'a → Oyuk'a) en güvenli alt küme.
Önizleme göster, onayla, arşivle (geri alınabilir). Kaynaşık ekli cins adlar (Kovanı → Oyuğu)
ikinci adım; emin olunamayan geçiş elle/yeniden çeviriye bırakılır. Model çağrısı yok.
Ölçüm önerisi: SS'te bilinen bir düzeltme (ör. `Hollow Mountain`) üzerinde kaç geçişin
otomatik, kaçının belirsiz kaldığı.

**Ö2 — Okuyucuda paragraf/pasaj yeniden çevirisi.**
Uçlarda yalnız bölüm arşivi var (`/api/chapter/arsiv`), paragraf düzeyinde yeniden çeviri
yok. Hizalama `[[n]]` ile paragraf düzeyinde tutulduğu için tek paragrafı kaynağıyla birlikte
(önceki/sonraki paragraf bağlamıyla) yeniden çevirmek ve iki adayı yan yana gösterip seçtirmek
ucuzdur (tek kısa çağrı). Kalite katmanının "onarılamadı" işaretli paragrafları için doğal giriş
noktası.

**Ö3 — Bölüm başına sözlük damgası.**
Çeviri anında kullanılan sözlüğün özetini (o bölümde geçen kayıtların kimlik + karşılık
özeti) künyeye yaz. Terim etkisi ve Faz 4 bayatlık koruması bugün bunu tarihçeden yeniden
kuruyor; damga, "bu bölüm eski sözlükle çevrildi" rozetini tek karşılaştırmaya indirir.

**Ö4 — Öneriyi kabul/atla ile sunma (Editor AI benzeri).**
Cilalama şu an önerisini doğrudan uyguluyor (anlam kaybı denetimiyle). Düşük güvenli
değişiklikleri okuyucuya "öneri" olarak göstermek kullanıcının denetimini artırır; ancak
okuma akışını böler. Yalnız künyede şüpheli işaretli paragraflarla sınırlı denenmeli.

**Ö5 — Küçük iyileştirmeler.** Terime önem/öncelik (istemde sıralama), terim kayıtlarında
geçiş sıklığı (WTR-LAB her kayıtta tutuyor; istem kesilirken sık terimleri önce almak için),
parça sınırında paragraf tekrarı denetimi (novel-v1).

**Önerilmeyenler:** topluluk önerileri/oylama (tek kullanıcı), cinsiyet alanı (EN→TR'de
zamir cinsiyetsiz; bizde hitap sen/siz daha önemli ve var), RAG örnekleri (Faz 4 ölçümünde
ısrarlı sapma çıkmadı), çoklu çeviri izi (arşiv zaten var).

## 4. Sınırlılıklar

- WTR-LAB'da tek kitap/tek bölüm, girişsiz oturum; kullanıcı sözlüğü, yeniden çeviri ve
  öneri akışları çalıştırılmadı (hesap gerektirir; sahte hesap açılmadı, bkz. 5. bölüm).
  İlk statik analiz okuyucu dışındaki 40 betiği kapsam dışı bırakmıştı; yeniden çalıştırıldı,
  41/41 betik ayrıştırıldı (bkz. 5. bölüm).
- Diğer sistemler yalnız kendi belgelerinden; davranışları gözlenmedi.
- Hiçbir öneri bizim verimizde ölçülmedi; Ö1'in Türkçe ek yeniden üretimindeki isabet
  bilinmiyor ve uygulamadan önce ölçülmeli.

## 5. Uygulama ve ölçüm sonuçları (2026-10-18)

**REA yeniden analiz.** 41/41 betik ayrıştırıldı. Sözlük uçlarından çıkan akışlar:
genel sözlük (`glossary/create-generic`, `edit-generic`, `batch-add-generic`), kullanıcının
genel kaydı ezmesi (`edit-overwrite`, `batch-add-overwrite`), ham terimi yok sayma
(`edit-raw-ignore`, `edit-generic-ignore`), yapay zekâyla terim çözümleme
(`ai-analyze-terms`, `analyze-user-terms`), yeniden çeviri kuyruk işi olarak (`reader/task`,
`queue/update`), hata bildirimleri yapay zekâ çözümlemesiyle (`report/ai-analysis`). Bizdeki
karşılıkları zaten var (kitap sözlüğü, red/yasak listesi, otomatik öneri ve doğrulama, toplu
yeniden çeviri işi); yeni öneri çıkmadı.

**Uygulananlar (canlıda, kabuk v137):** Ö2 tek paragraf yeniden çeviri, Ö3 bölüm başına sözlük
damgası ve bugünkü sözlükle farkı, Ö4 öneriyi kabul/atla paneli (yalnız şüpheli işaretli
paragraflarda), Ö5'ten ardışık paragraf tekrarı şüphesi.

**Uygulanmayan (Ö5, terim önceliği/sıklığı):** istem sözlüğün tamamını değil yalnız parçada
fiilen geçen terimleri alıyor (`translate._relevant_glossary`); kesilen bir liste olmadığı için
sıralamanın etkileyeceği yer yok. Geçiş sayacı (`hit_count`) da bilerek tutulmuyor: okumanın
gövdesi önbellekten geldiği için sistematik eksik sayardı (`glossary.py` notu).

**Ö1 ölçümü (yalnız ölçüm; canlıda kullanıcıya açık değil).** Shadow Slave canlı kopyası,
1.020 bölüm, sözlük geçmişindeki 42 gerçek karşılık değişikliği yeniden oynandı
(`scripts/sozluk_yerinde_olcum.py`, model çağrısı yok; hakem ayrı).

| | Sayı |
|---|---|
| Eski karşılığın geçişi | 3.286 |
| Otomatik değişen | 1.909 (%58) |
| Yeni biçimi kitapta başka yerde de geçen | 1.553 (değişenlerin %81'i) |
| Kaynakta terim yok, dokunulmadı | 807 |
| Ek çok anlamlı / ayrışmadı | 207 / 163 |
| Tekil-çoğul karşılık değişimi, belirsiz bırakıldı | 102 |
| Eşleşme ardında kesmeli ek, belirsiz bırakıldı | 58 |

Hakem (gemini-3.6-flash, sıcaklık 0, yalnız yeni sözcüğün çekimi): ilk koşu 160/179 doğru
(%89), düzeltmelerden sonra 156/167 (%93). Düzeltilen sınıflar: özel ada çokluk eki kesmesiz
(TDK; yabancı adda da), eşleşme ardındaki kesmeli ek ve tekil/çoğul değişimi belirsiz.
Son düzeltme (yabancı adda da çokluk kesmesiz; kalan 11 yanlışın 9'u bu sınıftı) birim
testlerle doğrulandı; hakem koşusu bellek yetersizliğinden yarıda kaldı, yeniden ölçülmedi.
Bilerek bırakılan belirsizlikler: "İblis'i" (ad tamlaması mı belirtme mi), "Fool'ca"
(eşitlik hâli mi yapım eki mi).

**Yer tutucu.** Bugünkü sözlükle 1.020 bölüm şablona çevrilip geri dolduruldu: 1.020/1.020
birebir (ilk koşuda 1.016; kalan 4'ü kaydın bir sözcüğünü küçük yazan model çıktısıydı:
"ilk Lord'a"). Sözcük başına harf maskesi eklendi; ayrıca şablon her belirteci geri doldurup
denetliyor, özgünü birebir vermeyen geçiş metin kalıyor. 48.067 belirteç.

**Sonuç.** Ö1 uygulanabilir: geçişlerin yarıdan fazlası model çağrısı olmadan, ölçülen
çekim doğruluğu %93 ile değişiyor; geri kalanı belirsiz işaretlenip yeniden çeviriye
bırakılabilir. Uygulama (önizleme, onay, arşiv) kullanıcı kararı bekliyor.

