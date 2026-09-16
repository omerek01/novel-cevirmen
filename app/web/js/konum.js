/* Yerel okuma konumu: bölüm-içi kaydırma oranı ve kitap başına son okunan bölüm. */

import { durum } from "./durum.js";

export const LS_SCROLL = "novellink:scroll";
export const LS_LASTREAD = "novellink:lastread";
export const SCROLL_MAX = 500; // localStorage'da tutulan en fazla bölüm konumu (budama)

/* ---------- kaydırma konumu (oran) ---------- */
export function loadScrollMap() {
  try {
    return JSON.parse(localStorage.getItem(LS_SCROLL)) || {};
  } catch {
    return {};
  }
}
// Saf: harita SCROLL_MAX'ı aşarsa en eski eklenenleri at (test edilebilir).
export function pruneScrollPositions(map, max) {
  const keys = Object.keys(map);
  if (keys.length <= max) return map;
  for (const k of keys.slice(0, keys.length - max)) delete map[k];
  return map;
}
export function saveScrollLocal(url, ratio) {
  const map = loadScrollMap();
  delete map[url]; // yeniden ekle → ekleme sırasında en sona gelsin (LRU benzeri)
  map[url] = ratio;
  pruneScrollPositions(map, SCROLL_MAX);
  try {
    localStorage.setItem(LS_SCROLL, JSON.stringify(map));
  } catch {}
}
export function getScrollLocal(url) {
  return loadScrollMap()[url] || 0;
}

/* ---------- son okunan bölüm (kitap başına; çevrimdışı resume için) ----------
   Sunucu "kaldığın yer" işaretini (books.current_url) yalnız çevrimiçiyken günceller.
   Çevrimdışı okurken bölüm SW önbelleğinden gelir, istek sunucuya ulaşmaz → işaret
   ilerlemez. Bu yerel kayıt her bölüm render'ında ilerler; resume iki kaynaktan en
   TAZE olanı seçer, böylece çevrimdışı okunan son bölümden devam edilir. */
export function loadLastReadMap() {
  try {
    return JSON.parse(localStorage.getItem(LS_LASTREAD)) || {};
  } catch {
    return {};
  }
}
export function saveLastRead(slug, url) {
  if (!slug || !url) return;
  const map = loadLastReadMap();
  // chapter_no/title: kütüphane sırtı "BÖL. N" etiketini çevrimdışı okumaya göre
  // gösterebilmek için (sunucu chapter_no'su yalnız çevrimiçi güncellenir).
  map[slug] = { url, ts: Date.now(), chapter_no: durum.currentChapterNo, title: durum.currentChapterTitle };
  try {
    localStorage.setItem(LS_LASTREAD, JSON.stringify(map));
  } catch {}
}
export function getLastRead(slug) {
  return loadLastReadMap()[slug] || null;
}
// Resume hedefi: sunucu konumu (çok-cihaz paylaşımı) ile yerel son-okuma (çevrimdışı)
// arasından en TAZE olanı. Yerel ts sunucunun updated_at'inden yeniyse (çevrimdışı
// okuma) yerel kazanır; değilse sunucu (başka cihazda daha yeni okunmuş olabilir).
export function resolveResume(book, slug) {
  let url = (book && book.current_url) || null;
  let ratio = (book && book.current_ratio) || 0;
  let chapterNo = (book && book.chapter_no) || null;
  const local = getLastRead(slug);
  const serverTsMs = ((book && book.updated_at) || 0) * 1000;
  if (local && local.url && local.ts >= serverTsMs) {
    url = local.url;
    ratio = getScrollLocal(url);
    if (local.chapter_no != null) chapterNo = local.chapter_no; // eski kayıtta yoksa sunucu değeri kalır
  }
  return { url, ratio, chapterNo };
}
