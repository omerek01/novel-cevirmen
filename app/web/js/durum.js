/* Modüller arası PAYLAŞILAN değişken durum ve görünüm düğümleri.

   Klasik tek dosyada bunlar üst düzey `let` idi. ES modülünde içe aktarılan bir
   bağlama ATAMA yapılamaz; birden çok modülün yazdığı değerler bu yüzden tek bir
   nesnenin alanlarıdır. Yalnız GERÇEKTEN paylaşılanlar burada durur — modül içi
   durum kendi modülünde kalır. */

import { el } from "./temel.js";

export const views = {
  library: el("libraryView"),
  book: el("bookView"),
  glossary: el("glossaryView"),
  reader: el("readerView"),
  apidurum: el("apiDurumView"),
};

export const durum = {
  currentUrl: null,
  currentChapterNo: null, // açık bölümün numarası (yerel "son okunan" kaydı + kütüphane etiketi)
  currentChapterTitle: null,
  currentBookSlug: null,
  currentBook: null, // {current_url, current_ratio, ...} — resume için
  currentChapters: [], // açık kitabın tam bölüm listesi (prev türetme + arama)
};
