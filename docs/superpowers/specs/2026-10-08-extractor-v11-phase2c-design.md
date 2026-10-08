# Faz 2C — Kitaptan bağımsız extractor v11 tasarımı

Durum: yazılı tasarım; henüz implementasyon veya kullanıcı tasarım incelemesi tamamlanmadı.

## Amaç ve kapsam

Kaynakta açıkça bulunan graph-worthy bilgilerin sessizce kaybolmasını önlemek. Frozen v10'dan ayrı, iki model geçişi ve bağımsız kanıt doğrulaması olan v11 geliştirilecek. İlk teslim yalnız kod, testler, izole kronolojik 1–24 reprocessing ve Türkçe eski/yeni karşılaştırmasıdır. Bu teslim sonunda durulacak; deploy veya canlı yeniden yazım yapılmayacak.

2026-10-08 canlı salt-okunur kontrolü: head=24; pilot MainPID=0, inactive/dead; uygulama servisi active. Chapter 25 cached sonucu ve rollback artifact'ları korunur. Chapter 25 commit edilmez, 26+ başlatılmaz.

Kullanıcının Faz 2C talimatı ürün gereksinimidir. Bu belge teknik uygulama sınırlarını belirler; yeni ürün kapsamı eklemez.

## Yaklaşım seçimi

Önerilen yaklaşım: mevcut SQLite graph semantics ve kontrollü vocabulary üzerinde **ayrı v11 paket + parser adapter'ları + iki bağımsız model geçişi + ortak güvenli validator**. Frozen v10 dosyaları değişmez. Yeni paket app runtime'a otomatik bağlanmaz.

Alternatif 1: v10'a yalnız üç regex düzeltmesi. Küçük değişikliktir fakat yeni kitaplarda discourse, kapsam kaydı ve ikinci geçiş gereksinimlerini karşılamaz.

Alternatif 2: serbest Event/Fact graph'ına geçiş. Kapsamı büyütür ancak kullanıcı bu aşamada yeni generic tabloları yasakladı; mevcut semantik ve authority kurallarını riske atar.

## Mevcut koddan doğrulanan kök nedenler

- `app/core/bilgi_aday.py:aday_dogrula`: endpoint bağlanamazsa `entity_not_allowed` sonucu üretip durur. Yeni kişi keşfi ile canonical graph endpoint kabulü ayrı aşamalar değildir.
- `app/core/bilgi_kanit.py:epistemik_kontrol`: `believ*` genel şüphe örüntüsüne dahildir. `couldn't believe how sudden ... demise` ifadesindeki şaşkınlık ölüm önermesini belirsizleştirebilir.
- `app/core/bilgi_aday.py:span_ayir`: kararlı cümle kimlikleri ve exact offset'ler vardır; çok satırlı blok ownership ve bütün blokların değerlendirildiğini kanıtlayan kapsam sözleşmesi yoktur.
- `app/core/bilgi_aday.py:Anmalar`: genel glossary resolver kullanır. Yeni sürüm N−1 entity/alias görünürlüğünü ayrıca denetleyecek; glossary'de bir adın bulunması geçmişte kimlik/alias bilgisi öğrenildiği anlamına gelmez.
- `app/core/varlik_grafigi.py`: düğümler glossary kimliklerine bağlıdır; ayrı entity tablosu yoktur. Kontrollü vocabulary'de `akrabasi` vardır, özel `kiz_kardesi` ilişkisi yoktur. Akrabalık graph'ta temsil edilir; özel kardeşlik ayrıntısının kaybolmaması için kanıtlı representation-detail gap ayrıca kaydedilir.

## Korunacak sınırlar

Frozen extractor/prompt/schema/core dosyaları ve bütün eski audit artifact'ları korunur. Translation model zinciri, canlı glossary, canlı graph ve ledger değişmez. SQLite KG, authority manual > sistem > model, epistemik durum ile workflow ayrımı, learned_at ile validity ayrımı, transactional chapter commit ve idempotency korunur.

Yeni sürüm kendi extraction ve coverage response sözleşmelerini kullanır; frozen v10 sözleşmesini değiştirmez. Üretim migration yoktur. Clone içinde yalnız kapsam/gap/entity-candidate/audit yardımcı ledger'ları oluşturulabilir; generic Event/Fact/Mystery tabloları oluşturulmaz.

## Bileşenler ve arayüzler

Yeni paket `app/core/bilgi_v11/` altında yer alır:

| Modül | Sorumluluk |
|---|---|
| `contracts.py` | Versioned SourceBlock, ClaimCandidate, EntityCandidate, CoverageDecision, ValidationDecision sözleşmeleri |
| `source.py` | V10 sentence span kimliklerini koruma; exact offset'li paragraph/block manifest'i ve anlatım türü etiketleri |
| `adapters.py` | Adapter kayıt mekanizması; genel structured profile parser ve frozen rune adapter |
| `context.py` | Yalnız N−1 state, görünür endpoint/alias'lar ve same-N deterministic facts hazırlama |
| `discourse.py` | Özne, konuşmacı, zamir/iyelik ve block owner bağlama kanıtları |
| `epistemic.py` | Önerme bazında narrator/belief/rumor/shock/negation/revelation analizi |
| `extraction.py` | Tam kaynak manifest'ini gören candidate-first discovery geçişi |
| `coverage.py` | Kaynağı bağımsız okuyan omission audit ve kapsam sözleşmesi |
| `validation.py` | Exact evidence, endpoint, relation, epistemic, authority ve yüksek etki kapıları |
| `ledger.py` | Clone-only source coverage, gap ve unresolved/audit kayıtları |
| `provider.py` | Vertex-only iki geçiş, bounded retry, pacing ve kullanım ölçümü |
| `pipeline.py` | İki geçişin birleşimi, dedup, revalidate, atomic clone commit/resume |

`scripts/reprocess_v11.py` yalnız açıkça belirtilmiş izole DB ve chapter 1–24 aralığını kabul eder. Snapshot manifest'i yoksa, hedef kaynak backup veya canlı DB ile aynı resolved path ise çalışmaz. `scripts/report_v11.py` Türkçe karşılaştırmayı üretir. Tests `tests/test_v11_*.py` altında tutulur.

Adapter seçimi kitap kimliğine gömülü if/else ile yapılmaz. Parser adapter yapılandırması formata göre seçilir; frozen rune parser mevcut kitabın mevcut profilini tüketebilir. Yeni genel mantık Sunny, Rain, Scholar, Nephis veya chapter numarası içermez.

## Kaynak manifest'i ve tam değerlendirme

Kaynak metin normalize edilerek yeniden yazılmaz. Bütün evidence `source_text[start:end]` olmalı; span/block source hash'ine bağlanır. V10 sentence IDs korunur. Block IDs bölüm ve offset sınırlarından kararlı biçimde üretilir. Her boş olmayan kaynak aralığı manifest'te temsil edilir; yalnız boşluklar fact gerektirmez.

Anlatım türleri tek otorite sınıfına zorlanmaz: narration, dialogue, internal_thought, system_notice, structured_profile, list_attribute, historical_or_flashback, rumor_or_belief. İç içe türler mümkündür; belirsiz sınıflama review'a işaretlenir. Tırnak tek başına system authority sağlamaz.

Her model geçişi bütün block IDs için değerlendirme döndürür. İlk geçiş keyword-selected candidate listesiyle sınırlanmaz; her blok için serbest fakat source-bound aday üretimi mümkündür. Bir kategori veya block cevapsızsa `no_graph_knowledge` varsayılmaz: eksik kapsam hata olarak kaydedilir ve bölüm tamamlanmış sayılmaz.

Kaynak çok büyükse prompt'u sessizce kesmek yasaktır. Bu teslimin 1–24 bölümleri request bütçesine sığıyorsa iki çağrı kullanılır. Sığmayan gelecekteki kaynak için açık `SOURCE_BUDGET_EXCEEDED` oluşur; tam kapsam sağlayan chunk orchestration ayrı geliştirme olmadan atlama yapılamaz.

## Claim ve entity adayları

Her ClaimCandidate şunları taşır: book/chapter/source hash, claim ID, discovery stage, span/block IDs, exact evidence offsets, subject mention/ref, relation/state veya gap tipi, object/value mention/ref, epistemic önerisi, attribution, temporal öneri, coreference/ownership evidence ve novelty kararı.

Yeni adlar EntityCandidate olarak kaydedilir. Adın büyük harfle başlaması yeterli değildir. Naming/relationship/profile bağlamı ve exact mention kanıtı gerekir. Mevcut N−1 endpoint'e birebir güvenli eşleme bulunursa reuse edilir. Eşleme yoksa yeni ayrı kimlik önerilir; otomatik alias merge yapılmaz. Tür belirsizse veya birden çok canonical match varsa unresolved/review.

Clone glossary kaydı yalnız entity validator geçerse, destekleyen fact ile aynı transaction'da oluşur. Aynı kaynak ve ad için replay aynı endpoint'i üretir. Yeni entity kabul edilmezse destekleyen ilişki yok sayılmaz; review kaydıyla birlikte kalır. Gelecek alias veya isimden cinsiyet tahmini yasaktır.

## Deterministik yapılandırılmış profil

Genel adapter `Name` gibi açık owner alanını takip eden `True Name` gibi desteklenen alanları aynı kesintisiz profile bağlar. Dış tırnak/bracket yalnız parsing view'da ele alınır; saklanan evidence orijinal exact kaynaktır.

Yeni `Name` alanı yeni blok başlatır. Birden fazla owner içeren karışık tablo, diyalog veya owner değişimi otomatik bağlanmaz. Ownership proof, owner ve field span'larını birlikte saklar. Örnek içerikli sıradan konuşma veya karşı-olgusal profil, sırf alan formatında diye authoritative kabul edilmez.

Deterministik parsing, bütün profile anlatılarını otomatik `sistem` yapmaz. System/rune bağlamı doğrulanmışsa sistem authority; açık narrator profile fact ise uygun kaynak sınıfı korunur; belirsiz attribution review. Frozen rune adapter çıktıları provenance ve owner proof ile aynı validator'a gider.

## Discourse ve scoped epistemic kuralları

Coreference kaynağın söylem bağlamıyla çözülür; yalnız iki cümle regex penceresi değildir. Model önceki bağlam span'larını ve neden tek öncül olduğunu bildirir. Validator görünür adlar, exact referanslar, owner/speaker zinciri ve karşıt öncülleri denetler. Birden çok makul öncül veya yüksek etkili zamir bağlama otomatik kabul edilmez.

`his little sister was called Rain`: önceki açık owner anlatımıyla iyelik bağlanır; Rain güvenli entity adayıdır. `akrabasi` kabul edilebilir; sister/younger ayrıntısı evidence ve detail gap içinde korunur.

Ölüm örnekleri ayrı test beklentileridir:

| Kaynak yapısı | Beklenti |
|---|---|
| Narrator: `He couldn't believe how sudden X's demise was.` | Şok, narrator ölüm önermesinden ayrılır; açık özne/ölüm kanıtı doğrulanırsa confirmed dead adayı |
| `He didn't believe X had died.` | Ölümün confirmed olduğu çıkarılmaz; atfedilmiş disbelief/uncertain claim review veya uygun epistemic ledger |
| `It was rumored X had died.` | Rumor; confirmed dead olmaz |
| `X was thought dead, but appeared alive.` | Önceki belief ile şimdiki alive ayrılır; otomatik confirmed dead olmaz; çürütme geçişi güvenli update review'a gider |

`couldn't believe` tek başına whitelist değildir: rumor, negation, düşünce veya karşı-olgusal kapsam içindeyse narrator confirmed kabulü yoktur. Model epistemic etiketini kendisi onaylayarak güvenli kapıyı geçemez. Desteklenmeyen dilsel yapı review'a gider.

## İki model geçişi

Sıra: STATE(N−1) → SOURCE(N) manifest'i → same-N deterministic → complete extraction → independent coverage audit → ortak validation → atomic clone commit.

Extraction pass bütün kategorileri kontrol eder: kimlik/takma ad, özel ad, unvan, aile/soy, öğretmen/öğrenci, dostluk/düşmanlık, liderlik/organizasyon, yetenek/nitelik, sahiplik, yaşam/ölüm, konum, rol, dönüşüm, ilişki başlangıcı/bitişi ve çelişki/yanlış inanç/açığa çıkma.

Coverage pass SOURCE(N), STATE(N−1), same-N deterministic ve ilk geçiş önerilerini görür. İlk sonuç otorite değildir. Kaynağı ayrı talimatla baştan inceler; bütün kategoriler ve bloklar için missed_candidate/already_covered/ambiguous/capability_gap/not_graph_worthy sonucu verir. `already_covered` somut claim ID referansı ister; sadece aynı endpoint'in geçmişte bulunması aynı epistemic/temporal iddianın kapsandığını kanıtlamaz.

İkinci geçiş missed_candidate'ları ilk geçiş ile aynı validator'a gider. Dedup anahtarı canonical fact + epistemic + temporal anlamdır. Deterministik same-N aynı claim tekrar yazılmaz. İlk geçişte önerilmiş fakat reddedilmiş/review olmuş claim, accepted sayılmaz; discovery ve final representation ölçümleri ayrıdır.

## Ledger ve güvenli commit

Her blok: evaluated, graph_knowledge_detected, no_graph_knowledge, ambiguous veya representation_gap; ham iki geçiş kararları ve final statü ayrı tutulur. İddia içeren bir blokta birden fazla durum/claim mümkündür. Kapsam ledger'i graph mutation sayısı değildir.

Gap ledger exact evidence, kategori, desteklenmeyen ayrıntı, neden mevcut vocabulary'ye map edilemediği ve keşif geçişini taşır. İlişkiyi benzer başka ilişkiye zorlamak yasaktır. Entity failure, role failure, epistemic ambiguity ve capability gap farklı nedenlerle kaydedilir.

Her bölüm tek SQLite transaction: onaylı yeni endpoints/facts, review/gap/coverage/proposal ledger'ları, request provenance ve head. Hata rollback olur. Provider sonuçları source/state/prompt/schema/version hash'leriyle önce bağımsız cached artifact olarak saklanır; resume aynı geçiş için temiz cache'i revalidate eder. Eski v10 cache v11 sonucunu taklit etmek için kullanılmaz.

Manual/sistem eski kayıtları model overwrite edemez. Faz 2B'nin iki dar rune guard olayı korunur; kapsamı genişletilmez. Temporal/epistemic conflict ve authority değişimleri review'dır. Destructive merge yoktur.

## İzole DB ve 1–24 yeniden değerlendirme

Head24 immutable checkpoint backup ve prepilot backup hash'leri manifest'e kaydedilir. Kaynak/çeviri cache'leri aynı snapshot'tan alınır. Kaynak backup'lar salt okunur açılır; yalnız ayrı clone çalışma DB'sine yazılır. Başlangıç ve final canlı head ayrıca salt okunur doğrulanır.

Eski backup'ta head=0 olması graph'ın boş olduğu anlamına gelmez: tarihsel/future graph bulunduğu için eski graph'ı doğrudan STATE(0) yapmak yasaktır. Reprocessing çalışma DB'sinde ayrı kronolojik projection kurulur; eski snapshot graph'ı karşılaştırma girdisi olarak korunur. Canlı veya immutable backup'tan hiçbir kayıt silinmez.

Projection başlangıcında graph'ta gelecekte öğrenilmiş model/sistem facts ve alias'lar görünmez. Learned_at belirsiz eski kayıtlar geçmiş bilgisi diye prompt'a verilmez. Bilinen öğrenilme tarihli manual authority ayrı protected overlay'de tutulur; yalnız N−1 görünürlüğüyle erişilir. Eski glossary canonical adları identity/alias bilgisi diye kullanılmaz; kaynakta yeniden görülen endpoint adayları konservatif olarak incelenir. Bu politikayla dışlanan eski kayıtlar karşılaştırma raporunda sayılır.

1'den 24'e sırayla her bölüm iki geçişle değerlendirilir. 25 source/extraction çağrısı bu job'a dahil değildir. Bölüm atlama ve yalnız 25'ten patch yoktur. DB hedef/başlangıç head/request cache/source hash değişirse resume STOP eder.

## Provider, retry ve maliyet

İki geçiş yalnız `vertex/gemini-3.8-flash`; free API ve başka provider fallback=0. Translation helper'ın fallback zincirini kullanmak yasaktır. Her request provider/model doğrulaması ve bağımsız kullanım kaydı taşır.

Retry en fazla 4 toplam attempt; yalnız 429, geçici 5xx ve transport hatalarında bounded exponential backoff (30, 60, 120 saniye üst sınırı; küçük jitter) uygulanır. Retry beklemesi parçalara bölünüp durum kaydı yazılır. Request başlangıçları arasında en az 30 saniye pacing. Auth/model-not-found/kalıcı schema hatası sonsuz retry yapmaz; provider blocked veya validation failure olarak açık kaydedilir.

Input/output/thinking/cache tokenları ayrı, latency, retries ve stop reason her geçişte saklanır. Thinking tokenları toplam output'a zaten dahilse iki kez ücretlendirilmez. Maliyet resmi doğrulanmış model/SKU fiyatına dayalı estimate olarak raporlanır; mevcut fiyat doğrulanamazsa unknown olarak açık belirtilir, maliyet uydurulmaz. Billing tutarıyla estimate ayrılır.

## Test ve kabul kapıları

Önce failing regression tests, ardından implementasyon. Üç gerçek fixture (1,12,24) ve aynı dilsel yapıları kullanan farklı kurgusal adlar zorunludur. Gerçek kitap adları production mantığında kullanılmaz.

Negatif testler: ambiguous antecedents, değişen konuşmacı, yanlış owner profile, çoklu Name, diyalogda örnek profile, quoted rumor, shock içindeki rumor, wrong relation direction, unsupported family detail, invalid exact offsets, future alias, manual overwrite, destructive merge, truncated model output, eksik block/category kararları, coverage'da uydurma already_covered referansı, provider fallback, 429 retry exhaustion, atomic rollback ve idempotent resume.

İkinci geçişin bağımsızlık testi: ilk geçiş fixture'da açık bir fact'i kasıtlı atlar; coverage onu bulmalı ve validator destekleneni kabul etmeli. İlk geçiş yanlış claim sunarsa coverage/validator bunu accepted'a çevirmemeli.

Kabul: üç bilinen omission yakalanmış ve accepted/review/gap sonucu açıklanmış; belirsiz/yüksek etkili unsupported kabul yok; yeni entity nedeniyle sessiz kayıp yok; multi-line owner çalışır; second-pass gerçek omitted fact keşfi gösterilir; full suite PASS. Hard safety violations sıfır: future knowledge leak, destructive identity merge, unsupported high-impact accepted, wrong relation accepted, invalid source evidence accepted, manual overwrite.

Kapsamda eksik block varsa tamamlanmış bölüm veya tam source coverage iddiası yapılmaz. Modelin iki tur kendi çıktısını değerlendirmesi insan gold'u değildir; recall yüzde 100 olarak sunulmaz. Accepted precision yalnız açıkça kapsamı belirtilmiş elle/deterministik doğrulanmış fixture örnekleminde hesaplanır; tüm gerçek kaynak için ölçülmemiş precision unknown kalır.

## Türkçe teslim raporu

`reports/phase2c-v11/RAPOR.md`: deterministik coverage, first-pass discovery, second-pass recovered omission, final validator conversion, ölçülebilir precision kapsamı, review/gap/ambiguity ve source-span coverage ayrı raporlanır. Eski/yeni diff newly discovered/recovered/false-positive-review/unresolved/gap/provenance/epistemic sınıflarını taşır. Provenance değişimiyle yeni olgu sayısı karıştırılmaz.

Her recovered omission satırı bölüm, mevcut Türkçe cache bağlamı, authoritative exact English evidence, yeni bilgi, önceki kayıp nedeni, yeni kapı ve accepted/review/gap sonucunu içerir. EN/TR paragraf hizası güvenilir değilse belirsizlik belirtilir; yeni çeviri çağrısı yapılmaz.

Rapor ayrıca final izole head, canlı head24 kontrolü, immutable backup hash'leri, çağrı/kullanım/maliyet, bütün safety metrics ve test kanıtlarını içerir. 1–24 tamamlanmadan veya sağlayıcı bloke olursa kısmi sonuç açık belirtilir; teslim PASS gibi sunulmaz. İlk rapordan sonra durulur; deploy yalnız sonraki ayrı kullanıcı kararıdır.
