"""Complete V4 only: carry 431, call six fixed chapters, simulation/no backfill."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT))
NEW=(360,848,162,313,670,691)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('db','out','fixture','carry'):p.add_argument('--'+field,type=Path,required=True)
    p.add_argument('--env',type=Path);a=p.parse_args()
    if a.db.resolve()==(ROOT/'cache/chapters.db').resolve():p.error('live DB forbidden')
    from dotenv import load_dotenv
    if a.env:load_dotenv(a.env)
    os.environ['NOVEL_DB_PATH']=str(a.db.resolve())
    from core import bilgi_delta as b,api_durum
    from scripts.validation_v3 import parmakizi,metrikler
    b._connect().close();before=parmakizi(a.db)
    frozen=hashlib.sha256(a.fixture.read_bytes()).hexdigest()
    carried=next(r for r in json.loads(a.carry.read_text(encoding='utf-8')) if r['bolum']==431)
    assert not carried.get('sema_hatalari') and carried['durum']!='failed'
    carried={**carried,'carried_v4_pass':True};rows=[carried]
    assert not a.out.exists(),'never overwrite/retry an existing run silently'
    calls=[];original=api_durum.istek_kaydet
    def record(*args,**kw):
        names=('anahtar','sira','model','sonuc','kod','sure_ms');v=dict(zip(names,args));v.update(kw)
        calls.append({k:v.get(k) for k in ('model','sonuc','kod','sure_ms')});return original(*args,**kw)
    api_durum.istek_kaydet=record;a.out.parent.mkdir(parents=True,exist_ok=True)
    with api_durum.islem('varlik_cikarim'):
        for n in NEW:
            start=time.time();idx=len(calls)
            r=b.bolum_degerlendir('shadow-slave',n,'vertex/gemini-3.6-flash')
            r['api_cagrilari']=calls[idx:];r.setdefault('olcum',{}).update(sure_sn=round(time.time()-start,2),model_attempts=len(calls)-idx,model_retries=max(0,len(calls)-idx-1))
            r['provider_status']='PROVIDER_BLOCKED' if r['durum']=='failed' and r.get('hata_sinifi')=='model_api_failure' else ('SUCCESS' if r['durum']!='failed' else 'ERROR')
            rows.append(r);a.out.write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding='utf-8')
            print(json.dumps({'chapter':n,'provider':r['provider_status'],'schema':r.get('sema_hatalari'),'delta':r.get('model_deltasi'),'counters':(r.get('degerlendirme') or {}).get('sayac')},ensure_ascii=False),flush=True)
            if r.get('sema_hatalari') or r['provider_status']=='ERROR':print('STOP: model/schema contract failure',flush=True);break
            if r['provider_status']=='SUCCESS':assert r['olcum']['baglam_tokeni']<=4000
    assert before==parmakizi(a.db)
    assert frozen==hashlib.sha256(a.fixture.read_bytes()).hexdigest()
    a.out.with_suffix('.audit.json').write_text(json.dumps({'protected_tables_unchanged':True,'before':before,'after':parmakizi(a.db),'fixture_sha256':frozen,'carry_chapter':431,'new_chapters':[r['bolum'] for r in rows if not r.get('carried_v4_pass')],'model':'vertex/gemini-3.6-flash','versions':[b.CIKARICI_SURUMU,b.ISTEM_SURUMU,b.SEMA_SURUMU],'metrics':metrikler(rows)},ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if len(rows)==7 and all(r['durum']!='failed' for r in rows) else 2
if __name__=='__main__':raise SystemExit(main())
