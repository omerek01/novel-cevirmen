"""Ayrı kaynak bağlı API onayı: hatalı yanıt asla etkin kural değildir."""
import json
from types import SimpleNamespace

import pytest

from core import cache, glossary, sozluk_dogrulama as dogrulama, translate

KITAP = 'api-onayi'
KAYNAK = 'At dusk, Mira entered the Ash Gate. The gate was made of grey stone.'


def satir():
    return next(r for r in glossary.get_glossary_rows(KITAP) if r['source'] == 'Ash Gate')


def hazirla(monkeypatch):
    monkeypatch.setenv('SOZLUK_DOGRULAMA', '1')
    glossary.merge_terms(KITAP, {'Ash Gate': 'Kül Kapısı'}, 'auto', 1)
    cache.save_chapter('https://example.test/1', dict(book_slug=KITAP, chapter_no=1,
                       title='1', source=KAYNAK, translation='Mira Kül Kapısı’na girdi.'))
    monkeypatch.setattr(translate, 'ceviri_anahtari_var_mi', lambda *_: True)
    return satir()


def sahte(monkeypatch, kayit, *, finish='STOP', duzenle=None, kanit=True):
    sayac = []

    def generate(factory, models, user, system, max_tokens):
        sayac.append(user)
        if duzenle:
            duzenle()
        # Yeni istekte kimlik ve bağlamlar JSON; eski kod için bilinçli aynı yanıt.
        try:
            payload = json.loads(user)
            request = payload['kayitlar'][0]
            evidence = request.get('baglamlar', [])
        except ValueError:
            evidence = []
        item = dict(source='Ash Gate', kimlik=kayit['kimlik'], uygun=True,
                    karar='onay', tur='yer', tanim='Taştan yapılmış kapı.',
                    genel_sozcuk=False, sorun='', oneri='', kanit=[])
        if kanit and evidence:
            item['kanit'] = [dict(baglam_id=evidence[0]['id'], alinti=evidence[0]['metin'])]
        return SimpleNamespace(text=json.dumps({'terms': [item]}),
            candidates=[SimpleNamespace(finish_reason=finish)],
            usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=10)), 'sahte'

    monkeypatch.setattr(translate, '_generate_with_fallback', generate)
    return sayac


@pytest.mark.parametrize('uygun', [None, 'false', 'true', 1, 0])
def test_acik_boolean_olmayan_onay_gecmez(uygun):
    assert dogrulama.karar_ver({'source':'Ash Gate','target':'Kül Kapısı'},
                              {'uygun':uygun})[0] != 'gecti'


def test_dogrulama_kapali_olsa_da_otomatik_aday_bekler(monkeypatch):
    monkeypatch.setenv('SOZLUK_DOGRULAMA', '0')
    monkeypatch.setenv('SOZLUK_BEKLEME', '0')
    glossary.merge_terms(KITAP, {'Ash Gate':'Kül Kapısı'}, 'auto', 1)
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)


@pytest.mark.parametrize('finish', [None, 'MAX_TOKENS', 'SAFETY'])
def test_kesilmis_yanit_adayi_etkinlestirmez(monkeypatch, finish):
    kayit = hazirla(monkeypatch)
    sahte(monkeypatch, kayit, finish=finish)
    dogrulama.kitabi_dogrula(KITAP, 'bekleyen', api_key='sahte')
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)


def test_kaynak_baglam_yoksa_cagri_ve_onay_yok(monkeypatch):
    kayit = hazirla(monkeypatch)
    monkeypatch.setattr(cache, 'kaynak_bolumleri', lambda _: [])
    calls = sahte(monkeypatch, kayit)
    sonuc = dogrulama.kitabi_dogrula(KITAP, 'bekleyen', api_key='sahte')
    assert calls == []
    assert sonuc and sonuc[0]['sonuc'] == 'baglam_eksik'
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)


def test_alintisiz_model_onayi_kural_olmaz(monkeypatch):
    kayit = hazirla(monkeypatch)
    sahte(monkeypatch, kayit, kanit=False)
    dogrulama.kitabi_dogrula(KITAP, 'bekleyen', api_key='sahte')
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)


def test_gecerli_onay_ve_resume_yeniden_cagri_yapmaz(monkeypatch):
    kayit = hazirla(monkeypatch)
    calls = sahte(monkeypatch, kayit)
    sonuc = dogrulama.kitabi_dogrula(KITAP, 'bekleyen', api_key='sahte')
    assert sonuc[0]['sonuc'] == 'gecti'
    assert glossary.ceviri_sozlugu(KITAP)['Ash Gate'] == 'Kül Kapısı'
    dogrulama.kitabi_dogrula(KITAP, 'hepsi', api_key='sahte')
    assert len(calls) == 1


def test_api_sirasinda_degisen_kayda_eski_onay_yazilmaz(monkeypatch):
    kayit = hazirla(monkeypatch)
    sahte(monkeypatch, kayit, duzenle=lambda: glossary.terimi_yaz(KITAP,'Ash Gate','Kül Geçidi'))
    dogrulama.kitabi_dogrula(KITAP, 'bekleyen', api_key='sahte')
    assert satir()['dogrulama'] != 'gecti'
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)


def test_elle_yeni_kayit_ve_import_once_bekler():
    glossary.terimi_yaz(KITAP,'Ash Gate','Kül Kapısı')
    glossary.ice_aktar(KITAP,[{'source':'Iron Hall','target':'Demir Salon'}])
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)
    assert 'Iron Hall' not in glossary.ceviri_sozlugu(KITAP)


def test_duzenlemede_eski_onayli_karsilik_yeni_onaya_kadar_korunur():
    glossary.set_term(KITAP,'Ash Gate','Kül Kapısı')  # açık eski insan kararı
    glossary.onayla(KITAP,'Ash Gate')
    glossary.terimi_yaz(KITAP,'Ash Gate','Kül Geçidi')
    assert satir()['durum'] == glossary.TUTULDU
    assert glossary.ceviri_sozlugu(KITAP)['Ash Gate'] == 'Kül Kapısı'


def test_rapordan_eski_baglamsiz_onay_uygulanamaz(monkeypatch):
    hazirla(monkeypatch)
    dogrulama.sonucu_yaz(KITAP, {'source':'Ash Gate','sonuc':'gecti','not':{'uygun':True}})
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)
