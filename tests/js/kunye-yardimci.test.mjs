import { test } from "node:test";
import assert from "node:assert/strict";
import { modelAdi, modelAdlari, sureYaz } from "../../app/web/js/kunye-yardimci.js";

test("süre saniye, dakika ve saat olarak okunur yazılır", () => {
  assert.equal(sureYaz(0), "0 sn");
  assert.equal(sureYaz(42.4), "42 sn");
  assert.equal(sureYaz(60), "1 dk");
  assert.equal(sureYaz(383), "6 dk 23 sn");
  assert.equal(sureYaz(3780), "1 sa 3 dk");
  assert.equal(sureYaz(null), "0 sn");
});

test("ham model kimliği okunur ada döner, ücretli olan işaretlenir", () => {
  assert.equal(modelAdi("vertex/gemini-4-argon"), "4 Argon (ücretli)");
  assert.equal(modelAdi("gemini-3.6-flash"), "3.6 Flash");
  assert.equal(modelAdi("mistral:mistral-medium-latest"), "Mistral Medium Latest");
});

test("birden çok model birleşik yazılır, tekrar eden ad bir kez geçer", () => {
  assert.equal(modelAdlari("gemini-3.6-flash + vertex/gemini-4-argon"),
    "3.6 Flash + 4 Argon (ücretli)");
  assert.equal(modelAdlari("gemini-3.6-flash + gemini-3.6-flash"), "3.6 Flash");
});
