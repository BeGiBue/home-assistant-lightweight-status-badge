import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
let browser, server, url;
before(async () => {
  server = createServer((req, res) => {
    if (req.url === "/badge.js") {
      res.setHeader("Content-Type", "application/javascript");
      res.end(
        readFileSync(
          "custom_components/lightweight_status_badge/www/lightweight-status-badge.js",
        ),
      );
    } else {
      res.setHeader("Content-Type", "text/html");
      res.end(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><script type="module" src="/badge.js"></script></body></html>',
      );
    }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  url = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
    args: ["--no-sandbox"],
  });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise((r) => server.close(r));
});
async function setup(viewport = { width: 1280, height: 800 }, lang = "en") {
  const page = await browser.newPage({ viewport });
  await page.goto(url);
  await page.waitForFunction(() =>
    customElements.get("lightweight-status-badge"),
  );
  await page.evaluate((lang) => {
    window.xss = 0;
    class Connection extends EventTarget {
      constructor() {
        super();
        this.subscriptions = 0;
        this.unsubscribed = 0;
        this.calls = [];
        this.callbacks = new Set();
        this.revision = 1;
        this.alerts = [
          {
            rule_id: "ups",
            occurrence: "once",
            entity_id: "sensor.ups",
            title: 'UPS &lt;img src=x onerror="window.xss=1"&gt;',
            description: "Battery operation. Check power.",
            recommendation: "Check the mains supply.",
            raw_state: "OB &amp; &lt;script&gt;window.xss=1&lt;/script&gt;",
            severity: 2,
            acknowledged: false,
            can_acknowledge: true,
          },
        ];
      }
      async subscribeMessage(cb) {
        this.subscriptions++;
        this.callbacks.add(cb);
        cb({ loaded: true });
        return () => {
          this.callbacks.delete(cb);
          this.unsubscribed++;
        };
      }
      emit() {
        this.revision++;
        for (const cb of this.callbacks)
          cb({ loaded: true, revision: this.revision });
      }
      async sendMessagePromise(m) {
        this.calls.push(m);
        if (m.type.endsWith("/alerts"))
          return {
            alerts: this.alerts.slice(m.offset, m.offset + 100),
            total: this.alerts.length,
            next_offset:
              m.offset + 100 < this.alerts.length ? m.offset + 100 : null,
            revision: this.revision,
          };
        if (this.failure) throw { code: this.failure };
        const a = this.alerts.find(
          (a) => a.rule_id === m.rule_id && a.occurrence === m.occurrence,
        );
        if (!a) throw { code: "invalid_alert" };
        a.acknowledged = m.acknowledged;
        this.emit();
      }
    }
    window.connection = new Connection();
    window.hass = { connection, locale: { language: lang } };
    for (const type of [
      "lightweight-status-badge",
      "lightweight-status-alerts-card",
    ]) {
      const view = document.createElement(type);
      view.setConfig({ type: `custom:${type}` });
      view.hass = hass;
      if (type === "lightweight-status-badge") {
        const wrapper = document.createElement("div");
        wrapper.id = "hui-badge-fixture";
        view.addEventListener("badge-visibility-changed", () => {
          wrapper.hidden = view.hidden;
          if (!view.connectedWhileHidden && view.hidden) view.remove();
        });
        wrapper.append(view);
        document.body.append(wrapper);
      } else document.body.append(view);
    }
  }, lang);
  await page.waitForFunction(
    () =>
      document.querySelector("lightweight-status-badge").store?.status ===
      "ready",
  );
  return page;
}
const badge = "lightweight-status-badge",
  card = "lightweight-status-alerts-card",
  portal = "lightweight-status-dialog";
test("native custom badge/card discovery and GUI editor emit full configuration", async () => {
  const p = await setup();
  assert.equal(
    await p.evaluate(() => window.customBadges[0].type),
    "lightweight-status-badge",
  );
  assert.equal(
    await p.evaluate(() => window.customCards[0].type),
    "lightweight-status-alerts-card",
  );
  await p.evaluate(() => {
    const editor = customElements
      .get("lightweight-status-badge")
      .getConfigElement();
    editor.hass = { locale: { language: "de" } };
    editor.setConfig({
      type: "custom:lightweight-status-badge",
      visibility: [{ condition: "user", users: ["a"] }],
    });
    editor.addEventListener(
      "config-changed",
      (e) => (window.config = e.detail.config),
    );
    document.body.append(editor);
  });
  await p.getByLabel("Anzeigename").fill("Hausstatus");
  assert.deepEqual(await p.evaluate(() => window.config), {
    type: "custom:lightweight-status-badge",
    name: "Hausstatus",
    visibility: [{ condition: "user", users: ["a"] }],
  });
  await p.close();
});
test("dialog safely renders text, descriptions, technical data; keyboard Escape and focus restoration", async () => {
  const p = await setup();
  await p.locator(`${badge} button`).focus();
  await p.keyboard.press("Enter");
  assert.equal(
    await p.locator(`${portal} dialog`).evaluate((d) => d.open),
    true,
  );
  assert.match(
    await p.locator(`${portal} article`).innerText(),
    /Check the mains supply/,
  );
  assert.match(
    await p.locator(`${portal} article`).innerText(),
    /OB & <script>/,
  );
  assert.equal(
    await p.locator(`${portal} article img, ${portal} article script`).count(),
    0,
  );
  assert.equal(await p.evaluate(() => window.xss), 0);
  await p.keyboard.press("Escape");
  await p.locator(`${portal} dialog`).waitFor({ state: "detached" });
  assert.equal(await p.locator(`${portal} dialog`).count(), 0);
  assert.equal(
    await p
      .locator(`${badge} .trigger`)
      .evaluate((b) => b.getRootNode().activeElement === b),
    true,
  );
  await p.close();
});
test("global ack hides badge with no layout gap; secondary card shows acknowledged and revokes", async () => {
  const p = await setup();
  await p.locator(`${badge} .trigger`).click();
  await p
    .locator(portal)
    .getByRole("button", { name: "Acknowledge globally" })
    .click();
  await p.waitForFunction(
    () =>
      document.querySelector("lightweight-status-badge").store.alerts[0]
        ?.acknowledged,
  );
  assert.equal(await p.locator(`${badge} .trigger`).isVisible(), false);
  assert.equal(
    await p.locator(badge).evaluate((b) => b.getBoundingClientRect().width),
    0,
  );
  assert.equal(
    await p.locator(`${portal} dialog`).evaluate((d) => d.open),
    true,
  );
  await p.keyboard.press("Escape");
  assert.equal(await p.locator(badge).isVisible(), false);
  assert.equal(
    await p.locator("#hui-badge-fixture").evaluate((w) => w.hidden),
    true,
  );
  await p.locator(`${card} .trigger`).click();
  assert.match(
    await p.locator(`${portal} article`).innerText(),
    /Acknowledged/,
  );
  await p
    .locator(portal)
    .getByRole("button", { name: "Undo acknowledgement" })
    .click();
  await p.waitForFunction(
    () => !document.querySelector("lightweight-status-badge").hidden,
  );
  assert.match(await p.locator(`${badge} .trigger`).innerText(), /1 · Warning/);
  assert.equal(await p.evaluate(() => connection.subscriptions), 1);
  await p.close();
});
test("no polling or re-render on hass ticks; disconnect/ready and detach clean up", async () => {
  const p = await setup();
  const before = await p.evaluate(() => connection.calls.length);
  await p.evaluate(() => {
    window.original = document.querySelector(
      "lightweight-status-badge",
    ).trigger.firstChild;
    for (let i = 0; i < 100; i++)
      for (const v of document.querySelectorAll(
        "lightweight-status-badge,lightweight-status-alerts-card",
      ))
        v.hass = { ...hass };
  });
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(await p.evaluate(() => connection.calls.length), before);
  assert.equal(
    await p.evaluate(
      () =>
        document.querySelector("lightweight-status-badge").trigger
          .firstChild === window.original,
    ),
    true,
  );
  await p.evaluate(() => connection.dispatchEvent(new Event("disconnected")));
  assert.match(
    await p.locator(`${badge} .trigger`).innerText(),
    /Connection lost/,
  );
  await p.evaluate(() => connection.dispatchEvent(new Event("ready")));
  await p.waitForFunction(
    () =>
      document.querySelector("lightweight-status-badge").store.status ===
      "ready",
  );
  await p.evaluate(() =>
    document.querySelector("lightweight-status-badge").remove(),
  );
  assert.equal(await p.evaluate(() => connection.unsubscribed), 0);
  await p.evaluate(() =>
    document.querySelector("lightweight-status-alerts-card").remove(),
  );
  assert.equal(await p.evaluate(() => connection.unsubscribed), 1);
  await p.close();
});
test("permissions and stale actions give translated recoverable errors", async () => {
  const p = await setup(undefined, "de");
  await p.locator(`${card} .trigger`).click();
  await p.evaluate(() => {
    connection.failure = "unauthorized";
  });
  await p
    .locator(portal)
    .getByRole("button", { name: "Global quittieren", exact: true })
    .click();
  await p.waitForFunction(
    () =>
      document.querySelector("lightweight-status-alerts-card").store
        .actionError === "denied",
  );
  assert.match(
    await p.locator(`${portal} [role=alert]`).innerText(),
    /Steuerungsberechtigung/,
  );
  await p.evaluate(() => {
    connection.alerts[0].can_acknowledge = false;
    connection.emit();
  });
  await p.waitForFunction(
    () =>
      document
        .querySelector("lightweight-status-dialog")
        .shadowRoot.querySelector("article button").disabled,
  );
  assert.equal(
    await p
      .locator(portal)
      .getByRole("button", { name: "Nur lesen" })
      .isDisabled(),
    true,
  );
  await p.close();
});
for (const [name, viewport] of [
  ["phone", { width: 360, height: 640 }],
  ["tablet", { width: 768, height: 1024 }],
  ["desktop", { width: 1440, height: 900 }],
])
  test(`${name}: 105 alerts, scrolling, long content, transparent theme and focus containment`, async () => {
    const p = await setup(viewport, "de");
    await p.evaluate(() => {
      document.documentElement.style.cssText =
        "--ha-card-background:rgba(25,35,45,.4);--primary-text-color:rgb(240,240,240);--ha-card-backdrop-filter:blur(12px);--warning-color:rgb(220,180,40)";
      connection.alerts = Array.from({ length: 105 }, (_, i) => ({
        ...connection.alerts[0],
        rule_id: `r${i}`,
        entity_id: `sensor.${"long".repeat(80)}`,
        acknowledged: i !== 0,
      }));
      connection.emit();
    });
    await p.waitForFunction(
      () =>
        document.querySelector("lightweight-status-alerts-card").store.alerts
          .length === 105,
    );
    await p.locator(`${card} .trigger`).click();
    assert.equal(await p.locator(`${portal} article`).count(), 105);
    const layout = await p.locator(`${portal} dialog`).evaluate((d) => ({
      width: d.getBoundingClientRect().width,
      height: d.getBoundingClientRect().height,
      horizontal: d.scrollWidth > d.clientWidth + 1,
      scroll: d.scrollHeight > d.clientHeight,
      background: getComputedStyle(d).backgroundColor,
      blur: getComputedStyle(d).backdropFilter,
    }));
    assert.ok(layout.width <= viewport.width - 20);
    assert.ok(layout.height <= viewport.height - 20);
    assert.equal(layout.horizontal, false);
    assert.equal(layout.scroll, true);
    assert.equal(layout.background, "rgba(25, 35, 45, 0.4)");
    assert.equal(layout.blur, "blur(12px)");
    await p
      .locator(portal)
      .getByRole("button", { name: "Quittierung zurücknehmen" })
      .last()
      .focus();
    await p.keyboard.press("Tab");
    assert.equal(
      await p
        .locator(`${portal} dialog`)
        .evaluate((d) => d.contains(d.getRootNode().activeElement)),
      true,
    );
    await p.close();
  });

test("empty badge stays connected, reappears on an event, and dialog is removed on navigation", async () => {
  const p = await setup();
  await p.evaluate(() => {
    window.saved = connection.alerts;
    connection.alerts = [];
    connection.emit();
  });
  await p.waitForFunction(
    () => document.querySelector("lightweight-status-badge").hidden,
  );
  assert.equal(
    await p.locator("#hui-badge-fixture").evaluate((w) => w.hidden),
    true,
  );
  assert.equal(await p.evaluate(() => connection.unsubscribed), 0);
  await p.locator(`${card} .trigger`).click();
  assert.match(
    await p.locator(`${portal} dialog`).innerText(),
    /No active alerts/,
  );
  await p.keyboard.press("Escape");
  await p.evaluate(() => {
    connection.alerts = saved;
    connection.emit();
  });
  await p.waitForFunction(
    () => !document.querySelector("lightweight-status-badge").hidden,
  );
  assert.equal(
    await p.locator("#hui-badge-fixture").evaluate((w) => w.hidden),
    false,
  );
  await p.locator(`${badge} .trigger`).click();
  await p.evaluate(() =>
    document.querySelector("lightweight-status-badge").remove(),
  );
  await p.waitForFunction(
    () => !document.querySelector("lightweight-status-dialog"),
  );
  await p.close();
});
