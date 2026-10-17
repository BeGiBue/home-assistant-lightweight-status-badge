import test from "node:test";
import assert from "node:assert/strict";
globalThis.HTMLElement = class {};
globalThis.customElements = { define() {} };
globalThis.window = {};
const { AlertStore, summary, decodeText, language } =
  await import("../../frontend/lightweight-status-badge.js");
const tick = () => new Promise((resolve) => setImmediate(resolve));
const alert = (id, acknowledged = false, severity = 2) => ({
  rule_id: id,
  occurrence: `${id}-occurrence`,
  acknowledged,
  severity,
});
const page = (
  alerts,
  revision = 1,
  next_offset = null,
  total = alerts.length,
) => ({ alerts, revision, next_offset, total });
class Connection extends EventTarget {
  constructor(handler = () => page([])) {
    super();
    this.handler = handler;
    this.calls = [];
    this.subscriptions = 0;
    this.unsubscribed = 0;
  }
  async subscribeMessage(callback, message) {
    this.callback = callback;
    this.subscriptions++;
    assert.match(message.type, /subscribe$/);
    callback({ loaded: true });
    return () => {
      this.unsubscribed++;
    };
  }
  async sendMessagePromise(message) {
    this.calls.push(message);
    return this.handler(message);
  }
  event(value = { loaded: true }) {
    this.callback(value);
  }
}
test("unread summary, locale fallback and single safe entity decoding", () => {
  assert.deepEqual(
    summary([alert("a", true, 3), alert("b", false, 1), alert("c", false, 2)]),
    { count: 2, severity: 2 },
  );
  assert.deepEqual(summary([]), { count: 0, severity: 0 });
  assert.equal(language({ locale: { language: "de-DE" } }), "de");
  assert.equal(language({ language: "fr" }), "en");
  assert.equal(decodeText("&lt;img&gt;&amp;lt;&#x27;&quot;"), "<img>&lt;'\"");
});
test("shared store consumers subscribe once, idle hass changes do not read, final detach cleans up", async () => {
  const c = new Connection(() => page([alert("a")])),
    store = new AlertStore(c, "de");
  const off1 = store.listen(() => {}),
    off2 = store.listen(() => {});
  await tick();
  assert.equal(c.subscriptions, 1);
  assert.equal(c.calls.length, 1);
  assert.equal(c.calls[0].language, "de");
  off1();
  assert.equal(c.unsubscribed, 0);
  off2();
  assert.equal(c.unsubscribed, 1);
  assert.equal(store.alerts.length, 0);
});
test("all pages include acknowledged records; inconsistent revision restarts at zero", async () => {
  const offsets = [];
  let first = true;
  const c = new Connection((m) => {
    offsets.push(m.offset);
    if (m.offset === 0) return page([alert("a")], first ? 1 : 2, 1, 2);
    first = false;
    return page([alert("b", true, 3)], 2, null, 2);
  });
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  assert.deepEqual(offsets, [0, 1, 0, 1]);
  assert.equal(store.alerts.length, 2);
  assert.equal(summary(store.alerts).severity, 2);
  off();
});
test("new invalidation discards in-flight snapshot and coalesces bursts", async () => {
  let resolve;
  const c = new Connection(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  c.event();
  c.event();
  resolve(page([alert("stale")]));
  await tick();
  assert.equal(c.calls.length, 2);
  resolve(page([alert("fresh")]));
  await tick();
  assert.equal(store.alerts[0].rule_id, "fresh");
  off();
});
test("disconnect clears data; ready refetches; unloaded and reloaded revisions may reset", async () => {
  const c = new Connection(() => page([alert("live")], 0)),
    store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  c.dispatchEvent(new Event("disconnected"));
  assert.equal(store.status, "offline");
  assert.equal(store.alerts.length, 0);
  c.dispatchEvent(new Event("ready"));
  await tick();
  assert.equal(store.status, "ready");
  c.event({ loaded: false });
  assert.equal(store.status, "unloaded");
  assert.equal(store.alerts.length, 0);
  c.event();
  await tick();
  assert.equal(store.alerts[0].rule_id, "live");
  off();
});
test("duplicate actions suppressed, occurrence sent, no optimistic mutation, revoke supported", async () => {
  let resolve;
  const a = alert("a");
  const c = new Connection((m) =>
    m.type.endsWith("/alerts") ? page([a]) : new Promise((r) => (resolve = r)),
  );
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  const action = store.acknowledge(a);
  store.acknowledge(a);
  assert.equal(a.acknowledged, false);
  assert.equal(
    c.calls.filter((m) => m.type.endsWith("/acknowledge")).length,
    1,
  );
  assert.equal(c.calls.at(-1).occurrence, "a-occurrence");
  resolve();
  await action;
  a.acknowledged = true;
  const undo = store.acknowledge(a);
  assert.equal(c.calls.at(-1).acknowledged, false);
  resolve();
  await undo;
  off();
});
for (const [code, expected] of [
  ["unauthorized", "denied"],
  ["invalid_alert", "stale"],
  ["unknown", "failed"],
])
  test(`action error ${code} refreshes authoritative data`, async () => {
    const a = alert("a"),
      c = new Connection((m) => {
        if (m.type.endsWith("/acknowledge")) throw { code };
        return page([a]);
      });
    const store = new AlertStore(c, "en"),
      off = store.listen(() => {});
    await tick();
    await store.acknowledge(a);
    assert.equal(store.actionError, expected);
    assert.equal(store.pending.size, 0);
    assert.equal(c.calls.length, 3);
    off();
  });
test("read-only actions disabled and API errors recover on invalidation", async () => {
  let fail = true;
  const c = new Connection(() => {
    if (fail) throw { code: "not_loaded" };
    return page([{ ...alert("a"), can_acknowledge: false }]);
  });
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  assert.equal(store.status, "unloaded");
  fail = false;
  c.event();
  await tick();
  await store.acknowledge(store.alerts[0]);
  assert.equal(c.calls.length, 2);
  off();
});
test("malformed pagination cannot loop or publish partial data", async () => {
  const c = new Connection(() => page([alert("a")], 1, 0, 2)),
    store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  assert.equal(store.status, "error");
  assert.equal(store.alerts.length, 0);
  assert.equal(c.calls.length, 1);
  off();
});
test("continuous revision changes bounded and never present mixed snapshots", async () => {
  let revision = 0;
  const c = new Connection((m) =>
    page([alert("a")], ++revision, m.offset === 0 ? 1 : null, 2),
  );
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  assert.equal(store.status, "error");
  assert.equal(c.calls.length, 8);
  off();
});
test("late subscription completion after remount unsubscribes old lifecycle", async () => {
  const resolves = [];
  const c = new Connection();
  c.subscribeMessage = () => new Promise((r) => resolves.push(r));
  const store = new AlertStore(c, "en");
  let old = 0,
    fresh = 0;
  const off = store.listen(() => {});
  off();
  const off2 = store.listen(() => {});
  resolves[0](() => old++);
  await tick();
  resolves[1](() => fresh++);
  await tick();
  assert.equal(old, 1);
  assert.equal(fresh, 0);
  off2();
  assert.equal(fresh, 1);
});
test("detach while reading never publishes stale records", async () => {
  let resolve;
  const c = new Connection(() => new Promise((r) => (resolve = r)));
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  off();
  resolve(page([alert("a")]));
  await tick();
  assert.equal(store.alerts.length, 0);
  assert.equal(store.status, "loading");
});

test("failed subscription can retry without polling or leaking listeners", async () => {
  const c = new Connection(() => page([]));
  const subscribe = c.subscribeMessage.bind(c);
  let fail = true;
  c.subscribeMessage = async (...args) => {
    if (fail) throw new Error("offline");
    return subscribe(...args);
  };
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  assert.equal(store.status, "error");
  assert.equal(c.calls.length, 0);
  fail = false;
  store.retry();
  await tick();
  assert.equal(store.status, "ready");
  assert.equal(c.subscriptions, 1);
  off();
  assert.equal(c.unsubscribed, 1);
});

test("disconnect during a pending read discards its successful stale response", async () => {
  let resolve;
  const c = new Connection(() => new Promise((r) => (resolve = r)));
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  await tick();
  c.dispatchEvent(new Event("disconnected"));
  resolve(page([alert("stale")]));
  await tick();
  assert.equal(store.status, "offline");
  assert.equal(store.alerts.length, 0);
  off();
});

test("pending HA subscription survives ready without creating another subscription", async () => {
  let resolve,
    subscriptions = 0;
  const c = new Connection();
  c.subscribeMessage = () => {
    subscriptions++;
    return new Promise((r) => (resolve = r));
  };
  const store = new AlertStore(c, "en"),
    off = store.listen(() => {});
  c.dispatchEvent(new Event("ready"));
  assert.equal(subscriptions, 1);
  resolve(() => Promise.reject(new Error("disconnected while unsubscribing")));
  await tick();
  off();
  await tick();
});

test("late action failure cannot contaminate a remounted store", async () => {
  let reject;
  const a = alert("a");
  const c = new Connection((m) => m.type.endsWith("/alerts") ? page([a]) : new Promise((_, r) => { reject = r; }));
  const store = new AlertStore(c, "en");
  const off = store.listen(() => {});
  await tick();
  const action = store.acknowledge(a);
  off();
  const off2 = store.listen(() => {});
  await tick();
  assert.equal(store.pending.size, 0);
  const calls = c.calls.length;
  reject({code: "unauthorized"});
  await action;
  assert.equal(store.actionError, "");
  assert.equal(c.calls.length, calls);
  off2();
});

test("reloading a versioned module does not redefine elements or duplicate pickers", async () => {
  const defined = new Map();
  globalThis.customElements = {
    get: (name) => defined.get(name),
    define: (name, value) => {
      assert.equal(defined.has(name), false);
      defined.set(name, value);
    },
  };
  await import("../../frontend/lightweight-status-badge.js?first-version");
  await import("../../frontend/lightweight-status-badge.js?next-version");
  assert.equal(defined.size, 3);
  assert.equal(window.customBadges.length, 1);
  assert.equal(window.customCards.length, 1);
});
