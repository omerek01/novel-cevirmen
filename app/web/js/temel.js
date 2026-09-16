/* Ortak küçük yardımcılar: DOM erişimi, kaçış, ikonlar, gün, segment işareti.
   Hiçbir modülü içe aktarmaz — bağımlılık grafiğinin yaprağıdır. */

// SVG ikonlar (emoji yerine — temiz çizgi ikon, currentColor). skill kuralı: emoji ikon yok.
export const SVG = (p, sz = 22) =>
  `<svg viewBox="0 0 24 24" width="${sz}" height="${sz}" fill="none" stroke="currentColor" ` +
  `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
export const ICONS = {
  moon: SVG('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
  sun: SVG(
    '<circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6' +
      'M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/>'
  ),
  search: SVG('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.2-4.2"/>'),
  sliders: SVG(
    '<path d="M4 8h11M19 8h1M4 16h4M12 16h8"/><circle cx="16" cy="8" r="2"/><circle cx="9" cy="16" r="2"/>'
  ),
  download: SVG('<path d="M12 3v11M8 11l4 4 4-4M5 20h14"/>', 18),
  // Alt gezinme "Kütüphane" sekmesi: rafta duran iki kitap sırtı + eğik üçüncü —
  // uygulamanın kendi raf metaforunu tekrarlar.
  shelf: SVG('<path d="M4 5h4v14H4zM10 5h4v14h-4zM16.6 5.8l3.4.9-3.1 12.5-3.4-.9z"/>', 18),
};
export const THEME_ICON = { light: ICONS.moon, sepia: ICONS.sun, dark: ICONS.sun };

export const el = (id) => document.getElementById(id);

// İstemcinin YEREL günü (YYYY-MM-DD) — "bugün" sayacı gece yarısı UTC'ye kaymaz.
export function localDay() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
export function markSegment(group, value, attr) {
  for (const b of document.querySelectorAll(`[${attr}]`)) {
    b.setAttribute("aria-pressed", b.getAttribute(attr) === value ? "true" : "false");
  }
}

export function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

export function isSyntheticSlug(slug) {
  return (
    !!slug &&
    (slug.startsWith("paste-") ||
      slug.startsWith("pdf-") ||
      slug.startsWith("manga-") ||
      slug.startsWith("epub-"))
  );
}
