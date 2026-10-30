// Registry-sichere Registrierung mit dem echten Polyfill im Browser: Das Modul ist schon
// registriert, dann lädt ein anderes Add-on @webcomponents/scoped-custom-element-registry
// (ersetzt window.customElements durch eine neue, leere Registry).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const POLYFILL = readFileSync(
  require.resolve("@webcomponents/scoped-custom-element-registry"),
  "utf8",
);
const NAMES = [
  "lightweight-status-badge",
  "lightweight-status-alerts-card",
  "lightweight-status-badge-editor",
];
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
        '<!doctype html><html><head></head><body><script type="module" src="/badge.js"></script></body></html>',
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

const allDefined = (names) =>
  names.every((name) => customElements.get(name));

async function openWithBadge() {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url);
  await page.waitForFunction(allDefined, NAMES);
  return { page, errors };
}

test("echter Polyfill: Badge, Karte und Editor sind danach in der neuen Registry auffindbar", async () => {
  const { page, errors } = await openWithBadge();
  await page.addScriptTag({ content: POLYFILL });
  const swapped = await page.evaluate(
    () => customElements instanceof window.CustomElementRegistry,
  );
  assert.equal(swapped, true, "der Polyfill ist aktiv");
  await page.waitForFunction(allDefined, NAMES, { timeout: 5000 });
  const state = await page.evaluate(async (names) => {
    const badge = document.createElement("lightweight-status-badge");
    return {
      instance: badge instanceof customElements.get("lightweight-status-badge"),
      whenDefined: Boolean(
        await customElements.whenDefined("lightweight-status-alerts-card"),
      ),
      pickers: [window.customBadges.length, window.customCards.length],
    };
  }, NAMES);
  assert.deepEqual(state, { instance: true, whenDefined: true, pickers: [1, 1] });
  assert.deepEqual(errors, []);
  await page.close();
});

test("echter Polyfill: auch ein zweites, spätes Laden des Polyfills wird repariert", async () => {
  const { page, errors } = await openWithBadge();
  await page.addScriptTag({ content: POLYFILL });
  await page.waitForFunction(allDefined, NAMES, { timeout: 5000 });
  await page.addScriptTag({ content: POLYFILL });
  await page.waitForFunction(allDefined, NAMES, { timeout: 5000 });
  assert.deepEqual(errors, []);
  await page.close();
});
