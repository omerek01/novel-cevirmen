import assert from "node:assert/strict";
import { test } from "node:test";

import { defterNotu } from "../../app/web/js/defter-anahtar-yardimci.js";

test("kaynak ayar olduğunda düğmeyi gösterir", () => {
  const not = defterNotu({ kaynak: "ayar", model: "vertex/gemini-4-argon" });
  assert.match(not, /düğmeyle ayarlandı/);
  assert.match(not, /vertex\/gemini-4-argon/);
});

test("kaynak ortam olduğunda ortam değişkenini ADIYLA söyler", () => {
  // Okur "düğmeye dokunmadım ama açık" durumunu buradan anlıyor.
  assert.match(defterNotu({ kaynak: "ortam", model: "x" }), /KARAKTER_DEFTERI/);
});

test("model bilinmiyorsa not yine de anlamlı kalır", () => {
  const not = defterNotu({ kaynak: "ortam" });
  assert.match(not, /KARAKTER_DEFTERI/);
  assert.doesNotMatch(not, /·/);
});

test("alansız çağrı patlamaz", () => {
  assert.equal(typeof defterNotu(), "string");
});
