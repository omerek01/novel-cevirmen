"""Test ortak ayarları: app/ importlanabilir + her test izole geçici DB.

`NOVEL_DB_PATH` env'i geçici dosyaya yönlendirilir; db.db_path() bunu her
çağrıda okuduğu için modül reload gerekmez.
"""
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Bakım araçları da test edilebilsin: karar kuralları (hangi sapma BOZUKTUR) orada
# yaşıyor ve elle doğrulanması pahalı — `bolum_sirasi_denetle` numara/zincir
# ölçütlerini taşıyor ve yanlış bir gevşetme kullanıcının verisini bozar.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVEL_DB_PATH", str(tmp_path / "chapters.db"))
    # Arka plan sözlük doğrulaması GERÇEK model çağırır (`sozluk_dogrulama`):
    # `server` importu `.env`i yüklediği için testte anahtar bulunabilir. Testler
    # çevrimdışıdır; doğrulamayı sınayan test bayrağı kendisi açar.
    monkeypatch.setenv("SOZLUK_DOGRULAMA", "0")
    # Kalite denetimi gerçek model çağırır; kendi testleri açıkça etkinleştirir.
    monkeypatch.setenv("CEVIRI_KALITE", "0")
    monkeypatch.setenv("CEVIRI_ANALIZ", "0")
    yield


@pytest.fixture(autouse=True)
def _sozluk_bekleme(request, monkeypatch):
    """ÜRÜNDE bekleme her zaman açıktır (`glossary.bekleme_acik` -> True: onaysız aday kural olmaz).

    Sözlük davranışının BAŞKA yönlerini sınayan eski testler "otomatik kayıt hemen kural" varsayımıyla
    yazıldı; onlarda bekleme kapatılır. Bekleme akışını sınayan modül `BEKLEME_ACIK = True` tanımlar ya da
    test `@pytest.mark.bekleme` taşır — onlarda ürün davranışı aynen kalır."""
    if getattr(request.module, "BEKLEME_ACIK", False) or request.node.get_closest_marker("bekleme"):
        yield
        return
    from core import glossary
    monkeypatch.setattr(glossary, "bekleme_acik", lambda: False)
    yield
