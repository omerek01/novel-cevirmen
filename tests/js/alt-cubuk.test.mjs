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

test("kalan dakika kişisel harf/dk ile, en az 1", () => {
  assert.equal(kalanDakika(0.5, 6000, 1500), 2);
  assert.equal(kalanDakika(0, 9000, 3000), 3);
  assert.equal(kalanDakika(0.99, 100, 1500), 1);
  assert.equal(kalanDakika(0, 0, 1500), 1);
});

test("hız bilinmiyorsa 230 sözcük/dk (1495 harf/dk) varsayılır", () => {
  assert.equal(kalanDakika(0, 14950), 10);
  assert.equal(kalanDakika(0.5, 14950, 0), 5);
});
