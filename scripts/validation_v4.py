"""V4 fixed 3+4 chapters, simulation only. Primary results inspected before regression."""
import argparse, hashlib, json, os, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'app'))
sys.path.insert(0,str(ROOT))
SET=(360,431,848,162,313,670,691)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--env',type=Path)
    p.add_argument('--stage',choices=('primary','regression'),required=True)
    args=p.parse_args()
    if args.db.resolve()==(ROOT/'cache/chapters.db').resolve():p.error('live DB forbidden')
    from dotenv import load_dotenv
    if args.env:load_dotenv(args.env)
    os.environ['NOVEL_DB_PATH']=str(args.db.resolve())
    from core import bilgi_delta as bd, api_durum
    from scripts.validation_v3 import parmakizi,metrikler
    fixture=json.loads(args.fixture.read_text(encoding='utf-8'))
    assert tuple(fixture['chapters'])==SET and fixture['frozen_before_model']
    goldhash=hashlib.sha256(args.fixture.read_bytes()).hexdigest()
    bd._connect().close()
    before=parmakizi(args.db)
    rows=json.loads(args.out.read_text(encoding='utf-8')) if args.out.exists() else []
    if args.stage=='primary':assert not rows; chapters=SET[:3]
    else:
        assert tuple(r['bolum'] for r in rows)==SET[:3]
        assert all(r['durum']!='failed' and not r.get('sema_hatalari') for r in rows), 'primary failure: regression stage forbidden'
        assert all(all(x.get(k) for k in ('ozne','iliski','nesne','kanit')) for r in rows for x in (r.get('model_deltasi') or {}).get('review_items',[]) if x['kategori']=='relationship_conflict'), 'unexpected primary review format: regression stage forbidden'
        chapters=SET[3:]
    original=api_durum.istek_kaydet
    calls=[]
    def record(*a,**kw):
        calls.append({'model':a[2] if len(a)>2 else kw.get('model'),'sonuc':a[3] if len(a)>3 else kw.get('sonuc'),'kod':kw.get('kod'),'sure_ms':kw.get('sure_ms')})
        return original(*a,**kw)
    api_durum.istek_kaydet=record
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with api_durum.islem('varlik_cikarim'):
        for n in chapters:
            start=time.time();count=len(calls)
            r=bd.bolum_degerlendir('shadow-slave',n,'vertex/gemini-3.6-flash')
            r['api_cagrilari']=calls[count:]
            r.setdefault('olcum',{}).update(sure_sn=round(time.time()-start,2),model_attempts=len(calls)-count,model_retries=max(0,len(calls)-count-1))
            rows.append(r)
            args.out.write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding='utf-8')
            print(json.dumps({'chapter':n,'status':r['durum'],'schema':r.get('sema_hatalari'),'delta':r.get('model_deltasi'),'evaluation':r.get('degerlendirme',{}).get('sayac')},ensure_ascii=False),flush=True)
            if r['durum']=='failed' or r.get('sema_hatalari'):
                print('STOP: unexpected model/schema failure',flush=True);break
            assert r['olcum']['baglam_tokeni']<=4000
    after=parmakizi(args.db)
    assert before==after
    assert goldhash==hashlib.sha256(args.fixture.read_bytes()).hexdigest()
    audit={'stage':args.stage,'before':before,'after':after,'protected_tables_unchanged':True,
           'fixture_sha256':goldhash,'completed':[r['bolum'] for r in rows],'metrics':metrikler(rows),
           'model':'vertex/gemini-3.6-flash','versions':[bd.CIKARICI_SURUMU,bd.ISTEM_SURUMU,bd.SEMA_SURUMU]}
    args.out.with_suffix('.'+args.stage+'.audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=1),encoding='utf-8')
    return 0 if all(r['durum']!='failed' and not r.get('sema_hatalari') for r in rows) and tuple(r['bolum'] for r in rows)==(SET[:3] if args.stage=='primary' else SET) else 2

if __name__=='__main__':raise SystemExit(main())
