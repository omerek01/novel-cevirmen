"""Sözlük temizlik önerisi (bulguyu bilen) ve örneklemeli tarama: çevrimdışı, model çağrısı YOK."""
import pytest

from core import glossary, sozluk_tarama, sozluk_temizlik

KITAP = 'kurgu'


def _kur():
    glossary.merge_terms(KITAP, {'Devil': 'Şeytan', 'daemon': 'Şeytan', 'Lost': 'Kayıplar'}, 'auto', 1)
    glossary.set_term(KITAP, 'Weaver', 'Weaver’s')  # elle yazılmış hatalı kayıt (manual)


def _vaka(*kayitlar):
    return dict(id='v1', kayitlar=[dict(source=s, target=t, origin=o) for s, t, o in kayitlar], bulgular=[])


def test_vakalar_ilgili_kayitlari_birlestirir():
    _kur()
    bulgular = {'Devil': [dict(tur='karsilik_cakismasi', aciklama='x', ilgili=['daemon'])],
                'daemon': [dict(tur='karsilik_cakismasi', aciklama='x', ilgili=['Devil'])],
                'Lost': [dict(tur='bicim', aciklama='y', ilgili=[])]}
    vakalar = sozluk_temizlik.vakalari_kur(KITAP, bulgular, uyum={})
    uyeler = sorted(sorted(k['source'] for k in v['kayitlar']) for v in vakalar)
    assert uyeler == [['Devil', 'daemon'], ['Lost']]


def test_dusuk_uyum_orani_vaka_olur():
    _kur()
    vakalar = sozluk_temizlik.vakalari_kur(KITAP, {}, uyum={'Lost': dict(once=137, uyan=4, oran=0.029)})
    assert [v['kayitlar'][0]['source'] for v in vakalar] == ['Lost']
    assert vakalar[0]['bulgular'][0]['tur'] == 'kayit_oncesi_uyum'


@pytest.mark.parametrize('islem, beklenen', [
    (dict(source='daemon', islem='karsilik_degistir', yeni_karsilik='İblis'), 'oneri'),
    (dict(source='daemon', islem='karsilik_degistir', yeni_karsilik="İblis'i"), 'reddedildi'),   # biçim
    (dict(source='daemon', islem='karsilik_degistir', yeni_karsilik='Kayıplar'), 'reddedildi'),  # başka kavram
    (dict(source='daemon', islem='alternatif_yazim', kanonik='Devil'), 'oneri'),
    (dict(source='daemon', islem='alternatif_yazim', kanonik='Yok'), 'reddedildi'),
    (dict(source='Baska', islem='sil'), 'reddedildi'),                                            # vakada yok
    (dict(source='daemon', islem='uydur'), 'reddedildi'),
])
def test_model_yaniti_yerel_kurallarla_suzulur(islem, beklenen):
    _kur()
    vaka = _vaka(('Devil', 'Şeytan', 'auto'), ('daemon', 'Şeytan', 'auto'))
    sonuc = sozluk_temizlik.yaniti_dogrula(vaka, dict(islemler=[islem]), glossary.get_glossary_rows(KITAP))
    assert sonuc[0]['durum'] == beklenen, sonuc[0]


def test_elle_yazilmis_kayit_degistirilmez_ve_yanitsiz_kayit_isaretlenir():
    _kur()
    vaka = _vaka(('Weaver', 'Weaver’s', 'manual'), ('Lost', 'Kayıplar', 'auto'))
    sonuc = sozluk_temizlik.yaniti_dogrula(vaka, dict(islemler=[dict(source='Weaver', islem='karsilik_degistir',
                                                                     yeni_karsilik='Dokumacı')]), [])
    durum = {x['source']: x['durum'] for x in sonuc}
    assert durum == {'Weaver': 'reddedildi', 'Lost': 'yanitsiz'}


def test_yalniz_onayli_oneri_uygulanir():
    _kur()
    vaka = _vaka(('Devil', 'Şeytan', 'auto'), ('daemon', 'Şeytan', 'auto'), ('Lost', 'Kayıplar', 'auto'))
    oneriler = sozluk_temizlik.yaniti_dogrula(vaka, dict(islemler=[
        dict(source='daemon', islem='karsilik_degistir', yeni_karsilik='İblis'),
        dict(source='Lost', islem='sil'),
        dict(source='Devil', islem='dokunma')]), glossary.get_glossary_rows(KITAP))
    for x in oneriler:
        x['onay'] = x['source'] == 'daemon'  # Lost onaylanmadı
    rapor = sozluk_temizlik.onerileri_uygula(KITAP, oneriler)
    sozluk = glossary.get_glossary(KITAP)
    assert sozluk['daemon'] == 'İblis' and sozluk['Lost'] == 'Kayıplar'
    assert [r['source'] for r in rapor if r['uygulandi']] == ['daemon']


def test_alternatif_yazim_uygulamasi_kaydi_birlestirir():
    glossary.merge_terms(KITAP, {'Chained Isles': 'Zincirli Adalar', 'Chained Islands': 'Zincirli Adalar'}, 'auto', 1)
    vaka = _vaka(('Chained Isles', 'Zincirli Adalar', 'auto'), ('Chained Islands', 'Zincirli Adalar', 'auto'))
    oneriler = sozluk_temizlik.yaniti_dogrula(vaka, dict(islemler=[
        dict(source='Chained Islands', islem='alternatif_yazim', kanonik='Chained Isles')]),
        glossary.get_glossary_rows(KITAP))
    oneriler[0]['onay'] = True
    sozluk_temizlik.onerileri_uygula(KITAP, oneriler)
    assert 'Chained Islands' not in glossary.get_glossary(KITAP)
    assert 'Chained Islands' in glossary.ceviri_sozlugu(KITAP) or 'Chained Isles' in glossary.get_glossary(KITAP)


# ---------- örneklemeli tarama ----------
BOLUMLER = [dict(chapter_no=n, source=f'Mira met Oren at the Ash Gate.\nThe seven lost men walked. {n}\n' * 40)
            for n in range(1, 31)]


def test_ornekleme_tohuma_gore_farkli_ve_tekrarlanabilir():
    a, b, c = (sozluk_tarama.ornekle(BOLUMLER, t) for t in (1, 1, 2))
    assert a == b and [p['chapter_no'] for p in a] != [p['chapter_no'] for p in c]
    assert len(a) == sozluk_tarama.PARCA and all(p['text'] for p in a)


def test_tarama_adaylari_kanit_kayit_siradan_sozcuk_ve_tekrar_suzgeci():
    parcalar = [dict(chapter_no=1, text='Mira met Oren at the Ash Gate. The seven lost men walked.')]
    korpus_bolumleri = [p['source'] for p in BOLUMLER]
    korpus = '\n'.join(korpus_bolumleri) + (' lost' * 50)
    satirlar = [dict(source='Oren', target='Oren')]
    oneriler = [dict(source='Ash Gate', target='Kül Kapısı', kanit='Mira met Oren at the Ash Gate.'),
                dict(source='Oren', target='Oren', kanit='Mira met Oren at the Ash Gate.'),
                dict(source='Lost', target='Kayıplar', kanit='The seven lost men walked.'),
                dict(source='Iron Hall', target='Demir Salon', kanit='Mira entered the Iron Hall.'),
                dict(source='Ash Gate', target='Kül Kapısı', kanit='Mira met Oren at the Ash Gate.')]
    sonuc = {a['source']: a['durum'] for a in sozluk_tarama.adaylari_suz(oneriler, parcalar, satirlar,
                                                                         korpus_bolumleri, korpus)}
    assert sonuc == {'Ash Gate': 'aday', 'Oren': 'zaten_kayitli', 'Lost': 'elendi', 'Iron Hall': 'elendi'}


def test_onaylanan_aday_yazma_kapisindan_gecerek_eklenir():
    adaylar = [dict(source='Ash Gate', target='Kül Kapısı', durum='aday', onay=True),
               dict(source='Iron Hall', target='Demir Salon', durum='aday', onay=False),
               dict(source='Mira', target='Mira', durum='aday', onay=True)]
    eklenen = sozluk_tarama.onaylananlari_ekle(KITAP, adaylar)
    sozluk = glossary.get_glossary(KITAP)
    assert sozluk.get('Ash Gate') == 'Kül Kapısı' and sozluk.get('Mira') == 'Mira' and 'Iron Hall' not in sozluk
    # Seçilen aday DB'ye gelir; ayrı bağlamlı API onayından önce kural olmaz.
    assert eklenen == {}
    assert 'Ash Gate' not in glossary.ceviri_sozlugu(KITAP)
