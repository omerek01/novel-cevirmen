/* Kitap ekle: URL / metin yapıştır / dosya (EPUB, PDF, manga). */

import { navigate } from "./gezinme.js";
import { fetchBooks } from "./kutuphane.js";
import { el, markSegment } from "./temel.js";

/* ---------- kitap ekle ---------- */
/* Kitap Ekle: URL · METİN sekmeleri (D-B4/5/8v2). Paste taslağı localStorage'da
   yaşar — modal kapansa da kaybolmaz; başarılı gönderimde temizlenir. */
export const LS_PASTE_DRAFT = "novellink:pasteDraft";
export let addTab = "url";

export function setAddTab(tab) {
  addTab = tab;
  markSegment("addtab", tab, "data-add-tab");
  el("addTabUrl").hidden = tab !== "url";
  el("addTabPaste").hidden = tab !== "paste";
  el("addTabDosya").hidden = tab !== "dosya";
  el("addConfirm").textContent = tab === "dosya" ? "Yükle ve Oku" : "Ekle ve Oku";
}

// EPUB/PDF dosyasını içe aktar: ham gövde + XHR (yükleme yüzdesi). Başarıda ilk bölüme
// gider (reader sayfayı/bölümü OKUDUKÇA çevirir: PDF sayfa görseli, EPUB yerinde HTML).
// İçe aktarım ÇEVİRMEZ, yalnız sahneler → kota tek dosyayla tükenmez.
export function uploadFile() {
  const f = el("fileInput").files[0] || null;
  if (!f) return el("fileInput").focus();
  const isPdf = /\.pdf$/i.test(f.name);
  const isEpub = /\.epub$/i.test(f.name);
  const isManga = /\.(cbz|zip|jpe?g|png|webp)$/i.test(f.name);
  if (!isPdf && !isEpub && !isManga)
    return alert("Yalnız EPUB, PDF veya manga (CBZ/ZIP/görsel) dosyası seçilebilir.");
  if (f.size > 50 * 1024 * 1024) return alert("Dosya 50MB sınırını aşıyor.");
  const path = isPdf ? "/api/import/pdf" : isEpub ? "/api/import/epub" : "/api/import/manga";
  const endpoint = path + `?filename=${encodeURIComponent(f.name)}`;

  const prog = el("uploadProgress");
  const bar = prog.querySelector(".upload-bar span");
  const status = el("uploadStatus");
  const btn = el("addConfirm");
  prog.hidden = false;
  bar.style.width = "0%";
  status.textContent = "Yükleniyor…";
  btn.disabled = true;

  const xhr = new XMLHttpRequest();
  xhr.open("POST", endpoint);
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) bar.style.width = Math.round((e.loaded / e.total) * 100) + "%";
  };
  xhr.upload.onload = () => {
    bar.style.width = "100%";
    status.textContent = "İşleniyor… (bölümler ayıklanıyor)";
  };
  xhr.onload = () => {
    btn.disabled = false;
    if (xhr.status >= 200 && xhr.status < 300) {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        status.textContent = "Geçersiz sunucu yanıtı.";
        return;
      }
      status.textContent = `${data.chapter_count} bölüm eklendi.`;
      el("fileInput").value = "";
      closeAddModal();
      navigate({ view: "reader", url: data.first_url });
    } else {
      let msg = `Hata (${xhr.status})`;
      try {
        msg = JSON.parse(xhr.responseText).detail || msg;
      } catch {}
      status.textContent = "Yüklenemedi: " + msg;
    }
  };
  xhr.onerror = () => {
    btn.disabled = false;
    status.textContent = "Yüklenemedi: ağ hatası.";
  };
  xhr.send(f);
}

export function savePasteDraft() {
  try {
    localStorage.setItem(LS_PASTE_DRAFT, JSON.stringify({
      book: el("pasteBookTitle").value,
      title: el("pasteChapterTitle").value,
      no: el("pasteChapterNo").value,
      text: el("pasteText").value,
    }));
  } catch {}
}

export function restorePasteDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(LS_PASTE_DRAFT)) || {};
    el("pasteBookTitle").value = d.book || "";
    el("pasteChapterTitle").value = d.title || "";
    el("pasteChapterNo").value = d.no || "";
    el("pasteText").value = d.text || "";
  } catch {}
}

export async function fillPasteBookSelect() {
  const sel = el("pasteBookSelect");
  while (sel.options.length > 1) sel.remove(1);
  const books = (await fetchBooks()) || [];
  for (const b of books) {
    if (!b.slug.startsWith("paste-")) continue; // yalnız içe aktarılan kitaplara eklenebilir
    const opt = document.createElement("option");
    opt.value = b.slug;
    opt.textContent = b.title || b.slug;
    sel.appendChild(opt);
  }
}

export async function openAddModal() {
  el("addUrlInput").value = "";
  restorePasteDraft();
  // Dosya sekmesini sıfırla (önceki hata/ilerleme kalmasın).
  el("fileInput").value = "";
  el("uploadProgress").hidden = true;
  el("uploadStatus").textContent = "";
  setAddTab(addTab);
  el("addModal").hidden = false;
  fillPasteBookSelect();
  if (addTab === "url") el("addUrlInput").focus();
}
export function closeAddModal() {
  savePasteDraft(); // taslak kaybolmasın
  el("addModal").hidden = true;
}

export async function submitPaste() {
  const btn = el("addConfirm");
  const text = el("pasteText").value.trim();
  const title = el("pasteChapterTitle").value.trim();
  if (!text) {
    el("pasteText").focus();
    return;
  }
  const slug = el("pasteBookSelect").value || null;
  const no = parseInt(el("pasteChapterNo").value, 10);
  btn.disabled = true;
  try {
    const res = await fetch("/api/import/paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        text,
        book_title: el("pasteBookTitle").value.trim() || null,
        slug,
        chapter_no: Number.isFinite(no) && no > 0 ? no : null,
      }),
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    try {
      localStorage.removeItem(LS_PASTE_DRAFT);
    } catch {}
    ["pasteBookTitle", "pasteChapterTitle", "pasteChapterNo", "pasteText"].forEach(
      (id) => (el(id).value = "")
    );
    el("addModal").hidden = true;
    // Kitap görünümüne git: koşan paste-import işi ilerleme ekranını kendisi açar.
    navigate({ view: "book", slug: data.slug });
  } catch {
    alert("İçe aktarma başarısız — sunucuya ulaşılamadı veya metin reddedildi.");
  } finally {
    btn.disabled = false;
  }
}
// Manga siteleri (URL bölüm linki → siteden sayfa görselleri çekip Gemini-vision ile
// çevir). Roman siteleri metin akışına gider; manga siteleri resim akışına.
export function isMangaUrl(u) {
  return /asurascans?\.com|asuracomic\.net|reaperscans|flamecomics|mangadex\.org/i.test(u || "");
}

export async function importMangaUrl(url) {
  const btn = el("addConfirm");
  const orig = btn.innerHTML;
  btn.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span> Manga çekiliyor…`;
  btn.disabled = true;
  try {
    const res = await fetch("/api/import/manga-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      throw new Error(e.detail?.message || e.detail || `Hata (${res.status})`);
    }
    const data = await res.json();
    closeAddModal();
    navigate({ view: "reader", url: data.first_url });
  } catch (err) {
    alert("Manga çekilemedi: " + (err.message || err));
  } finally {
    btn.innerHTML = orig;
    btn.disabled = false;
  }
}

/* Olay kayıtları: modül yüklenirken DEĞİL, giriş noktası (`app.js`) sırayla
   çağırınca kurulur — döngüsel içe aktarmalarda yarım değerlendirilmiş bir
   modülün fonksiyonuna erken dokunulmasın. */
export function kur() {

  /* ---------- kitap ekle olayları ---------- */
  el("addCancel").addEventListener("click", closeAddModal);
  document.querySelectorAll("[data-add-tab]").forEach((b) =>
    b.addEventListener("click", () => setAddTab(b.getAttribute("data-add-tab")))
  );
  ["pasteBookTitle", "pasteChapterTitle", "pasteChapterNo", "pasteText"].forEach((id) =>
    el(id).addEventListener("input", savePasteDraft)
  );
  el("pasteBookSelect").addEventListener("change", () => {
    // Mevcut kitaba eklerken kitap adı alanı anlamsız — gizle.
    el("pasteBookTitle").hidden = !!el("pasteBookSelect").value;
  });

  el("addConfirm").addEventListener("click", () => {
    if (addTab === "paste") {
      submitPaste();
      return;
    }
    if (addTab === "dosya") {
      uploadFile();
      return;
    }
    const url = el("addUrlInput").value.trim();
    if (url) {
      if (isMangaUrl(url)) return importMangaUrl(url); // manga sitesi → sayfaları çek+çevir
      closeAddModal();
      navigate({ view: "reader", url });
    }
  });
  el("addUrlInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") el("addConfirm").click();
  });
  el("addModal").addEventListener("click", (e) => {
    if (e.target === el("addModal")) closeAddModal();
  });
}
