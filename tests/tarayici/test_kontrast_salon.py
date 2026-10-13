"""Küçük bilgi metni üç temada da yüzeyden ayırt edilebilir."""
import pytest
from playwright.sync_api import expect

import tohum


@pytest.mark.parametrize("tema", ["light", "sepia", "dark"])
def test_kitap_islem_aciklamasi_kontrasti_en_az_45(sayfa, tema):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    sayfa.evaluate("t => document.documentElement.dataset.theme = t", tema)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    expect(sayfa.locator("#bookView")).to_be_visible()
    oran = sayfa.locator("#bookView .book-action small").first.evaluate(r"""e => {
      const parlaklik = renk => {
        const c = renk.match(/\d+(?:\.\d+)?/g).slice(0, 3).map(x => {
          const v = Number(x) / 255;
          return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
        });
        return .2126 * c[0] + .7152 * c[1] + .0722 * c[2];
      };
      const a = parlaklik(getComputedStyle(e).color);
      const b = parlaklik(getComputedStyle(e.closest('button')).backgroundColor);
      return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    }""")
    assert oran >= 4.5, (tema, oran)
