/* Künye yardımcıları (DOM'suz, node testli): süre biçimi ve okunur model adı. */
export function sureYaz(sn) {
  const t = Math.max(0, Math.round(Number(sn) || 0));
  if (t < 60) return `${t} sn`;
  const sa = Math.floor(t / 3600), dk = Math.floor((t % 3600) / 60), kalan = t % 60;
  if (sa) return `${sa} sa ${dk} dk`;
  return kalan ? `${dk} dk ${kalan} sn` : `${dk} dk`;
}

// "vertex/gemini-4-argon" -> "4 Argon (ücretli)", "gemini-3.6-flash" -> "3.6 Flash".
export function modelAdi(ham) {
  const ad = String(ham || "").trim();
  const ucretli = /^(vertex|claude)\//.test(ad) || ad.startsWith("claude-");
  const kisa = ad
    .replace(/^[a-z0-9]+[:/]/, "")
    .replace(/^gemini-/, "")
    .split("-")
    .map((p) => (p ? p[0].toUpperCase() + p.slice(1) : p))
    .join(" ");
  return ucretli ? `${kisa} (ücretli)` : kisa;
}

export function modelAdlari(ham) {
  return [...new Set(String(ham).split(" + ").map(modelAdi))].join(" + ");
}
