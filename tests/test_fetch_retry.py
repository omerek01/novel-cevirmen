"""fetch_chapter yeniden deneme iskeleti: kapı her denemede ayrı, uyku kapı DIŞINDA.

Ağ/Playwright yok — _fetch_locked ve time.sleep sahtelenir. Üç sözleşme:
(1) geçici hata (_Transient) üstel geri-çekilmeyle yeniden denenir ve uyku
sırasında kapı BOŞTUR (okuyucu araya girebilir); (2) kalıcı hata
(CloudflareChallenge/FetchError) hiç yeniden denenmez; (3) denemeler tükenince
son geçici hatanın mesajıyla FetchError fırlar.
"""
import pytest

from core import fetch


def test_transient_retries_then_succeeds_with_gate_free_during_sleep(monkeypatch):
    calls = []
    delays = []

    def fake_locked(url, headless, timeout_ms):
        calls.append(url)
        if len(calls) == 1:
            raise fetch._Transient("yavaş yükleme")
        return {"title": "B1"}

    def fake_sleep(seconds):
        delays.append(seconds)
        # Geri-çekilme uykusu kapı DIŞINDA geçmeli: uyurken kapı boş olmalı ki
        # okuyucu (veya başka iş) çekim yapabilsin.
        assert fetch._FETCH_GATE._busy is False

    monkeypatch.setattr(fetch, "_fetch_locked", fake_locked)
    monkeypatch.setattr(fetch.time, "sleep", fake_sleep)

    out = fetch.fetch_chapter("u1", retries=2)

    assert out == {"title": "B1"}
    assert calls == ["u1", "u1"]  # 1 hata + 1 başarı
    assert delays == [2.0]  # ilk geri-çekilme 2 sn


def test_permanent_error_is_not_retried_and_releases_gate(monkeypatch):
    calls = []

    def fake_locked(url, headless, timeout_ms):
        calls.append(url)
        raise fetch.CloudflareChallenge("doğrulama geçilemedi")

    def fail_sleep(_):
        raise AssertionError("kalıcı hatada geri-çekilme uykusu olmamalı")

    monkeypatch.setattr(fetch, "_fetch_locked", fake_locked)
    monkeypatch.setattr(fetch.time, "sleep", fail_sleep)

    with pytest.raises(fetch.CloudflareChallenge):
        fetch.fetch_chapter("u1", retries=2)

    assert calls == ["u1"]  # tek deneme, tekrar yok
    # Kapı hata yolunda da bırakılmış olmalı (finally): yeniden alınabilir.
    fetch._FETCH_GATE.acquire("interactive")
    fetch._FETCH_GATE.release()


def test_exhausted_retries_raise_fetcherror_with_last_message(monkeypatch):
    calls = []
    delays = []

    def fake_locked(url, headless, timeout_ms):
        calls.append(url)
        raise fetch._Transient("içerik gelmedi")

    monkeypatch.setattr(fetch, "_fetch_locked", fake_locked)
    monkeypatch.setattr(fetch.time, "sleep", delays.append)

    with pytest.raises(fetch.FetchError, match="içerik gelmedi"):
        fetch.fetch_chapter("u1", retries=2)

    assert calls == ["u1", "u1", "u1"]  # ilk deneme + 2 tekrar
    assert delays == [2.0, 4.0]  # üstel geri-çekilme
