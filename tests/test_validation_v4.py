import json
from pathlib import Path
import pytest
from core import bilgi_delta as b, bilgi_kanit as k, glossary, varlik_grafigi as g

REAL=json.loads((Path(__file__).parent/'fixtures/validation_v4.json').read_text(encoding='utf-8'))
BOOK='validation-v4-test'
def seed(*names):
    for name in names:glossary.set_term(BOOK,name,name)
    return g.DugumCozucu(BOOK).coz
def empty(**kwargs):return {**{key:[] for key in b.DELTA_SEMASI},**kwargs}

def test_real_companion_rupture_is_narrow_review_and_never_auto_closed():
    key=seed('Sunny','Cassie');g.bag_ekle(BOOK,key('Sunny'),'yoldasi',key('Cassie'),48,'prior','model',1,durum='onaylandi')
    evidence=REAL['360'][REAL['360'].index('But that doesn'):]
    result=b.delta_degerlendir(BOOK,360,empty(review_items=[dict(kategori='relationship_conflict',ozne='Sunny',iliski='yoldasi',nesne='Cassie',kanit=evidence,aciklama='Extra unsupported secret/vision claims must be discarded.',onem='high')]),evidence)
    assert len(result['inceleme'])==1
    description=result['inceleme'][0][2];data=result['inceleme'][0][3]
    assert 'secret' not in description and 'vision' not in description and data['auto_close'] is False
    result=b.delta_degerlendir(BOOK,360,empty(relationship_updates=[dict(ozne='Sunny',iliski='yoldasi',nesne='Cassie',kanit=evidence,degisim='ended')]),evidence)
    assert not any(p['karar']=='işle' for p in result['oneriler'])
    assert len(result['inceleme'])==1
    evidence='Sunny and Cassie were companions. Sunny was angry after their argument.'
    result=b.delta_degerlendir(BOOK,360,empty(review_items=[dict(kategori='relationship_conflict',ozne='Sunny',iliski='yoldasi',nesne='Cassie',kanit=evidence,aciklama='Friendship ended.',onem='high')]),evidence)
    assert not result['inceleme']

def test_real_collective_belief_and_null_time():
    seed('Ivory Tower','Tear');e=REAL['431']
    x=dict(ozne='Ivory Tower',iliski='bulundugu_yer',nesne='Tear',kanit=e,durum_bilgisi='believed',gecerli_baslangic=None,gecerli_bitis=None)
    result=b.delta_degerlendir(BOOK,431,empty(new_relationships=[x]),e)
    assert result['oneriler'][0]['karar']=='işle'
    x['durum_bilgisi']='confirmed'
    assert b.delta_degerlendir(BOOK,431,empty(new_relationships=[x]),e)['oneriler'][0]['karar'].startswith('reddedildi:')

def test_real_transfer_is_capability_review_not_shadow_mastership_and_alive_is_explicit():
    seed('Rain','Soul Serpent');e=REAL['848']
    review=dict(kategori='relation_capability_gap',ozne='Rain',iliski='golgesi',nesne='Soul Serpent',kanit=e,aciklama='MISSING_RELATION_CAPABILITY: transfer',onem='medium')
    state=dict(varlik='Soul Serpent',anahtar='life_status',deger='alive',kanit=e,durum_bilgisi='confirmed')
    result=b.delta_degerlendir(BOOK,848,empty(review_items=[review],state_changes=[state]),e)
    assert result['inceleme'][0][3]['capability_gap'] is True
    assert any(p['tur']=='state_changes' and p['karar']=='işle' for p in result['oneriler']), result['oneriler']
    x=dict(ozne='Rain',iliski='golgesi',nesne='Soul Serpent',kanit=e,durum_bilgisi='confirmed')
    assert not any(p['karar']=='işle' for p in b.delta_degerlendir(BOOK,848,empty(new_relationships=[x]),e)['oneriler'])

@pytest.mark.parametrize('e',['Orion gave Sentinel to Nila.','Orion entrusted Sentinel to Nila.','Sentinel was given to Nila.','Orion handed Sentinel over to Nila.','Sentinel now belongs to Nila.'])
def test_generic_transfer_roles_do_not_imply_shadow_master(e):
    assert k.transfer_kaniti(e,'Nila','Sentinel',{})
    assert k.semantik_sonuc(dict(ozne='Nila',iliski='golgesi',nesne='Sentinel',kanit=e),{})==('unknown','MISSING_RELATION_CAPABILITY')

@pytest.mark.parametrize('e',['Some people believed the Glass Tower stood in the Hollow.','It was widely believed that the Glass Tower stood in the Hollow.','People thought the Glass Tower stood in the Hollow.','According to common belief, the Glass Tower stood in the Hollow.','It was generally assumed that the Glass Tower stood in the Hollow.'])
def test_collective_belief_never_fact(e):
    assert k.epistemik_kontrol(e,'believed') is None
    assert k.epistemik_kontrol(e,'confirmed')

@pytest.mark.parametrize('e',['Ada appeared.','Ada moved.','Ada spoke.','Ada was present.','Ada never survived.'])
def test_presence_not_explicit_alive(e):
    x=dict(varlik='Ada',anahtar='Yaşam',deger='alive',durum_bilgisi='confirmed',kanit=e)
    assert not k.state_kaniti(x,e,{},[])[0]

def test_canonical_rune_context_and_schema_stay_unchanged():
    seed("Puppeteer's Shroud",'Sunny')
    resolver=g.DugumCozucu(BOOK)
    assert b.canonical_triple('Sunny','anisi','Puppeteer’s Shroud',resolver)==('Sunny','anisi',"Puppeteer's Shroud")
    assert b.SEMA_SURUMU=='delta-3-v4-final'


def test_final_conflict_schema_required_fields_optional_description():
    x=dict(kategori='relationship_conflict',ozne='Orion',iliski='yoldasi',nesne='Lina',kanit='Lina betrayed Orion.',onem='medium')
    assert not b.sema_dogrula(empty(review_items=[x]))
    for field in ('ozne','iliski','nesne','kanit','onem'):
        assert b.sema_dogrula(empty(review_items=[{key:value for key,value in x.items() if key!=field}]))


def test_final_conflict_requires_existing_prior_edge_and_entity_names():
    seed('Orion','Lina');e='Lina betrayed Orion. Orion cannot forgive Lina.'
    x=dict(kategori='relationship_conflict',ozne='Orion',iliski='yoldasi',nesne='Lina',kanit=e,onem='medium')
    assert not b.delta_degerlendir(BOOK,2,empty(review_items=[x]),e)['inceleme']
    key=g.DugumCozucu(BOOK).coz;g.bag_ekle(BOOK,key('Orion'),'yoldasi',key('Lina'),1,'prior','model',1,durum='onaylandi')
    assert b.delta_degerlendir(BOOK,2,empty(review_items=[x]),e)['inceleme']
    x['ozne']='OrionResponse to betrayal and rupture'
    assert not b.delta_degerlendir(BOOK,2,empty(review_items=[x]),e)['inceleme']


def test_final_bounded_review_no_stitched_quotes_or_long_span():
    assert k.review_span_gecerli('Ada betrayed Boris. Boris cannot forgive Ada.','Ada betrayed Boris. Boris cannot forgive Ada.')
    source='Ada betrayed Boris. Unrelated intervening sentence. Boris cannot forgive Ada.'
    assert not k.review_span_gecerli('Ada betrayed Boris. Boris cannot forgive Ada.',source)
    long=' '.join(['Ada and Boris were companions.']*7)
    assert not k.review_span_gecerli(long,long)
