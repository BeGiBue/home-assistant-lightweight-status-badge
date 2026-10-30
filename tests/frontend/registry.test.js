// Registry-sichere Registrierung: Lädt eine andere Karte oder ein Add-on den Polyfill
// @webcomponents/scoped-custom-element-registry, ersetzt er window.customElements durch eine
// neue, leere Registry. Das Modul muss sich dort anmelden, auch lange nach dem Start.
// (Mit dem echten Polyfill im Browser: tests/browser/registry.test.js.)
import test, { after, afterEach, mock } from "node:test";
import assert from "node:assert/strict";

const MODULE = "../../custom_components/lightweight_status_badge/www/lightweight-status-badge.js";
const NAMES = ["lightweight-status-badge", "lightweight-status-alerts-card", "lightweight-status-badge-editor"];
const saved = {
  HTMLElement: globalThis.HTMLElement,
  customElements: globalThis.customElements,
  window: globalThis.window,
  document: globalThis.document,
};

function fakeRegistry() {
  const defined = new Map();
  return {
    defined,
    get: (name) => defined.get(name),
    define: (name, value) => {
      defined.set(name, value);
    },
  };
}

const hasAll = (registry) => NAMES.every((name) => registry.defined.has(name));
const useRegistry = (registry) => {
  globalThis.customElements = registry;
};
let loads = 0;
// Jeder Aufruf lädt eine frische Modulinstanz (eigene Timer und Ereignis-Handler).
async function load(registry) {
  globalThis.HTMLElement = class {};
  globalThis.window = new EventTarget();
  globalThis.document = new EventTarget();
  useRegistry(registry);
  mock.timers.reset(); // eine frühere Instanz im selben Test verliert ihre Timer
  mock.timers.enable({ apis: ["setTimeout"] });
  await import(`${MODULE}?registry-${++loads}`);
}
const run = (milliseconds) => {
  for (let elapsed = 0; elapsed < milliseconds; elapsed += 100) mock.timers.tick(Math.min(100, milliseconds - elapsed));
};

afterEach(() => mock.timers.reset());
after(() => {
  Object.assign(globalThis, saved);
});

test("registriert Badge, Karte und Editor sofort in der aktuellen Registry", async () => {
  const registry = fakeRegistry();
  await load(registry);
  assert.equal(hasAll(registry), true);
});

test("meldet sich in der neuen Registry an, wenn sie kurz nach dem Start ausgetauscht wird", async () => {
  const oldRegistry = fakeRegistry();
  await load(oldRegistry);
  const next = fakeRegistry();
  useRegistry(next);
  assert.equal(next.defined.size, 0);
  run(600);
  assert.equal(hasAll(next), true);
  for (const name of NAMES) assert.equal(next.defined.get(name), oldRegistry.defined.get(name));
});

test("repariert auch einen späten Austausch, lange nach dem Start (höchstens 10 s)", async () => {
  await load(fakeRegistry());
  run(10 * 60 * 1000); // zehn Minuten Dauerbetrieb
  const late = fakeRegistry();
  useRegistry(late);
  run(9_999);
  assert.equal(hasAll(late), true);
});

test("repariert jeden weiteren Austausch erneut", async () => {
  await load(fakeRegistry());
  for (let round = 0; round < 3; round++) {
    const next = fakeRegistry();
    useRegistry(next);
    run(10_000);
    assert.equal(hasAll(next), true);
  }
});

test("meldet sofort an bei location-changed und Sichtbarkeitswechsel", async () => {
  await load(fakeRegistry());
  run(60_000);
  const first = fakeRegistry();
  useRegistry(first);
  window.dispatchEvent(new Event("location-changed"));
  assert.equal(hasAll(first), true);
  const second = fakeRegistry();
  useRegistry(second);
  document.dispatchEvent(new Event("visibilitychange"));
  assert.equal(hasAll(second), true);
});

test("lässt fremde Einträge in der neuen Registry unangetastet", async () => {
  await load(fakeRegistry());
  const late = fakeRegistry();
  const foreign = class {};
  late.define("lightweight-status-badge", foreign);
  useRegistry(late);
  run(10_000);
  assert.equal(late.defined.get("lightweight-status-badge"), foreign);
  assert.equal(late.defined.has("lightweight-status-alerts-card"), true);
  assert.equal(late.defined.has("lightweight-status-badge-editor"), true);
});

test("definiert nichts neu, solange die Registry unverändert ist", async () => {
  const registry = fakeRegistry();
  await load(registry);
  let defines = 0;
  const define = registry.define;
  registry.define = (...args) => {
    defines++;
    return define(...args);
  };
  run(5 * 60 * 1000);
  assert.equal(defines, 0);
});

test("verträgt eine Registry ohne get und eine, die define ablehnt", async () => {
  await load({ define() {} });
  run(30_000);
  await load({
    get: () => undefined,
    define() {
      throw new Error("already used");
    },
  });
  run(30_000);
});

test("belastet nicht: im Dauerbetrieb ein Durchlauf alle 10 s", async () => {
  const registry = fakeRegistry();
  await load(registry);
  run(60_000);
  let gets = 0;
  const get = registry.get;
  registry.get = (name) => {
    gets++;
    return get(name);
  };
  run(60_000);
  assert.equal(gets, 6 * NAMES.length); // 6 Durchläufe in 60 s, je drei Namen
});
