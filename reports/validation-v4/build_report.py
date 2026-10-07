"""V4 report: records the instructed STOP, never calls a model or writes the graph."""
import hashlib, json, sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from scripts.validation_v3 import metrikler
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')

rows=read(OUT/'v4.json');fixture=read(OUT/'expected-delta.json')
goldhash=hashlib.sha256((OUT/'expected-delta.json').read_bytes()).hexdigest()
assert goldhash==(OUT/'expected-delta.sha256').read_text()
audit=read(OUT/'v4.primary.audit.json')
assert goldhash==audit['fixture_sha256'] and audit['protected_tables_unchanged']
assert [r['bolum'] for r in rows]==[360,431,848]
events=read(OUT/'provider-attempts.json')
attempts=sorted((x for x in events if x['tur']=='istek'),key=lambda x:x['zaman'])
groups={}
for x in attempts:groups.setdefault(x['cagri'],[]).append(x)
assert len(groups)==3 and len(attempts)==6
per_chapter=dict(zip((360,431,848),groups.values()))
write(OUT/'verified-provider-attempts.json',per_chapter)
metrics=metrikler(rows)
cost=(metrics['giris_tokeni']*.75+(metrics['cikis_tokeni']+metrics['dusunme_tokeni'])*3.75)/1e6
statuses=Counter(x['durum_bilgisi'] for r in rows for s in ('new_relationships','new_aliases','state_changes') for x in (r.get('model_deltasi') or {}).get(s,[]))
result={
 'decision':'REPEAT VALIDATION','stop_reason':'360 malformed/unusable review; 848 provider failure 504 -> 429 -> 429',
 'planned_chapters':fixture['chapters'],'model_attempted_chapters':[360,431,848],
 'model_not_run_chapters':[162,313,670,691],'logical_model_calls':3,'provider_attempts':6,
 'schema_failures':0,'model_failures':1,'future_knowledge_violations':0,
 'wrong_direction_accepted':0,'high_impact_unsupported_accepted':0,'unsupported_review_accepted':0,
 'true_name_confusions':0,'deterministic_same_chapter_duplicates_raw':0,'deterministic_duplicates_written':0,
 'expected_model_items':9,'expected_model_items_with_returned_output':2,
 'expected_model_items_provider_unmeasured':2,'expected_model_items_not_run':5,
 'model_found':1,'validator_accepted':1,'review_correct':0,'capability_gaps_detected':0,
 'missing_expected_items':1,'unmeasured_expected_items':7,
 'precision_proxy':1.0,'precision_proxy_denominator':2,
 'recall_proxy':.5,'recall_proxy_denominator':2,'primary_end_to_end_recall_proxy':.25,
 'final_seven_chapter_recall_proxy':None,'cost_successful_usage_estimate_usd':cost,
 'failed_attempt_cost_unknown':True,'statuses':dict(statuses),'protected_tables_unchanged':True,
 'fixture_unchanged':True,'backfill_started':False,
 'special_results':{
  '360':{'relationship_conflict_detected_raw':True,'evidence_bounded':False,'review_useful':False,'validator_review_accepted':False},
  '431':{'collective_belief_detected':True,'status_believed':True,'temporal_range_not_fabricated':True},
  '848':{'transfer_detected':None,'correct_representation_or_gap':None,'alive_detected':None,'rune_duplicate_written':False,'reason':'no model response: provider failure'}
 }}
write(OUT/'metrics.json',result)
known=[]
for x in fixture['items']:
    n=x['chapter']
    state='NOT_RUN' if n not in (360,431,848) else ('PROVIDER_UNMEASURED' if n==848 else ('ACCEPTED' if n==431 else 'DETECTED_RAW_BUT_UNUSABLE'))
    known.append({**x,'outcome':state})
write(OUT/'expected-delta-results.json',known)
lines=[
'# Faz 2A — Hedefli Validation v4','',
'7 Ekim 2026 · **Karar: REPEAT VALIDATION — READY FOR 1–100 değil.**','',
'Kod ve hedefli testler tamamlandı. Önce üç ana hedefte model çağrıldı. **360 kopuşu fark etti, ancak kanıt/ilişki alanları olmayan ve bozuk özne içeren review üretti. 431 geçti. 848 sağlayıcı 504 → 429 → 429 nedeniyle model çıktısı veremedi.** Kullanıcının beklenmeyen yeni problemde DUR kuralıyla kalan dört model çağrısı başlatılmadı. 1–100 backfill başlatılmadı.','',
'## Kapsam ve koşu','',
'- Planlanan final gate: **360, 431, 848, 162, 313, 670, 691**.',
'- Gerçek model çağrısı: **360, 431, 848**; **3 mantıksal çağrı / 6 sağlayıcı denemesi**. Sonuncu yanıt üretmedi. 162/313/670/691 için yeni model çağrısı **0**.',
'- İlk üç kapsam zaten başlatılmıştı; 360 sorunu görüldüğünde 848 çağrısı başlamıştı. Başlamış çağrı sonucu kaydedildi, regression aşaması açılmadı. İkinci/19 bölümlük model koşusu ve otomatik tekrar başlatılmadı.',
'- Model `vertex/gemini-3.6-flash`; çıkarıcı/istem **4/4**, şema **delta-3 değişmedi**. Graph vocabulary, temporal model ve graph tabloları yeniden tasarlanmadı.',
'- Ayrı `/tmp/novel-validation-v4-20261007` kod ve SQLite kopyası. Canlı deploy/restart yok. `v4.primary.audit.json` korunan tabloların önce/sonra içerik hash eşitliğini doğruluyor. Grafik 1036 bağ, 48 değer; head/isleme/oneri/review tabloları boş kaldı.',
'- Mevcut 23 V3 ham yanıt validator-only replay edildi: **0 yeni model çağrısı**, ham metin aynı, korunan tablolar aynı. `v3-validator-replay.json`, `replay-audit.json`.',
'- Final gate’in tamamı koşulmadığından dört regression bölümünde V4 model precision/recall başarısı iddia edilmiyor. Offline regression ve gerçek fixture testleri ayrı kanıttır.','',
'## Çağrıdan önce dondurulan fixture','',
f'`expected-delta.json` SHA-256: `{goldhash}`. Yerel freeze hash ile remote model koşusunun hash’i aynı. Model çıktısına göre gold değiştirilmedi.',
'',
'| Bölüm | Knowledge type | Beklenti | Epistemik durum | Temsil | Sonuç |',
'|---|---|---|---|---|---|']
for x in known:
    lines.append(f"| {x['chapter']} | {x['knowledge_type']} | {x['subject']} / {x['relation_state']} / {x['object_value']} | {x['epistemic_status']} | {x['representation']} | {x['outcome']} |")
lines += ['',
'Toplam **11** öğe: 2 deterministik, 7 model, 1 ilişki review’i, 1 capability-gap kabul edilebilir transfer. `expected_model_items=9`, modelin fark edip geçerli delta/review/gap olarak temsil etmesi gereken bütün non-deterministic sorumlulukları sayar. Başarılı yanıt alınmış gold öğe 2; provider yüzünden ölçülemeyen 2; henüz model çağrılmamış 5.','',
'### FIXTURE_CORRECTION — V3 beklentisinin semantik düzeltilmesi','',
'V3’ün Rain → golgesi → Soul Serpent fixture beklentisi bu tur vocabulary audit’inde fazla güçlü bulundu. `golgesi` mevcut metadata’da **master → Shadow**, `kendi_golgesi` kişinin kendi gölgesi, `anisi` owner → Memory, `yanki` owner → Echo; `grubu` üyelik, `yoldasi` sosyal yoldaşlık. Genel `sahibi`, custody/entrustment/transfer relation yok. Bir teslim/emanet verme mastership veya Memory/Echo türünü kendi başına kanıtlamaz. Ayrıca 848 rünleri Soul Serpent’i hâlâ Sunny’nin Shadows listesinde gösteriyor ve prose bağlantısının sürdüğünü söylüyor. Eski master bağını kapatmak veya Rain’i yeni master yapmak kanıtı aşar.',
'Bu yüzden V4 transfer gold’u, **model çağrısından önce** `MISSING_RELATION_CAPABILITY` review’ine izin verecek biçimde donduruldu. **Bu V4 gold’una sonuçtan sonra yapılan bir düzeltme değildir.** Yeni relation eklenmedi. Yanlış ownership triple yerine transferin graph-worthy bilgi olarak görülmesi ve insan temsil kararı gerekir. Transferin görülüp görülmediği 848 API hatası nedeniyle bu koşuda ölçülemedi.','',
'## Genel extraction değişiklikleri','',
'- Empty delta öncesi dört prose kontrolü: named transfer/entrustment, explicit life status, collective unresolved belief, mevcut companion bağının açık bozulması. Rünlerde varlığın görünmesi yeni prose bilgisini bastırmıyor; suppression yalnız exact triple/state için.',
'- Gave/entrusted/was given/handed over/now belongs dilinde item ve new_holder rolleri kontrol edilir. Teslim/emanet mastership’e körlemesine map edilmez; uygun relation yoksa mevcut review şemasında capability gap. Previous holder kaynak/önceki graph’tan audit edilir; kaynağın kurmadığı holder tahmin edilmez.',
'- Explicit alive/still alive/survived/not dead kanıtı; appeared/moved/spoke/present tek başına yeterli değil. Full ad ve kısa adı aynı bounded span’da görülebilir; kaynak dışı/zamirsiz özne şartı kaldırılmadı. Pozitif gerçek 848 testi, eski ikinci sentence-only kontrolünün bounded span’ı reddettiğini gösterdi; bu redundant kontrol kaynak içindeki bounded span kontrolüne düzeltildi.',
'- Collective belief örnekleri prompta ve deterministik epistemik işaret kapısına eklendi. Tek karakter özel inancı dışarıda. Collective believed hiçbir şekilde confirmed’a yükseltilmez; tarih belirsizse iki temporal alan NULL.',
'- Companion rupture, var olan N−1 bağ + iki açık isim + bounded source + açık ihanet/güven kırılması gerektirir. Review açıklaması dar kanıttan yeniden üretilir; secret/vision gibi ek model açıklamaları taşınmaz. Companion update gelse de AUTO CLOSE yok. Argument/anger/disagreement yeterli değil.',
'- Production logic’e 360/431/848 veya o bölümlerin gerçek kişi/entity adlarıyla special case eklenmedi. Gerçek isimler yalnız fixture/test/rapor verisinde; prompt örnekleri farklı kurmaca isimlerle genel.',
'- API şeması değişmedi. Bu yüzden optional review alanlarının eksikliği JSON schema failure olmayabilir; semantik kapı review’i reddeder. 360’ta tam olarak bu durum görüldü.','',
'## V3’ün dört raw rün tekrarı','',
'| Tekrar | Gözlenen ana kategori | Ek etken | V4 hazırlığı |',
'|---|---|---|---|',
'| Sunny anisi Puppeteer’s Shroud | D: exact claim context’te vardı, çıktı yine tekrarladı | B: curly/straight apostrophe presentation mismatch | Shared canonical name/triple + named-field JSON |',
'| Sunny gorunusu Shadow Slave | D | A/C/E yok | Shared canonical JSON row |',
'| Shadow Slave rutbesi Divine | D | A/C/E yok | Shared canonical JSON row |',
'| Sunny yetenegi Shadow Bond | D | A/C/E yok | Shared canonical JSON row |','',
'D sınıflandırması gözlenen instruction compliance sonucudur; modelin içsel nedenini bildiğimiz anlamına gelmez. Dört claim’in çağrıdan önce context’e girdiği ve normalize triple’ın aynı olduğu doğrulandı; timing yok, relation mismatch yok. İlkinde yazım farkı ek etken. V4 prompt ve validator `canonical_triple/canonical_plan` paylaşır; parser’ın internal `_evrim` işareti graph fact listesine girmez. Output alan adlarıyla tekilleştirilmiş rün JSON listesi çağrıdan önce 4000 ortak bütçeye girer.',
'`15-canonical-context-audit.json` eski/yeni context’i gösterir. **15’te yeni model çağrısı yapılmadı**; aynı bölümde model compliance düzeldiği iddia edilmiyor. V4’ün iki yanıtında raw deterministic duplicate 0, yazılan duplicate 0; bu tam yedi bölüm veya eski 15 davranışının kanıtı değildir. Kullanıcının güncel kapısı korunur: <=1 raw tekrar, root cause anlaşılmış ve yazımda bastırılmışsa tek başına blocker değil.','',
'## İstenen özel sonuçlar','',
'| Bölüm | Kontrol | YES / NO | Kanıt / sınır |','|---|---|---|---|',
'| 360 | Relationship conflict detected? | YES (raw signal) | Model açıklamasında betrayal/rupture var |',
'| 360 | Evidence bounded? | NO | `kanit` alanı yok |',
'| 360 | Review useful? | NO | `iliski`/`nesne` yok; `ozne` entity adı yerine uzun açıklama. Kuyruğa alınmadı |',
'| 431 | Collective belief detected? | YES | Ivory Tower bulundugu_yer Tear |',
'| 431 | Epistemic = believed? | YES | confirmed’a yükseltilmedi |',
'| 431 | No fabricated temporal range? | YES | başlangıç/bitiş NULL |',
'| 848 | Transfer detected? | NO — UNMEASURED | API yanıtı yok; modelin görmezden geldiği söylenemez |',
'| 848 | Correct representation OR capability gap surfaced? | NO — UNMEASURED | Güvenli gap yolu/testi hazır, model başarısı yok |',
'| 848 | Alive detected? | NO — UNMEASURED | API yanıtı yok; full-pipeline fixture testi başarılı |',
'| 848 | No rune duplication written? | YES | Simulation hiçbir graph yazımı yapmadı |','',
'360’ın bozuk `ozne` alanı “SunnyResponse to Cassie’s betrayal and relationship rupture: …” ile başlıyor. Bu JSON parse/schema hatası değil, expected structured review contract’ının semantik başarısızlığı. Eksik kanıt sonradan fixture’dan doldurulup model başarısı gibi sayılmadı.','',
'## V4 metrikleri — kısmi koşu','',
'| Metrik | Değer | Kapsam / açıklama |','|---|---:|---|']
for key,desc in [
('schema_failures','2 başarılı yanıt; review semantic failure ayrı'),
('model_failures','848 provider failure'),
('future_knowledge_violations','Başarılı bağlamlar + offline failed-context audit'),
('wrong_direction_accepted','V4 başarılı yanıtlar; ayrıca negatif control geçiyor'),
('high_impact_unsupported_accepted','Başarılı yanıtlar + negative control'),
('unsupported_review_accepted','360 unsupported review reddedildi'),
('true_name_confusions','V4 raw primary 0; 691 model tekrar çalışmadı'),
('deterministic_same_chapter_duplicates_raw','Yalnız alınan V4 yanıtları'),
('deterministic_duplicates_written','Simulation / protected hashes'),
('expected_model_items','Planlanan 7 bölüm: 9 non-deterministic sorumluluk'),
('model_found','Usable structured expected item: 431. 360 raw signal usable item değil'),
('validator_accepted','Gold 431 öğesi. Gold dışı Sunny/Sky Below ile toplam planlanan ilişki 2'),
('review_correct','Beklenen 360 review: 0. Diğer dar yön incelemesi gold başarısı sayılmadı'),
('capability_gaps_detected','Gerçek model/delta koşusunda 0; offline pozitif testi bu sayıya eklemedik'),
('missing_expected_items','Kesin usable missing: 360. Ölçülemeyenler missing recall diye sunulmuyor'),
('unmeasured_expected_items','848 iki öğe + çağrılmayan regression beş öğe'),
('precision_proxy','2/2 otomatik kabul planı; küçük örnek, 7 bölüm için garanti değil'),
('recall_proxy','1/2 başarılı yanıt alınan expected item; final-gate recall N/A'),
('primary_end_to_end_recall_proxy','1/4 primary expected item; API başarısızlığı dahil'),
('final_seven_chapter_recall_proxy','Kapsam tamamlanmadı')]:
    v=result[key];lines.append(f"| `{key}` | {'N/A' if v is None else v} | {desc} |")
for status in ('confirmed','strongly_implied','believed','rumor','uncertain','disproven','deception'):
    lines.append(f"| `{status}` | {statuses[status]} | Alınan raw relationship/alias/state öğeleri |")
lines += ['',
'`expected-delta-results.json` öğe bazında ACCEPTED / DETECTED_RAW_BUT_UNUSABLE / PROVIDER_UNMEASURED / NOT_RUN ayrımını saklar. Raw açıklamada konuyu fark etme ile kanıtlı usable delta aynı metrik değildir. Boş/ölçülemeyen 0/0 sonuç başarı sayılmadı.','',
'## Sağlayıcı ve maliyet','',
'| Bölüm | HTTP denemeleri | Sonuç |','|---|---|---|',
'| 360 | 429 → 200 | JSON alındı, review usable değil |',
'| 431 | 200 | Collective belief kabul |',
'| 848 | 504 → 429 → 429 | Model API failure, ham yanıt yok |','',
'HTTP kodları kopya SQLite’ın `api_olay` kayıtlarından işlem/call kimliğiyle doğrulandı. Runner callback’in positional kod/süre alanları null kalmıştı; kaynak telemetri `verified-provider-attempts.json` içinde, ham model yanıtı değiştirilmedi. Altı provider attempt = 2 başarılı, 4 geçici hata. Sonuç, 429’un kapasite mi kota mı olduğu konusunda tek başına teşhis değildir.',
f"Başarılı yanıt usage’ından repo fiyatıyla tahmin: **${cost:.7f}** (input 26282, output 592, thinking 6248; $0.75/M ve $3.75/M). Bu **toplam fatura değildir**. Dört başarısız denemenin token/ücretleri bilinmiyor. V3 replay ve offline kontrollerin model maliyeti 0.",
'',
'## Precision regression ve testler','',
'Gerçek bölüm kaynaklı beş negative control **5/5** geçiyor: Effie→ogretmeni→Sunny ret; Prince→gercek_adi→Nether ret; stabbing-alone→oldurdu ret; parasite death→host dead ret; unsupported geniş review ret. `negative-controls.json` ham kontrol ve final validator kararlarını taşır. Hiçbiri graph/review yazmadı.',
'Gerçek 360/431/848 bounded fixture testleri; isimlerden bağımsız beş transfer örneği, beş collective belief biçimi, appearance/movement/speech/presence negatif life testleri, no-auto-close ve canonical apostrophe/same-schema kontrolleri geçti. **1013 passed, 3 mevcut deprecation warning**. Hedefli 57 test de geçti. Graph temporal/schema mimarisi aynı.',
'',
'## Final hard gate kararı','',
'Gözlenen acceptance güvenliği bozulmadı. Buna rağmen 360 usable review kapısı **FAIL**, 848 transfer/alive kapıları **UNMEASURED**, dört regression model bölümü **NOT RUN**. Tam yedi bölümlük gate **PASS değildir**. Bu nedenle **REPEAT VALIDATION**. Kullanıcının DUR kuralıyla yeni model çağrıları kesildi; 19 bölüm yeniden çağrılmadı.',
'Sonraki deneme için çözülmesi gerekenler: review örneğinin tüm mevcut structured alanları ve bounded evidence zorunluluğu açık olmalı; prompttaki eski “ONE sentence” genellemesi bounded-span talimatıyla tutarlı hale getirilmeli. 848 ancak sağlayıcı yanıt verdiğinde ölçülebilir. Bu rapor promptun düzeltilmiş yeni bir model sonucunu içermez; eksik veri elle tamamlanmadı.',
'',
'**1–100 başlatılmadı. READY FOR 1–100 verilmediği için gerçek backfill yürütme komutu önerisi bu raporda aktive edilmedi.**','',
'Kanıtlar: `expected-delta.json/.sha256`, `prior-state-audit.json`, `v3-duplication-audit.json`, `15-canonical-context-audit.json`, `848-context-audit.json`, `v3-validator-replay.json`, `replay-audit.json`, `negative-controls.json`, `v4.json`, `v4.primary.audit.json`, `verified-provider-attempts.json`, `metrics.json`.']
(OUT/'RAPOR.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
write(OUT/'manifest.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app/core/bilgi_delta.py',ROOT/'app/core/bilgi_kanit.py',ROOT/'scripts/validation_v4.py',OUT/'expected-delta.json',OUT/'v4.json',OUT/'v3-validator-replay.json')})
print(json.dumps({'decision':result['decision'],'model_chapters':result['model_attempted_chapters'],'successful_cost_estimate':cost,'full_gate_complete':False},ensure_ascii=True))
