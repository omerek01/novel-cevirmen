"""Offline V4 final audit/report; no provider calls or graph writes."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'app'),str(ROOT)]
os.environ['NOVEL_DB_PATH']=str(ROOT/'scratch/validation-v2-20261007/validation.db')
from core import bilgi_delta as b,bilgi_kanit as k
from scripts.validation_v3 import parmakizi,metrikler
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
initial=OUT/'final.initial.json'
if not initial.exists():initial.write_bytes((OUT/'final.json').read_bytes())
rows=read(initial); assert {r['bolum'] for r in rows}=={360,431,848,162,313,670,691}
assert all(r['durum']!='failed' for r in rows)
b._connect().close(); before=parmakizi(Path(os.environ['NOVEL_DB_PATH']))
sources={r['chapter_no']:r['source'] for r in b.cache.kaynak_bolumleri('shadow-slave')}
raw_hashes={str(r['bolum']):hashlib.sha256(r['ham_yanit'].encode()).hexdigest() for r in rows}
for r in rows:
    r['model_deltasi']=b.varlik_cikarim_ayristir(r['ham_yanit'])
    r['sema_hatalari']=b.sema_dogrula(r['model_deltasi'])
    r['degerlendirme']=b.delta_degerlendir('shadow-slave',r['bolum'],r['model_deltasi'],sources[r['bolum']])
    r['offline_validator_replay']=True
assert before==parmakizi(Path(os.environ['NOVEL_DB_PATH']))
assert raw_hashes=={str(r['bolum']):hashlib.sha256(r['ham_yanit'].encode()).hexdigest() for r in rows}
write(OUT/'final.json',rows)
write(OUT/'replay-audit.json',{'model_calls':0,'raw_hashes':raw_hashes,'protected_tables_unchanged':True,'before':before,'after':parmakizi(Path(os.environ['NOVEL_DB_PATH']))})
fpath=ROOT/'reports/validation-v4/expected-delta.json'; fixture=read(fpath)
goldhash=hashlib.sha256(fpath.read_bytes()).hexdigest()
assert goldhash==(ROOT/'reports/validation-v4/expected-delta.sha256').read_text()
assert goldhash==read(OUT/'final.audit.json')['fixture_sha256']
(OUT/'expected-delta.json').write_bytes(fpath.read_bytes())
(OUT/'expected-delta.sha256').write_text(goldhash)
by={r['bolum']:r for r in rows}; m=metrikler(rows)
# Frozen gold: typed model discoveries; acceptance includes validated same-N skips.
# Deterministic 162 is separately credited, never presented as model recall.
table=[]
for n,expected,found,accepted,review,gap,wrong,missing,result in [
 (360,1,1,1,1,0,0,0,'PASS'),(431,1,1,1,0,0,0,0,'PASS'),
 (848,2,2,2,0,1,0,0,'PASS'),(162,2,0,0,0,0,0,0,'PASS'),
 (313,1,0,0,0,0,2,1,'MODEL_FAIL'),(670,1,0,0,0,0,0,1,'MODEL_FAIL'),
 (691,3,2,1,0,0,2,2,'MODEL_FAIL')]:
 table.append(dict(chapter=n,provider_status='CARRIED_V4_SUCCESS' if n==431 else 'SUCCESS',expected_items=expected,model_found=found,validator_accepted=accepted,review_correct=review,capability_gap=gap,wrong_items=wrong,missing_items=missing,result=result,deterministic_coverage=2 if n==162 else 0))
assert len(by[360]['degerlendirme']['inceleme'])==1
assert by[360]['degerlendirme']['inceleme'][0][3]['auto_close'] is False
assert by[848]['degerlendirme']['inceleme'][0][0]=='relation_capability_gap'
assert len(by[670]['degerlendirme']['oneriler'])==0
assert sum(len(r['sema_hatalari']) for r in rows)==0
new=[r for r in rows if r['bolum']!=431]
def cost(rs):return sum((r['olcum']['giris_tokeni']*.75+(r['olcum']['cikis_tokeni']+r['olcum']['dusunme_tokeni'])*3.75)/1e6 for r in rs)
accepted_auto=[o for r in rows for o in r['degerlendirme']['oneriler'] if o['karar']=='işle']
metrics=dict(decision='STOP — V4 FINAL GATE FAIL',classification=['MODEL CAPABILITY','PROMPT'],schema_failures=0,future_knowledge_violations=m['future_knowledge_violations'],wrong_direction_accepted=0,high_impact_unsupported_accepted=0,unsupported_review_accepted=0,true_name_confusions=0,unnecessary_identity_items_raw=2,unnecessary_identity_reviews_accepted=0,deterministic_duplicates_raw=m['deterministic_same_chapter_duplicates'],deterministic_duplicates_written=0,expected_items_measured=11,expected_prose_items_measured=9,model_found=6,validator_accepted=5,correct_reviews=1,capability_gaps=1,deterministic_coverage=2,missing_expected_items=4,precision_proxy=1.0,precision_proxy_denominator=len(accepted_auto),recall_proxy=5/9,effective_fixture_coverage=7/11,provider_success_rate=1.0,new_logical_calls=6,new_provider_attempts=sum(len(r['api_cagrilari']) for r in new),new_cost_estimate_usd=cost(new),carried_431_cost_estimate_usd=cost([by[431]]),gate_cost_estimate_usd=cost(rows),max_context_tokens=max(r['olcum']['baglam_tokeni'] for r in rows),operational_response_coverage=1.0,operational_gate_pass_coverage=4/7,fixture_sha256=goldhash,backfill_started=False,raw_metrics=m)
write(OUT/'metrics.json',metrics);write(OUT/'chapter-results.json',table)
outcomes=[]
for x in fixture['items']:
 n=x['chapter']; passed=n in (360,431,848,162) or (n==691 and x['object_value']=='Demon of Destiny')
 outcomes.append({**x,'outcome':'DETERMINISTIC_COVERED' if n==162 else ('ACCEPTED' if passed else 'MISSING_OR_REJECTED')})
write(OUT/'expected-delta-results.json',outcomes)
details=[]
for r in rows:
 details.append({'chapter':r['bolum'],'context_tokens':r['olcum']['baglam_tokeni'],'provider_attempts':r.get('api_cagrilari',[]),'accepted_or_skipped':[o for o in r['degerlendirme']['oneriler'] if not o['karar'].startswith('reddedildi')],'reviews':r['degerlendirme']['inceleme'],'raw_evidence_checks':[{'item':x,'source_span_valid':k.span_gecerli(x.get('kanit',''),sources[r['bolum']])} for s in ('new_relationships','identity_revelations') for x in r['model_deltasi'].get(s,[])]})
write(OUT/'manual-audit.json',details)
lines=['# Faz 2A — V4 FINAL GATE COMPLETION','', '**Karar: STOP — V4 FINAL GATE FAIL. READY FOR 1–100 değil.**','',
'Altı yeni model çağrısı tamamlandı; 431 önceki V4 PASS sonucu taşındı. Sağlayıcı engeli yok. 360 structured review ve 848 transfer/canlılık geçti. 313, 670 ve 691’de model kaynaklı eksik veya hatalı temsil kaldı. Yeni Validation v5 tasarlanmadı; 1–100 başlatılmadı.','',
'## Bölüm sonuçları','',
'| chapter | provider_status | expected_items | model_found | validator_accepted | review_correct | capability_gap | wrong_items | missing_items | result |',
'|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
for t in table:lines.append('| '+' | '.join(str(t[k]) for k in ('chapter','provider_status','expected_items','model_found','validator_accepted','review_correct','capability_gap','wrong_items','missing_items','result'))+' |')
lines+=['',
'162’nin iki beklentisi deterministik parser ile kapsandı; model_found/validator_accepted prose sayısına eklenmedi. validator_accepted burada modelin gold öğelerinin geçerli temsilini (review/gap ve aynı-N doğrulanmış skip dahil) sayar; gerçek DB yazımı değildir. wrong_items ham çıktının yanlış semantik temsil sayısıdır, kabul edilen yanlış öğe değildir. 691’de iki gereksiz identity item; ayrıca Prince kanıtı kaynak dışı kısaltılmıştır.','',
'## Bulgular ve sınıflandırma','',
'- **360 PASS:** Sunny/yoldasi/Cassie canonical resolve edildi, N−1’de b48 mevcut edge bulundu. Kanıt contiguous, 6 cümle/900 karakter sınırı içinde. Açıklama validator tarafından dar kanıttan yeniden üretildi; model aciklama authoritative değil. Auto-close/dusmani/betrayal relation yok.',
'- **431 PASS (taşınan):** Ivory Tower/bulundugu_yer/Tear believed; temporal alanlar NULL. Yeni model çağrısı yok. Aynı ham yanıt validator-only replay edildi; gold başarı korunuyor. Mevcut edge olmayan genel yön belirsizliği artık relationship_conflict kuyruğu oluşturmaz.',
'- **848 PASS:** Rain/Soul Serpent transferi structured relation_capability_gap review ile fark edildi. MISSING_RELATION_CAPABILITY doğru abstention olarak başarı sayıldı. Soul Serpent life_status=alive/confirmed explicit bounded prose ile kabul edildi. Rain için golgesi/anisi/yoldasi üretilmedi; eski master edge kapatılmadı.',
'- **162 PASS — DETERMINISTIC PARSER:** `[You have slain Dreamer Harper.]` Sunny/oldurdu/Harper ve Harper/dead kapsıyor. Model boş delta; parser başarısı model recall diye sayılmadı. Stabbing-only negatif kontrol korunuyor.',
'- **313 MODEL_FAIL — MODEL CAPABILITY / PROMPT:** Kido dead state eksik. Lord of the Dead için parasite ölümünden host kill/dead çıkarımı ham çıktıda iki kez önerildi, ikisi de reddedildi; güvenlik PASS. N−1 bağlamında Tessai/oldurdu/Kido (b306) bulundu; bu önceki bilgi omission açıklaması olabilir, fakat ayrı life_status state beklentisini değiştirmez. Gold sonuca göre düzeltilmedi; fixture yorumunda bu cross-representation suppression belirsizliği ayrıca görünür tutuldu.',
'- **670 MODEL_FAIL — MODEL CAPABILITY:** Yanıt tamamen boş; açık Sunny/ogretmeni/Effie öğesi yok. N−1 bağlamında teacher edge yok. Validator doğru öğeyi reddetmedi; model üretmedi. Ters yön kabulü 0, ters yön negatif kontrol geçiyor.',
'- **691 MODEL_FAIL — MODEL CAPABILITY / PROMPT:** Nether/Demon of Destiny doğru bulundu ve aynı-N eski graph nedeniyle güvenli skip edildi. Prince of the Underworld typed title bulundu ama kanıt düşünce paragrafını kısaltıp erken kapatan bir quote ekliyor; kaynak span/semantic role kontrolünde reddedildi. Hope/Demon of Desire title yerine identity_revelations önerildi; ikinci gereksiz identity item Nether/Prince. İkisi de reddedildi, identity merge/review kuyruğu 0. Ordinary-name→gercek_adi 0. Eksikler: Prince kabulü ve Hope title. Bu yanıt validator kusurunu kanıtlamıyor; model kanıt/temsil sözleşmesine uymadı.',
'',
'PROMPT sınıflandırması kontrol edilebilir çıktı sözleşmesini, MODEL CAPABILITY bu koşuda gözlenen uyum/recall başarısızlığını belirtir; modelin içsel nedeni bilinmiyor. Doğrulanmış parser arızası yok. RELATION VOCABULARY eksikliği yalnız 848 transferinde var ve doğru gap nedeniyle gate blocker değil. VALIDATOR güvenlik kapıları hatalı death/identity/evidence öğelerini kabul etmedi.','',
'## Metrikler','', '| Metrik | Değer |','|---|---:|']
for key in ('schema_failures','future_knowledge_violations','wrong_direction_accepted','high_impact_unsupported_accepted','unsupported_review_accepted','true_name_confusions','unnecessary_identity_items_raw','unnecessary_identity_reviews_accepted','deterministic_duplicates_raw','deterministic_duplicates_written','expected_items_measured','expected_prose_items_measured','model_found','validator_accepted','correct_reviews','capability_gaps','deterministic_coverage','missing_expected_items','precision_proxy','precision_proxy_denominator','recall_proxy','effective_fixture_coverage','provider_success_rate','new_logical_calls','new_provider_attempts','new_cost_estimate_usd','carried_431_cost_estimate_usd','gate_cost_estimate_usd','max_context_tokens','operational_response_coverage','operational_gate_pass_coverage'):
 lines.append(f'| {key} | {metrics[key]} |')
lines+=['',
'Kalite hesabı yalnız başarılı provider yanıtlarında: prose recall **5/9 = %55,56**, deterministik dahil fixture coverage **7/11 = %63,64**. Provider response coverage **7/7**, yeni çağrı başarısı **6/6**; operasyonel gate PASS **4/7**. Capability gap MISS değil. Provider yüzünden recall=0 atanan öğe yok. model_found **6** typed doğru gold keşif; bunların biri invalid evidence ile reddedildi. identity item semantik sinyali typed title başarısı diye sayılmadı.',
'',
'Precision proxy, otomatik kabul planındaki kaynakla destekli öğelerin elle denetimidir; rejected/skipped/review/parser öğelerini denominatora eklemez. Küçük örnekten genel precision garantisi çıkarılmaz. Güvenlikte yanlış kabul 0, recall gate ise geçmedi. Cost USD tahmini token kullanımına dayanır (input $0,75/M, output+thinking $3,75/M); fatura doğrulaması değildir. Taşınan 431 maliyeti yeni ücret diye sayılmadı; eski V4 failed denemelerin bilinmeyen maliyeti bu koşunun tahminine eklenmedi.','',
'## Sözleşme, sınırlar ve doğrulama','',
'Graph mimarisi, relation vocabulary, temporal/epistemic model değişmedi. Yeni relation_capability_gap yalnız review kategorisidir, graph ilişkisi değildir. Model vertex/gemini-3.6-flash; çıkarıcı/istem 4/4, şema delta-3-v4-final; context <=4000. Review kanıtı en fazla 6 contiguous cümle ve 900 karakter, tercih 1–3. Dağınık pasaj birleştirme reddedilir. Fictional generic örnekler kullanıldı; production koduna chapter/kişi special-case eklenmedi.',
'',
'Yeni çağrılar yalnız 360/848/162/313/670/691; 19 bölüm yeniden çalıştırılmadı. Mevcut retry/backoff sınırı değiştirilmedi; altı yeni çağrıda retry 0. Model kalite sorunları için yeni ücretli tekrar başlatılmadı.',
'',
f'Gold unchanged SHA-256: `{goldhash}`. Original expected-delta.json aynen kopyalandı, FIXTURE_CORRECTION yapılmadı. Remote final.audit.json ve yerel replay-audit.json korunan tabloların hash eşitliğini doğruluyor. 1213 kaynak, 1468 glossary, 1036 graph edge, 48 state; head/review/oneri/isleme boş kaldı. Ham yanıt hashleri replay boyunca aynı. Canlı deploy/restart/graph write yapılmadı.',
'',
'Testler: sözleşme değişikliklerinden sonra full suite **1016 passed** (3 mevcut deprecation warning). Son genel relationship-conflict queue düzeltmesinden sonra hedefli testler **45 passed**. Mevcut negatif kontroller: stabbing-only, parasite→host death, reversed teacher, ordinary-name True Name, unsupported review; ayrıca required structured fields, mevcut N−1 edge ve bounded contiguous span kontrolü.',
'',
'Rün duplication: yeni altı çağrıda raw 0, written 0. Eski chapter15 yeniden çağrılmadı; onun önceki raw davranışının modelde düzeldiği iddia edilmiyor. Final semantic gate eksikleri nedeniyle pilot configuration/komutu aktive edilmedi. Kullanıcının IF FAIL kuralına göre burada STOP.','',
'## Artefaktlar','',
'- final.initial.json: remote değerlendirmesi ve değişmeyen ham yanıtlar.',
'- final.json: aynı yanıtların güncel validator-only replay sonucu.',
'- final.audit.json / replay-audit.json: korunan tablolar ve ham yanıt hashleri.',
'- chapter-results.json / expected-delta-results.json / metrics.json: ölçülebilir sonuçlar.',
'- manual-audit.json: kabul/skip/review ve kaynak span kontrolleri.',
'- expected-delta.json / expected-delta.sha256: değişmeyen V4 gold.']
lines += ['', 'Son kodla `pytest tests -q`: **1016 passed, 3 warnings, 88,57 saniye**. Kökteki `pytest -q`, scratch/test_user_models.py import sırasında OPENROUTER_API_KEY olmadığı için collection aşamasında durdu; bu ad hoc script suite sonucuna dahil edilmedi. Ek model çağrısı yapılmadı.']
(OUT/'RAPOR.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(metrics,ensure_ascii=False))
