import test from "node:test";
import assert from "node:assert/strict";

import { escapeHtml } from "../../app/web/js/temel.js";

test("escapeHtml HTML özel karakterlerini kaçırır", () => {
  assert.equal(escapeHtml("<b>a & b</b>"), "&lt;b&gt;a &amp; b&lt;/b&gt;");
});

test("escapeHtml tırnakları da kaçırır: nitelik içinde güvenli", () => {
  // Kapak adresi bir sitenin og:image değerinden gelir ve src="..." içine basılır.
  const kotu = 'x" onerror="alert(1)';
  const cikti = escapeHtml(kotu);
  assert.ok(!cikti.includes('"'), cikti);
  assert.equal(escapeHtml("it's"), "it&#39;s");
});

test("escapeHtml boş ve sayısal değerleri dizeye çevirir", () => {
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(undefined), "");
  assert.equal(escapeHtml(42), "42");
});
