"""Sifirlama guvenligi: sunucu erisim kontrolu TEK ATISLIK olmamali.

Olculen kok neden (2026-09-06, kullanici bildirimi "sunucuya baglanmiyor"):
sunucu, `tailscale serve` proxy'si ve tunelin ucu de SAGLAMDI - PC'den
`https://<makine>.ts.net/api/books` 200 donuyordu. Ariza telefonun ILK
istegindeydi: Android'de Tailscale bostayken dusuk guc durumuna geciyor ve tunel
ilk pakette hazir olmuyor. Olcum: PC'den atilan `tailscale ping`in ILKI zaman
asimina ugradi, IKINCISI 38 ms'de dondu.

Tek atislik 4 sn'lik kontrol bu UYANMA ANINI "sunucu kapali" diye okuyup
sifirlamayi reddediyordu. Bu testler yeniden denemenin sessizce kaldirilmasini
tutar; app.js icin JS kosum ortami yok, o yuzden STATIK denetim.
"""
import pathlib

import pytest

APP_JS = pathlib.Path("app/web/app.js")


@pytest.fixture(scope="module")
def kaynak() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_yeniden_deneyen_yardimci_VAR(kaynak):
    assert "async function sunucuyaUlas(" in kaynak


def test_sifirlama_TEK_ATISLIK_kontrol_KULLANMAZ(kaynak):
    """Sifirlama yikici bir islem: yanlis bir 'ulasilamiyor' kullaniciyi
    sunucu sapasaglamken kilitliyor (olculen vaka)."""
    i = kaynak.find('el("shellReset")')
    assert i > 0, "sifirlama dugmesi bulunamadi"
    blok = kaynak[i:i + 2500]
    assert "sunucuyaUlas(" in blok, "sifirlama yeniden deneyen yardimciyi kullanmali"
    assert "await sunucuKabukSurumu()" not in blok, (
        "sifirlama TEK ATISLIK kontrole geri donmus"
    )


def test_ulasildi_ile_surum_okundu_AYRI(kaynak):
    """`null` = 'ULASILDI ama surum deseni eslesmedi'; 'ulasilamadi' DEGIL.

    Eski kontrol ikisini birlestiriyordu ve sunucu ayaktayken bile sifirlamayi
    reddedebilen bir yol biraki­yordu.
    """
    i = kaynak.find("async function sunucuyaUlas(")
    blok = kaynak[i:i + 700]
    assert "ulasildi: true" in blok and "ulasildi: false" in blok
