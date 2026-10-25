"""fetch: paragraf sırası koruması + filigran süzgeci (tel tuzağı).

freewebnovel 2026-10-24 civarında `<p>` etiketlerini HTML'e KARIŞIK sırada
yazmaya başladı; doğru sırayı `data-reader-order-index` / `style="order:N"`
ile taşıyıp kapsayıcıyı flex yaparak tarayıcıda düzeltiyor. HTML sırasını
okuyan ayrıştırıcı bölümü karışık kaydediyordu ve paragraf İÇİ kalite
denetimlerinin hiçbiri (hizalama, uzunluk oranı, sözlük, kalıntı) bunu
göremiyordu. Bu testler sıralamanın kurulduğunu, işaretsiz sayfalarda
davranışın DEĞİŞMEDİĞİNİ ve çözülemeyen korumada GÜRÜLTÜLÜ hata verildiğini
sabitler.
"""
import pytest
from bs4 import BeautifulSoup

from core import fetch


def _icerik(html: str):
    return BeautifulSoup(f'<div id="article">{html}</div>', "html.parser").select_one("#article")


def test_karisik_html_dogru_siraya_dizilir():
    el = _icerik(
        '<p data-reader-order-index="3" style="order:3;">ucuncu</p>'
        '<p data-reader-order-index="1" style="order:1;">birinci</p>'
        '<p data-reader-order-index="2" style="order:2;">ikinci</p>'
    )
    assert fetch._sirali_paragraflar(el) == ["birinci", "ikinci", "ucuncu"]


def test_eksik_indeks_sorun_degil():
    """Site bazı yuvaları `data-reader-order-optional` ile boş bırakıyor."""
    el = _icerik(
        '<p data-reader-order-index="42">son</p>'
        '<p data-reader-order-index="1">ilk</p>'
        '<p data-reader-order-index="17">orta</p>'
    )
    assert fetch._sirali_paragraflar(el) == ["ilk", "orta", "son"]


def test_nitelik_yoksa_stil_order_kullanilir():
    """Site veri niteliğinin adını değiştirirse `style="order:N"` kalır."""
    el = _icerik(
        '<p style="order:2;">ikinci</p>'
        '<p style="order:1;">birinci</p>'
    )
    assert fetch._sirali_paragraflar(el) == ["birinci", "ikinci"]


def test_isaret_yoksa_html_sirasi_korunur():
    """İşaretsiz siteler ve eski sayfalar için davranış eskisiyle AYNI."""
    el = _icerik("<p>bir</p><p>iki</p><p>uc</p>")
    assert fetch._sirali_paragraflar(el) == ["bir", "iki", "uc"]


def test_bos_paragraflar_atilir():
    el = _icerik("<p>bir</p><p>   </p><p></p><p>iki</p>")
    assert fetch._sirali_paragraflar(el) == ["bir", "iki"]


def test_korumali_ama_cozulemeyen_sira_hata_firlatir():
    """Kapsayıcı koruma imzası taşıyor ama paragrafların yarısı işaretsiz.

    Sessizce HTML sırasına düşmek bozuk metni kalıcı önbelleğe yazardı ve
    önbellek isabeti bir daha çeviri tetiklemediği için kullanıcı o bölümü
    sonsuza dek karışık okurdu.
    """
    el = BeautifulSoup(
        '<div id="article" data-reader-order="pending" data-reader-order-count="3">'
        '<p data-reader-order-index="2">a</p><p>b</p><p>c</p></div>',
        "html.parser",
    ).select_one("#article")
    with pytest.raises(fetch.FetchError, match="sıra işareti çözülemedi"):
        fetch._sirali_paragraflar(el)


def test_cakisan_indeks_hata_firlatir():
    """İndeksler tekil değilse sıra belirsizdir; dizmek paragrafı rastgele taşırdı."""
    el = _icerik(
        '<p data-reader-order-index="1">a</p>'
        '<p data-reader-order-index="1">b</p>'
    )
    with pytest.raises(fetch.FetchError, match="sıra işareti çözülemedi"):
        fetch._sirali_paragraflar(el)


def test_tek_tuk_order_stili_alarm_vermez():
    """Düzen amaçlı tek bir `order:` alarmı tetiklemez (yarıdan azı işaretli)."""
    el = _icerik('<p style="order:1;">a</p><p>b</p><p>c</p><p>d</p>')
    assert fetch._sirali_paragraflar(el) == ["a", "b", "c", "d"]


def test_filigran_suzulur():
    """Unicode matematiksel alfanumerik blok = sitenin gömdüğü filigran."""
    el = _icerik("<p>Sunny \U0001D41F\U0001D42B\U0001D41E\U0001D41E.com durdu</p>")
    assert fetch._sirali_paragraflar(el) == ["Sunny .com durdu"]


def test_yalnizca_filigrandan_olusan_paragraf_atilir():
    el = _icerik("<p>gercek</p><p>\U0001D41F\U0001D42B\U0001D41E\U0001D41E</p>")
    assert fetch._sirali_paragraflar(el) == ["gercek"]


def test_parse_karisik_sayfayi_dogru_sirada_cozer():
    """Uçtan uca: `_parse` çıktısındaki metin doğru sırada olmalı."""
    html = (
        '<html><head><title>x</title></head><body>'
        '<span class="chapter">Chapter 7: Test</span>'
        '<div id="article" data-reader-order="pending" data-reader-order-count="3">'
        '<p data-reader-order-index="2" style="order:2;">ikinci</p>'
        '<p data-reader-order-index="3" style="order:3;">ucuncu</p>'
        '<p data-reader-order-index="1" style="order:1;">birinci</p>'
        "</div></body></html>"
    )
    out = fetch._parse(
        html,
        "https://freewebnovel.com/novel/shadow-slave/chapter-7",
        fetch.SITES["freewebnovel"],
    )
    assert out["text"] == "birinci\n\nikinci\n\nucuncu"
