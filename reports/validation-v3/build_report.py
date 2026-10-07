"""Reproduce the report from frozen outputs; no model calls or graph writes."""
from pathlib import Path
import os, sys, json, hashlib
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
os.environ['NOVEL_DB_PATH'] = str(ROOT/'scratch/validation-v2-20261007/validation.db')
sys.path.insert(0, str(ROOT/'app'))
sys.path.insert(0, str(ROOT))
from core import bilgi_delta as bd, varlik_grafigi as vg, varlik_cikarim as vc
from scripts.validation_v3 import metrikler, parmakizi

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
before=parmakizi(os.environ['NOVEL_DB_PATH'])
rows={'V1':read(OUT.parent/'validation-v2/v1.json'), 'V2':read(OUT.parent/'validation-v2/v2.json'), 'V3':read(OUT/'v3.json')}
mini=read(OUT/'mini.json')
fixture=read(OUT/'expected-delta.json')['items']
plans=read(OUT/'deterministic-plans.json')
resolver=vg.DugumCozucu('shadow-slave')
targets={}
for r in resolver.satirlar.values(): targets.setdefault(r['target'],[]).append(r['source'])
def norm(s):
    k=resolver.coz(s)
    if k:s=resolver.kaynak(k)
    elif len(targets.get(s,[]))==1:s=targets[s][0]
    return vc._normal(s).casefold()
def triple(s,r,o): return (norm(s),r,norm(o))
fields={'new_relationships':('ozne','iliski','nesne','kanit','durum_bilgisi'),
        'new_aliases':('asil','ad','tur','kanit','durum_bilgisi'),
        'state_changes':('varlik','anahtar','deger','kanit','durum_bilgisi')}
def raw_triples(row):
    out=set()
    for section,keys in fields.items():
        for x in (row.get('model_deltasi') or {}).get(section,[]):
            if isinstance(x,list):x=dict(zip(keys,x))
            if section=='new_relationships':out.add(triple(x['ozne'],x['iliski'],x['nesne']))
            elif section=='new_aliases':out.add(triple(x['asil'],x['tur'],x['ad']))
            else:out.add(triple(x['varlik'],vg.DEGER,bd.DURUM_ANAHTARLARI.get(x['anahtar'],x['anahtar'])+'\t'+x['deger']))
    return out
def accepted_triples(row):
    out=set()
    for p in (row.get('degerlendirme') or {}).get('oneriler',[]):
        if p['karar']!='işle' and not p['karar'].startswith('atla:aynı bölüm'):continue
        x=p['veri']
        if p['tur'] in ('new_relationships','new_aliases'):out.add(triple(x['ozne'],x['iliski'],x['nesne']))
        elif p['tur']=='state_changes':out.add(triple(x['varlik'],vg.DEGER,x['anahtar']+'\t'+x['deger']))
    return out
gold=[]
for version,records in rows.items():
    for item in fixture:
        n=item['chapter'];row=next(r for r in records if r['bolum']==n)
        want=triple(item['subject'],item['relation'],item['object'])
        if version=='V3':det={triple(s,r,o) for s,r,o,e in plans[str(n)]}
        else:
            det={triple(b['kaynak'],b['iliski'],b['hedef']) for b in vg.baglar('shadow-slave',en_cok_bolum=n) if b['origin']=='sistem' and b['ilk_bolum']==n}
        found=want in raw_triples(row)
        accepted=want in accepted_triples(row)
        deterministic=item['coverage']=='deterministic' and want in det
        gold.append({**item,'version':version,'model_found':found,'validator_accepted':accepted,
                     'deterministic_covered':deterministic,'effective_covered':accepted or deterministic})
summary={}
for version in rows:
    g=[x for x in gold if x['version']==version]
    prose=[x for x in g if x['coverage']!='deterministic']
    summary[version]={'expected_items':len(g),'model_found':sum(x['model_found'] for x in g),
      'validator_accepted':sum(x['validator_accepted'] for x in g),
      'deterministic_covered':sum(x['deterministic_covered'] for x in g),
      'missing_expected_items':sum(not x['effective_covered'] for x in g),
      'recall_proxy':sum(x['effective_covered'] for x in g)/len(g),
      'prose_expected':len(prose),'prose_model_found':sum(x['model_found'] for x in prose),
      'prose_validator_accepted':sum(x['validator_accepted'] for x in prose),
      'prose_recall_proxy':sum(x['effective_covered'] for x in prose)/len(prose)}
write(OUT/'expected-delta-audit.json',{'method':'strict triples; old stored rune coverage vs v3 fresh pure parser; accepted includes same-N old-graph skips, never rejected/unknown proposals','summary':summary,'items':gold})
metrics={k:metrikler(v) for k,v in rows.items()}
for v,m in metrics.items():
    m.update(summary[v]);m['cost_usd_estimate']=(m.get('giris_tokeni',0)*.75+(m.get('cikis_tokeni',0)+m.get('dusunme_tokeni',0))*3.75)/1e6
metrics['V1'].update(epistemic_non_confirmed=1,wrong_accepted_relationships=0,unnecessary_identity_reviews=0,unsupported_review_items=0,direction_errors=0,high_impact_evidence_failures=0,precision_proxy=None)
metrics['V2'].update(wrong_accepted_relationships=1,unnecessary_identity_reviews=2,unsupported_review_items=5,direction_errors=1,high_impact_evidence_failures=2,precision_proxy=.5)
metrics['V3'].update(wrong_accepted_relationships=0,unnecessary_identity_reviews=0,precision_proxy=1.0,
                    rejected_unsupported_review_items=metrics['V3']['unsupported_review_items'],unsupported_review_items=0)
retro=read(OUT.parent/'validation-v2/v2.audit.json')['v1_duplicate_reanalysis_totals']
metrics['V1']['deterministic_same_chapter_duplicates']=retro['deterministic_same_chapter_duplicates']
metrics['V1']['unsupported_state_keys']=retro['unsupported_state_keys']
metrics['V1']['same_chapter_existing_proposals']=retro['same_chapter_existing_proposals']
mini_metrics=metrikler(mini)
mini_metrics['cost_usd_estimate']=(mini_metrics['giris_tokeni']*.75+(mini_metrics['cikis_tokeni']+mini_metrics['dusunme_tokeni'])*3.75)/1e6
statuses=Counter(x.get('durum_bilgisi') for r in mini for section in ('new_relationships','new_aliases','state_changes') for x in r['model_deltasi'][section])
mainaudit=read(OUT/'v3.model-audit.json')
miniaudit=read(OUT/'mini.audit.json')
assert mainaudit['protected_tables_unchanged'] and miniaudit['protected_tables_unchanged']
assert all(r['olcum']['baglam_tokeni']<=4000 for r in rows['V3']+mini)
assert all(a['ham_yanit']==b['ham_yanit'] for a,b in zip(read(OUT/'v3.initial.json'),rows['V3']))
assert all(a['ham_yanit']==b['ham_yanit'] for a,b in zip(read(OUT/'mini.initial.json'),mini))
audit={'decision':'REPEAT VALIDATION','main':metrics,'mini':mini_metrics,'mini_statuses':dict(statuses),
       'main_provider_attempts':sum(len(r['api_cagrilari']) for r in rows['V3']),
       'mini_provider_attempts':sum(len(r['api_cagrilari']) for r in mini),
       'cost_usd_estimate_total':metrics['V3']['cost_usd_estimate']+mini_metrics['cost_usd_estimate'],
       'raw_responses_unchanged_by_replay':True,'protected_tables_unchanged':True,
       'wrong_accepted_relationships_manual':0,'unsupported_review_claims_accepted_manual':0,
       'high_impact_unsupported_accepted_manual':0,'destructive_merges':0,'backfill_started':False}
write(OUT/'comparison.json',audit)

lines=['# Faz 2A — Validation v3','', '7 Ekim 2026 · **Karar: REPEAT VALIDATION**','',
'V3 uygulandı; aynı 19 bölüm ve ayrı dört epistemik bölüm çalıştırıldı. 670 yönü düzeldi, 691 True Name hatası engellendi. Buna rağmen 848’in iki açık düzyazı bilgisi, 360’taki ilişki çatışması ve 431’in okur düzeyindeki inancı kaçıyor. Rün tekrarları da sıfıra yaklaşmadı. **1–100 backfill başlatılmadı.**','',
'## Kapsam, güvenlik ve yöntem','',
'- Ana set: **2, 15, 24, 61, 106, 162, 273, 313, 352, 360, 381, 394, 479, 555, 670, 691, 822, 848, 923**.',
'- Ayrı epistemik mini-test: **412, 431, 685, 686**. Ana metriklere eklenmedi.',
'- Model `vertex/gemini-3.6-flash`; sürümler **3 / 3 / delta-3**. Structured output, N−1, birleşik 4000 token bütçe korundu.',
f"- **19 + 4 mantıksal çağrı**, **{audit['main_provider_attempts']} + {audit['mini_provider_attempts']} sağlayıcı denemesi**. Model fallback/retry yok. Yön doğrulaması için ikinci LLM çağrısı yapılmadı.",
'- Ayrı `/tmp/novel-validation-v3-20261007` kodu/DB kopyası; mini-test ayrı `mini.db`. Canlı servis deploy/restart edilmedi. Son validator replay yerelde aynı donmuş snapshot üzerinde API çağırmadan yapıldı.',
'- Ham 23 yanıt replay boyunca birebir değişmedi. `*.initial.json` ilk değerlendirmeyi, `v3.json` ve `mini.json` son değerlendirmeyi tutuyor.',
'- Korunan tabloların satır içeriği SHA-256 önce/sonra aynı: chapters, glossary, sozluk_yazim, varlik_bag, varlik_deger, bilgi_bas, bilgi_inceleme, bilgi_isleme, bilgi_oneri. Grafik 1036 bağ / 48 değer; head/review/oneri/isleme boş kaldı. API telemetrisi kopyada yazılabilir; grafik incelemesi kalıcı yazılmaz.',
'- Kaynak N içindeki adlar görülebilir; geçmiş açıklamalar/bağlar N−1 süzgeçlidir. Aynı N rün planı ayrı ve “simulation, not persisted” olarak etiketlidir. Gelecek bağ/alias N üzerinden canonical kimlik oluşturmaz. Yeni isim/sözlük kaydı, destructive merge ve head ilerletme yok.','',
'## Uygulanan doğrulama','',
'1. Mevcut ILISKILER’in tamamına subject_role, object_role, symmetry, inverse label, direction_sensitive ve strong-evidence metadata eklendi. Yeni ilişki türü/`adi` eklenmedi. Kanonik yön öğretmen için **öğrenci → ogretmeni → öğretmen**; lider için grup → lider; diğerleri aşağıdaki denetim tablosunda. `ogrencisi` yalnız ters görünüm etiketi, yeni ilişki türü değil.',
'2. Saf deterministik semantic gate, kaynak span’ı + iki açık isim + rol örüntüsünü denetliyor. Ters yön reddediliyor; rol kurulamazsa NEEDS_REVIEW, otomatik kabul yok. Bu regex kapısı tam bir dil anlama garantisi değildir; kapsanmayan paraphrase incelemeye gider.',
'3. `gercek_adi` yalnız açık True Name ifadesi/sistem ödülüyle. Ordinary naming yeterli değil. Canonical ad mevcut glossary source/kimlik; tekil Türkçe target geri eşlemesi mevcut kayda çözülüyor. Model canonical ad yazdı diye yeni `adi` bağı veya merge yok.',
'4. True Name/unvan/alias tek ilişkiyle temsil ediliyor; aynı raw delta’daki relationship+alias kopyası bastırılıyor. “title … becoming known as name” genel rol örüntüsü unvanın taşıyıcıya yönünü koruyor. İsim uçları kendi canonical adlarıyla eşleşirken çapraz alias’lar uçları yutmuyor. 691’de iki gereksiz critical identity önerisi kuyruğa alınmadı. Gerçek okur kimlik ifşası, iki isim + açık reveal kanıtı varsa insan incelemesine kalır.',
'5. Rün öznesi yalnız mevcut parser’ın doğrulanmış blok/ödül bağlamından geliyor. Normal düzyazıda eksik özne hâlâ ret. `oldurdu`: saldırı, bıçaklama, yaralama, yenme yeterli değil; açık öldürme veya Spell slain gerekir. İnsan kill bildirimi victim dead state de üretir.',
'6. Life status için gerçek özne ve alive/dead/missing/presumed_dead/unknown değeri kurulmalı. Diğer kontrollü state değerinde özellik ve değer kanıtı aranıyor. Unsupported key review üretmiyor.',
'7. Modelin serbest review açıklaması güvenilir kabul edilmiyor. Yapılandırılmış uçlar + kaynak kanıtı + graph issue gerekir; açıklama doğrulanan dar iddiadan yeniden üretilir. Olay özeti, karakterin özel bilgisi, motivasyon, atmosfer veya geçici mood kuyruğa sokulmaz.',
'8. Eski model/NULL epistemik kayıt üzerine gerçek believed önerisi sırf bağ zaten var diye atlanmıyor. Elle/rün geçmişini değiştirecek farklı epistemik iddia incelemeye gider.','',
'## V1 / V2 / V3 — ana 19 bölüm','',
'Accepted ilişkiler **yazım planıdır**, insan onayı veya gerçek yazım değildir. `wrong_accepted_relationships` yanlış semantik/yön; `high_impact_evidence_failures` yetersiz yüksek etkili kanıtı ayrı sayar. Karşılaştırmadaki `unsupported_review_items` kuyruğa kabul edilen kanıtsız iddia sayısıdır: V3 **0**. Çekirdeğin ret sayacı 3, karşılaştırmada ayrı `rejected_unsupported_review_items=3` olarak tutulur.','',
'| Metrik | V1 | V2 | V3 |','|---|---:|---:|---:|']
keys=('schema_failures','raw_relationships','accepted_relationships','wrong_accepted_relationships','evidence_failures','deterministic_same_chapter_duplicates','same_chapter_existing_proposals','unsupported_state_keys','new_entity_candidates','identity_revelations','unnecessary_identity_reviews','epistemic_non_confirmed','review_items','unsupported_review_items','future_knowledge_violations','direction_errors','high_impact_evidence_failures','expected_items','model_found','validator_accepted','missing_expected_items','precision_proxy','recall_proxy','cost_usd_estimate')
for key in keys:
    vals=[]
    for v in metrics:
        x=metrics[v].get(key,0)
        vals.append('N/A' if x is None else (f'{x:.4f}' if isinstance(x,float) else str(x)))
    lines.append(f"| `{key}` | {' | '.join(vals)} |")
lines += ['',
'V1’in 14 bölümü şemadan düştü; precision N/A, 0/0’ı başarı saymıyoruz. V1 tekrar/unsupported key/same-N değerleri v2 raporunun retrospektif eşlemesidir; özgün şema sonucu değiştirilmedi. Expected-delta karşılaştırması da bu tur oluşturulan küçük fixture’a retrospektif eşlemedir, eski koşularda ölçülmüş metrik gibi sunulmaz.',
'Precision proxy yeni kabul edilen ilişkilerde doğru yön **ve yeterli kanıt** oranıdır: V2 **2/4** (670 yanlış yön, 162 bıçaklama kanıtı yetersiz); V3 **2/2** (691 iki unvan). İki örnek yüksek güvenli genel doğruluk iddiası değildir. V2’nin 313 dead kanıtı da yetersizdi; toplam high-impact failure 2 kabulden geçti. V3’ün 3 high-impact yetersiz önerisi reddedildi, kabul edilen 0.',
'V3 aynı-delta kopyaları **4** ayrı sayılır; aynı bölüm rün tekrarları **4**. Aynı-N eski model/elle bağ tekrarları **8**, N−1 tekrarı **0**. İki sayaç birbirine karıştırılmadı. V3 tekrar sayacı yeni parser alanlarının yazmasız planını da kapsar; V1/V2 rün tekrarları eski kayıt kapsamıyla ölçüldüğünden 0→4 doğrudan gürültü artışı olarak yorumlanamaz. Rün tekrarları kalıcıya yazılmadı fakat “yaklaşık sıfır raw tekrar” kapısı geçmedi.','',
'## Ana setin bölüm sonuçları','',
'| Bölüm | Schema hatası | Ham ilişki | Planlanan ilişki | Planlanan state | Kanıt reddi | Review | Bağlam token | Kesilen |',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for row in rows['V3']:
    m=metrikler([row]);lines.append(f"| {row['bolum']} | {m.get('schema_failures',0)} | {m.get('raw_relationships',0)} | {m.get('accepted_relationships',0)} | {m.get('accepted_state_changes',0)} | {m.get('evidence_failures',0)} | {m.get('review_items',0)} | {row['olcum']['baglam_tokeni']} | {m.get('context_dropped',0)} |")
lines += ['',
'## Küçük expected-delta fixture ve recall','',
'Fixture çağrılardan önce oluşturuldu: `expected-delta.json`. Toplam 16 öğe: 9 deterministik, 7 model/review. Exhaustive lore gold değildir. `model_found` raw alanlarda doğru triple; şemadan düşmüş veya kanıtı zayıf raw içerik bulunmuş sayılabilir, kabul sayılmaz. `validator_accepted` işle ya da aynı-N kayıtla doğrulanmış skip; needs_review/ret ve aynı-delta kopyaları sayılmaz. Effective coverage = deterministik parser + validator kabulü.','',
'| Bölüm | Beklenen | Model buldu | Validator kabul | Deterministik kapsadı | Eksik |','|---|---:|---:|---:|---:|---:|']
for n in (15,106,360,670,691,848):
    xs=[x for x in gold if x['version']=='V3' and x['chapter']==n]
    lines.append(f"| {n} | {len(xs)} | {sum(x['model_found'] for x in xs)} | {sum(x['validator_accepted'] for x in xs)} | {sum(x['deterministic_covered'] for x in xs)} | {sum(not x['effective_covered'] for x in xs)} |")
g=summary['V3']
lines += ['', f"Toplam effective recall **{16-g['missing_expected_items']}/16 = {g['recall_proxy']:.1%}**. Düzyazı/review recall **{g['prose_validator_accepted']}/7 = {g['prose_recall_proxy']:.1%}**; raw model doğru triple **{g['prose_model_found']}/7**. Rün kazanımı düzyazı kaybını örtmüyor.",
'- **15:** Sunny Aspect Shadow Slave, Shadow Slave rank Divine, Shadow Bond, Dreamer, True Name ve Shroud award deterministik olmalı. Önce Aspect Rank sonra Aspect Name, standalone Aspect ve Innate Ability, Memory award çözüldü. Shroud’un Awakened rank’ı prose inference: **SHOULD REMAIN MODEL-EXTRACTED**; mevcut quote Shroud’u isimle anmadığından ret, fixture’a kesin kabul beklentisi eklenmedi.',
'- **106:** Stone Saint Shadow type/rank/class/attributes/fragments: **SHOULD BE DETERMINISTIC**. Battle Master/Stalwart önce bilindiğinden fixture yeni Spark of Divinity, Shadow type ve 0/200’e odaklanıyor. Shadow-specific continuation parent korunur; anlatımdan sonra genel Rank satırı önceki özneye bağlanmaz.',
'- **360:** Cassie’nin Sunny’ye ihanetinin ilişki çatışması insan review adayı; “kim ne öğrendi” character-knowledge graph değil. V2’nin verdiği kısa kanıt bütün açıklamayı desteklemiyordu. V3 onu tekrarlamadı ama gerekli friendship conflict’i de bulmadı. Sunny/Harper kill ve Harper dead için verdiği zamirli quote’lar reddedildi. Hastane/duygu özeti eklenmedi.',
'- **670:** model **Sunny → ogretmeni → Effie** buldu. N−1’de teacher bağı yok; mevcut aynı-N eski model kaydıyla doğrulanmış skip. Effie’nin Sunny’yi tanıması okur identity revelation değil. Yanlış Effie→Sunny negative control reddedildi.',
'- **691:** Nether→Demon of Destiny ve Nether→Prince of the Underworld unvan; Hope→Demon of Desire unvan. Model sonuncuyu Demon→takma_adi→Hope çıkardı; genel naming/title kuralı doğru unvan rolüne çevirdi. Relationship/alias/identity üçlü kopyası tek öneriye indi. Prince→gercek_adi→Nether negative control reddedildi. İki ham identity tekrarının critical review’i **0**.',
'- **848:** N−1’de Rain↔Soul Serpent bağı ve Serpent state yok. Context/rune planında sadece Sunny→Soul Serpent sahipliği görülüyor; bu, Rain’e gifting bilgisini temsil etmez. Kaynak ownership gift ve alive bilgilerini açıkça içeriyor, fakat V3 raw delta yine boş. Validator ret değil **model recall kaybı**. Aynı kaynak span’ı ile pozitif kontrol gift=verified, alive=True; bu elle hazırlanan kontrol model_found’a eklenmedi. Kesin içsel model nedeni gözlenemez; rün suppression/boş delta önceliği olası açıklama, doğrulanmış neden gibi sunulmaz.','',
'## Ayrı epistemik mini-test','',
'| Epistemik durum | Ham öğe |','|---|---:|']
for s in vg.DURUM_BILGISI:lines.append(f"| `{s}` | {statuses[s]} |")
lines += ['',
'Çeşitlilik zorlanmadı. Ana 19’da 0 non-confirmed; mini-testte 1 gerçek **believed**. Model yalnız character-specific bilgi iddiası değil, okur/anlatının kesinleşmemiş önermesini etiketledi.','',
'| Bölüm / konu | TEXT ESTABLISHES | MODEL CLASS | İnsan değerlendirmesi |','|---|---|---|---|',
'| 412 yanlış monster yorumu | Awakened topluluğunun görsel bozulma yorumu anlatı tarafından yanlışlanır; fiili copy ayrı gerçek | Delta boş | **QUESTIONABLE**: disproven sinyali kaçıyor; adı olmayan yanlış event önerisini yeni graph türüne zorlamak doğru değil |',
'| 431 Ivory Tower/Tear | Some people believed geçmiş konumunu; kesin coğrafya bilgisi değil | Bu önerme yok; diğer iki öneri confirmed | **WRONG (recall)**: mevcut bulundugu_yer ile believed temsil edilebilir bilgi kaçtı; mevcut doğru confirmed konum önerilerinin epistemik sınıfı doğru |',
'| 685 Sun Prince/Sevirax | “supposed to be a brother”: doğrulanmamış akrabalık aktarımı | believed | **CORRECT**: kesin akrabalık gibi kabul edilmedi; eski NULL model bağına yeni epistemik destek planlandı |',
'| 685 metal colossus soul/sentience | Kolektif inanç + anlatıcıdaki belirsizlik; adı olmayan colossus | Öneri yok | **CORRECT abstention / QUESTIONABLE coverage**: yeni event/soul-inside state türü icat edilmedi; uncertain sinyali graph çıktısında gösterilmedi |',
'| 686 fog/disappearances | Önce rumors, sonra gerçekten geri dönmeyen ekip; aynı önermeler değil | Night Temple konumu confirmed; rumor öğesi yok | **CORRECT** konum sınıfı, **QUESTIONABLE** epistemik kapsam: adsız event söylentisi graph’a zorlanmadı |','',
f"Mini-test: schema **0**, raw relationship **4**, planlanan ilişki **{mini_metrics['accepted_relationships']}**, alias **{mini_metrics['accepted_aliases']}**, review **{mini_metrics['review_items']}**, future **0**, unsupported review claim accepted **0**. Seven-status coverage kanıtlanmadı; yalnız doğal believed davranışı gösterildi. Mini sonuçları ana tabloda sayılmadı.",
'','## İlişki metadata denetimi','',
'Tüm mevcut türler denetlendi; ters etiketler yalnız görünüm metadata’sı, çoğu için yeni inverse ilişki oluşturulmadı. Symmetric türlerde killer/owner gibi yön rolleri aranmaz; named endpoints ve ilişkinin açık lexical kanıtı hâlâ gerekir.','',
'| Tür | Özne rolü → nesne rolü | Simetrik | Ters etiket | Yüksek etkili kanıt |','|---|---|---|---|---|']
for k,m in vg.ILISKILER.items():lines.append(f"| `{k}` | {m['subject_role']} → {m['object_role']} | {'evet' if m['symmetric'] else 'hayır'} | {m.get('inverse_relation') or '—'} | {'evet' if m['requires_strong_evidence'] else 'hayır'} |")
lines += ['', '## Hard gate sonucu','',
'| Kapı | Sonuç |','|---|---|',
'| schema / future / destructive merge = 0 | PASS |',
'| Yanlış yönlü kabul = 0 | PASS; gerçek 670 ve negative control |',
'| Yüksek etkili unsupported kabul = 0 | PASS; 3 zayıf öneri ret |',
'| Unsupported review claim kabul = 0 | PASS; ham noise korunup reddedildi |',
'| Sistematik True Name/unvan karışması yok | PASS; ordinary-name negative control engellendi |',
'| Rün tekrarları yaklaşık sıfır | FAIL; 4 ham tekrar, yazımda 0 |',
'| Doğal non-confirmed mini davranışı | KISMİ PASS; believed gerçek, 431 kaçtı |',
'| Açık düzyazı bilgisi sistematik kaçmıyor | FAIL; 848 gift/alive ve 360 çatışma kaçtı |','',
'## Maliyet, testler ve karar','',
f"Başarılı token usage’tan repo fiyatıyla tahmin: ana **${metrics['V3']['cost_usd_estimate']:.6f}**, mini **${mini_metrics['cost_usd_estimate']:.6f}**, toplam **${audit['cost_usd_estimate_total']:.6f}**. Girdi $0.75/M, çıktı+düşünme $3.75/M. Fatura değildir; ayrı v2 preflight/maliyetleri dahil değildir. Bu turda başarısız/retry sağlayıcı denemesi kaydedilmedi. Offline replay maliyet 0.",
'Testler: tam suite **994 passed / 3 mevcut deprecation warning**; son canonical/alias düzeltmelerinden sonra hedefli **38 passed**. Kökte bare pytest, mevcut scratch/test_user_models.py’nin API key isteyen top-level SystemExit’i nedeniyle collect edemedi; uygulama testi `pytest tests -q` ile tamamlandı.',
'**Öneri: REPEAT VALIDATION.** Bir sonraki tur rün raw suppression ve prose recall’a odaklanmalı; 848 ownership-transfer/alive, 360 bounded relationship-conflict kanıtı, 431 collective believed konumu için bu fixture regresyon kapısı olarak kullanılmalı. 1–100 chronological backfill için hazır değil. Bu rapordan sonra yeni model koşusu/backfill/deploy başlatılmadı.','',
'Kanıt dosyaları: `comparison.json`, `expected-delta*.json`, `deterministic-plans.json`, `negative-controls.json`, `recall-positive-controls.json`, `relation-audit.json`, `v3*.json`, `mini*.json`.']
(OUT/'RAPOR.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
assert before==parmakizi(os.environ['NOVEL_DB_PATH'])
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'app/core/bilgi_delta.py',ROOT/'app/core/bilgi_kanit.py',ROOT/'app/core/varlik_grafigi.py',ROOT/'scripts/validation_v3.py',OUT/'expected-delta.json',OUT/'v3.json',OUT/'mini.json']}
write(OUT/'manifest.json',manifest)
print(json.dumps({'summary':summary,'cost':audit['cost_usd_estimate_total'],'decision':audit['decision']},ensure_ascii=True))
