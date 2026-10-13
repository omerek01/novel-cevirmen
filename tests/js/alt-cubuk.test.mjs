import { test } from "node:test";
import assert from "node:assert/strict";
import { sonrakiHal, kalanDakika } from "../../app/web/js/alt-cubuk.js";

test("hap açar; kapat ve aşağı kaydırma kapatır; yukarı kaydırma kapalıyı açmaz", () => {
  assert.equal(sonrakiHal("kapali", "hap"), "acik");
  assert.equal(sonrakiHal("acik", "kapat"), "kapali");
  assert.equal(sonrakiHal("acik", "asagi-kaydir"), "kapali");
  assert.equal(sonrakiHal("kapali", "yukari-kaydir"), "kapali");
  assert.equal(sonrakiHal("acik", "yukari-kaydir"), "acik");
});

test("bilinmeyen olay hâli değiştirmez", () => {
  assert.equal(sonrakiHal("acik", "baska"), "acik");
});

test("kalan dakika en az 1, sözcük/230 ölçeğinde", () => {
  assert.equal(kalanDakika(0.99, 100), 1);
  assert.equal(kalanDakika(0.5, 2300), 5);
  assert.equal(kalanDakika(0, 0), 1);
});
