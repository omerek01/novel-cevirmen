"""Roman sayfası çekilirken ağır kaynakları indirme.

Neden: Playwright bugün her bölüm sayfasında sitenin reklamlarını, logosunu ve
fontlarını da indiriyor; oysa koddan yalnız `site["content"]` seçicisindeki
metin alınıyor. Proxy GB başına ücretlendirildiği için bu doğrudan para yakar —
bölüm başına ~2 MB yerine ~300 KB, aylık gider 10 kat düşer (500 bölüm/ay'da
~$1 yerine ~$0,15).

`script` ve `stylesheet` ENGELLENMEZ ve engellenmemeli: Cloudflare challenge'ı
JavaScript ile çözülüyor, script kesilirse sayfa hiç açılmaz.

Manga yolu etkilenmez: `manga_fetch.py` kendi `page.goto`'sunu kullanır,
`_extract_html`'den geçmez — orada sayfa görselleri asıl içeriktir.

Ağa çıkmaz — route nesnesi sahtelenir.
"""
from core import fetch


class _SahteIstek:
    def __init__(self, tur):
        self.resource_type = tur


class _SahteRoute:
    def __init__(self, tur):
        self.request = _SahteIstek(tur)
        self.iptal = False
        self.devam = False

    def abort(self):
        self.iptal = True

    def continue_(self):
        self.devam = True


def test_agir_kaynaklar_iptal_edilir():
    for tur in ("image", "media", "font"):
        r = _SahteRoute(tur)
        fetch._kaynak_engelle(r)
        assert r.iptal and not r.devam, f"{tur} engellenmeliydi"


def test_cloudflare_icin_gerekli_turler_gecer():
    """`script` engellenirse CF challenge çözülemez ve çekim TÜMDEN durur."""
    for tur in ("document", "script", "stylesheet", "xhr", "fetch"):
        r = _SahteRoute(tur)
        fetch._kaynak_engelle(r)
        assert r.devam and not r.iptal, f"{tur} geçmeliydi"


def test_bilinmeyen_tur_gecer():
    """Beyaz liste değil KARA liste: tanımadığımız bir tür sayfayı bozmasın."""
    r = _SahteRoute("websocket")
    fetch._kaynak_engelle(r)
    assert r.devam


def test_script_kara_listede_DEGIL():
    """Tel tuzağı: biri 'daha çok tasarruf' diye script eklerse CF kırılır."""
    assert "script" not in fetch.ENGELLENEN_KAYNAKLAR
    assert "stylesheet" not in fetch.ENGELLENEN_KAYNAKLAR
    assert "document" not in fetch.ENGELLENEN_KAYNAKLAR
