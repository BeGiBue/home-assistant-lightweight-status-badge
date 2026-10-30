/* Lightweight Status Badge. No dependencies, polling, storage or HTML interpolation. */
const DOMAIN = "lightweight_status_badge";
const words = {
  en: {
    name: "Status alerts",
    all: "All active alerts",
    empty: "No active alerts",
    ack: "Acknowledge globally",
    undo: "Undo acknowledgement",
    acknowledged: "Acknowledged",
    raw: "Original state",
    entity: "Entity",
    close: "Close",
    retry: "Retry",
    loading: "Loading…",
    offline: "Connection lost. Reconnect to update alerts.",
    error: "Could not load alerts.",
    unloaded: "Integration is not loaded.",
    denied: "Entity control permission required.",
    stale: "Alert changed or cleared. Review the current alerts.",
    failed: "Action failed. Review the current alerts before retrying.",
    title: "Display name",
    notice: "Notice",
    warning: "Warning",
    critical: "Critical",
    readOnly: "Read only",
  },
  de: {
    name: "Statusmeldungen",
    all: "Alle aktiven Meldungen",
    empty: "Keine aktiven Meldungen",
    ack: "Global quittieren",
    undo: "Quittierung zurücknehmen",
    acknowledged: "Quittiert",
    raw: "Originalzustand",
    entity: "Entität",
    close: "Schließen",
    retry: "Erneut versuchen",
    loading: "Wird geladen…",
    offline:
      "Verbindung unterbrochen. Nach Wiederverbindung werden Meldungen aktualisiert.",
    error: "Meldungen konnten nicht geladen werden.",
    unloaded: "Integration ist nicht geladen.",
    denied: "Steuerungsberechtigung für die Entität erforderlich.",
    stale: "Meldung geändert oder beendet. Aktuelle Meldungen prüfen.",
    failed:
      "Aktion fehlgeschlagen. Vor erneutem Versuch aktuelle Meldungen prüfen.",
    title: "Anzeigename",
    notice: "Hinweis",
    warning: "Warnung",
    critical: "Kritisch",
    readOnly: "Nur lesen",
  },
};
export const language = (hass) =>
  (hass?.locale?.language || hass?.language || "en").split("-")[0] === "de"
    ? "de"
    : "en";
export const decodeText = (value) =>
  String(value ?? "").replace(
    /&(amp|lt|gt|quot|#x27);/g,
    (_, key) => ({ amp: "&", lt: "<", gt: ">", quot: '"', "#x27": "'" })[key],
  );
export function summary(alerts) {
  const unread = alerts.filter((a) => !a.acknowledged);
  return {
    count: unread.length,
    severity: unread.reduce((s, a) => Math.max(s, a.severity), 0),
  };
}

// One permission-filtered snapshot and subscription for all mounted views per connection/locale.
const connections = new WeakMap();
function disposeSubscription(unsubscribe) {
  // HA cleans up subscription IDs in finally, even if disconnected mid-unsubscribe.
  try {
    Promise.resolve(unsubscribe?.()).catch(() => {});
  } catch {
    /* Already closed. */
  }
}
export class AlertStore {
  constructor(connection, lang) {
    this.connection = connection;
    this.lang = lang;
    this.listeners = new Set();
    this.alerts = [];
    this.status = "loading";
    this.actionError = "";
    this.pending = new Set();
    this.epoch = 0;
    this.dirty = false;
    this.running = false;
    this.active = false;
    this.lifecycle = 0;
    this.subscribing = false;
    this.onDisconnected = () => {
      this.dirty = false;
      this.epoch++;
      this.alerts = [];
      this.status = "offline";
      this.emit();
    };
    this.onReady = () => {
      if (this.unsubscribe) this.refresh();
      else if (!this.subscribing) this.retry();
    };
  }
  listen(listener) {
    this.listeners.add(listener);
    if (!this.active) {
      this.active = true;
      this.start();
    }
    listener(this);
    return () => {
      this.listeners.delete(listener);
      if (!this.listeners.size) this.stop();
    };
  }
  emit() {
    for (const fn of this.listeners) fn(this);
  }
  async start() {
    const generation = ++this.lifecycle;
    this.subscribing = true;
    this.epoch++;
    this.connection.addEventListener("disconnected", this.onDisconnected);
    this.connection.addEventListener("ready", this.onReady);
    try {
      const unsubscribe = await this.connection.subscribeMessage(
        (event) => {
          if (!this.active || generation !== this.lifecycle) return;
          if (!event.loaded) {
            this.dirty = false;
            this.epoch++;
            this.alerts = [];
            this.status = "unloaded";
            this.emit();
          } else this.refresh();
        },
        { type: `${DOMAIN}/subscribe` },
      );
      if (!this.active || generation !== this.lifecycle)
        disposeSubscription(unsubscribe);
      else this.unsubscribe = unsubscribe;
    } catch {
      if (this.active && generation === this.lifecycle) {
        this.status = "error";
        this.emit();
      }
    } finally {
      if (generation === this.lifecycle) this.subscribing = false;
    }
  }
  stop() {
    this.active = false;
    this.lifecycle++;
    this.epoch++;
    this.dirty = false;
    disposeSubscription(this.unsubscribe);
    this.unsubscribe = undefined;
    this.subscribing = false;
    this.connection.removeEventListener("disconnected", this.onDisconnected);
    this.connection.removeEventListener("ready", this.onReady);
    this.alerts = [];
    this.pending.clear();
    this.actionError = "";
    this.status = "loading";
  }
  retry() {
    if (!this.unsubscribe) {
      this.stop();
      this.active = true;
      this.start();
    } else this.refresh();
  }
  async refresh() {
    if (!this.active) return;
    this.epoch++;
    this.dirty = true;
    if (this.running) return;
    this.running = true;
    try {
      while (this.active && this.dirty) {
        this.dirty = false;
        const epoch = this.epoch;
        try {
          let records = [],
            offset = 0,
            revision,
            total,
            restarts = 0;
          do {
            const page = await this.connection.sendMessagePromise({
              type: `${DOMAIN}/alerts`,
              offset,
              language: this.lang,
            });
            if (!this.active || epoch !== this.epoch) break;
            if (
              !Array.isArray(page.alerts) ||
              page.alerts.length > 100 ||
              !Number.isInteger(page.total) ||
              page.total > 1000
            )
              throw new Error("Invalid page");
            if (
              revision !== undefined &&
              (page.revision !== revision || page.total !== total)
            ) {
              if (++restarts > 3)
                throw new Error("Snapshot changed repeatedly");
              records = [];
              offset = 0;
              revision = undefined;
              total = undefined;
              continue;
            }
            revision = page.revision;
            total = page.total;
            records.push(...page.alerts);
            if (
              page.next_offset !== null &&
              (!Number.isInteger(page.next_offset) ||
                page.next_offset <= offset ||
                page.next_offset > 1000)
            )
              throw new Error("Invalid offset");
            offset = page.next_offset;
          } while (offset !== null);
          if (!this.active || epoch !== this.epoch) continue;
          if (records.length !== total) throw new Error("Incomplete snapshot");
          this.alerts = records;
          this.status = "ready";
          this.emit();
        } catch (err) {
          if (this.active && epoch === this.epoch) {
            this.alerts = [];
            this.status = err?.code === "not_loaded" ? "unloaded" : "error";
            this.emit();
          }
        }
      }
    } finally {
      this.running = false;
    }
  }
  async acknowledge(alert) {
    if (
      this.status !== "ready" ||
      this.pending.has(alert.rule_id) ||
      alert.can_acknowledge === false
    )
      return;
    const generation = this.lifecycle;
    this.pending.add(alert.rule_id);
    this.actionError = "";
    this.emit();
    try {
      await this.connection.sendMessagePromise({
        type: `${DOMAIN}/acknowledge`,
        rule_id: alert.rule_id,
        occurrence: alert.occurrence,
        acknowledged: !alert.acknowledged,
      });
    } catch (err) {
      if (!this.active || generation !== this.lifecycle) return;
      this.actionError =
        err?.code === "unauthorized"
          ? "denied"
          : err?.code === "invalid_alert"
            ? "stale"
            : "failed";
    } finally {
      if (this.active && generation === this.lifecycle) {
        this.pending.delete(alert.rule_id);
        this.emit();
        await this.refresh();
      }
    }
  }
}
function getStore(connection, lang) {
  if (!connections.has(connection)) connections.set(connection, new Map());
  const stores = connections.get(connection);
  if (!stores.has(lang)) stores.set(lang, new AlertStore(connection, lang));
  return stores.get(lang);
}
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
const styles = `
:host { color:var(--primary-text-color); font-family:var(--paper-font-body1_-_font-family,inherit) }
:host([hidden]) { display:none !important }
button { font:inherit; color:inherit; cursor:pointer; min-height:44px; border:1px solid var(--divider-color, #888); border-radius:var(--ha-card-border-radius,12px); padding:8px 12px; background:var(--ha-card-background,var(--card-background-color,transparent)) }
button:focus-visible { outline:3px solid var(--primary-color); outline-offset:2px }
button:disabled { cursor:default; opacity:.6 }
.trigger { display:flex; align-items:center; gap:8px; background:var(--ha-card-background,var(--card-background-color,transparent)); backdrop-filter:var(--ha-card-backdrop-filter, var(--backdrop-filter,none)); box-shadow:var(--ha-card-box-shadow,none) }
.badge { border-radius:24px; border-color:var(--ha-card-border-color,var(--divider-color)); font-size:14px; min-height:44px; padding:4px 12px }
.icon,.priority { color:var(--severity-color,var(--primary-color)); font-weight:600 }
.s1 { --severity-color:var(--info-color,#039be5) } .s2 { --severity-color:var(--warning-color,#ffa600) } .s3 { --severity-color:var(--error-color,#db4437) }
dialog { color:var(--primary-text-color); background:var(--ha-card-background,var(--card-background-color,var(--primary-background-color,#fff))); backdrop-filter:var(--ha-card-backdrop-filter,var(--backdrop-filter,none)); border:1px solid var(--ha-card-border-color,var(--divider-color)); border-radius:var(--ha-card-border-radius,12px); box-shadow:var(--ha-card-box-shadow,0 8px 32px #0005); padding:0; width:min(680px,calc(100vw - 24px)); max-width:calc(100vw - 24px); max-height:calc(100dvh - 24px); overflow:auto; box-sizing:border-box }
dialog::backdrop { background:rgba(0,0,0,.4) }
header { display:flex; align-items:center; gap:12px; padding:16px; border-bottom:1px solid var(--divider-color) }
h2 { margin:0; font-size:1.2rem; flex:1 } header button { flex-shrink:0 }
.body { padding:0 16px 16px } article { border-bottom:1px solid var(--divider-color); padding:16px 0; overflow-wrap:anywhere } h3 { font-size:1rem; margin:0 0 8px } p { white-space:pre-wrap; overflow-wrap:anywhere; margin:8px 0 } .technical { color:var(--secondary-text-color); font-size:.875rem } .error { color:var(--error-color); overflow-wrap:anywhere }
@media(max-width:480px) { header { padding:12px } .body { padding:0 12px 12px } article button { width:100% } }
`;
class StatusView extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    const style = element("style", styles);
    this.trigger = element("button");
    this.trigger.type = "button";
    this.trigger.onclick = () => this.openDialog();
    this.dialog = element("dialog");
    this.dialog.setAttribute("aria-labelledby", "dialog-title");
    this.dialog.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const buttons = [
        ...this.dialog.querySelectorAll("button:not(:disabled)"),
      ];
      const first = buttons[0],
        last = buttons.at(-1),
        active = this.dialog.getRootNode().activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first?.focus();
      }
    });
    this.dialog.addEventListener("close", () => {
      this.shadowRoot.append(this.dialog);
      this.dialogHost?.remove();
      this.dialogHost = undefined;
      this.render();
      if (!this.hidden) this.trigger.focus();
    });
    this.dialog.addEventListener("click", (ev) => {
      if (ev.target === this.dialog) {
        const r = this.dialog.getBoundingClientRect();
        if (
          ev.clientX < r.left ||
          ev.clientX > r.right ||
          ev.clientY < r.top ||
          ev.clientY > r.bottom
        )
          this.dialog.close();
      }
    });
    this.shadowRoot.append(style, this.trigger, this.dialog);
  }
  get connectedWhileHidden() {
    return true;
  }
  static getStubConfig() {
    return {};
  }
  static getConfigElement() {
    return document.createElement("lightweight-status-badge-editor");
  }
  setConfig(config) {
    if (config.name !== undefined && typeof config.name !== "string")
      throw new Error("name must be text");
    this.config = { ...config };
    this.render();
  }
  set hass(hass) {
    this._hass = hass;
    this.bind();
  }
  connectedCallback() {
    this.bind();
  }
  disconnectedCallback() {
    this.release?.();
    this.release = undefined;
    this.store = undefined;
    if (this.dialog.open) this.dialog.close();
  }
  bind() {
    if (!this.isConnected || !this._hass?.connection) return;
    const lang = language(this._hass),
      store = getStore(this._hass.connection, lang);
    if (store === this.store) return;
    this.release?.();
    this.store = store;
    this.lang = lang;
    this.release = store.listen(() => this.render());
  }
  get t() {
    return words[this.lang || language(this._hass)];
  }
  getCardSize() {
    return 1;
  }
  getGridOptions() {
    return { columns: 12, rows: 1, min_columns: 6 };
  }
  openDialog() {
    if (this.dialog.open) return;
    // A hidden hui-badge must keep its subscription, while the modal lives outside
    // its display:none wrapper. Copy inherited theme variables into the portal.
    this.dialogHost = document.createElement("lightweight-status-dialog");
    this.dialogHost.style.display = "contents";
    const theme = getComputedStyle(this);
    for (const property of theme)
      if (property.startsWith("--"))
        this.dialogHost.style.setProperty(
          property,
          theme.getPropertyValue(property),
        );
    const root = this.dialogHost.attachShadow({ mode: "open" });
    root.append(element("style", styles), this.dialog);
    document.body.append(this.dialogHost);
    this.renderDialog();
    this.dialog.showModal();
  }
  render() {
    const t = this.t,
      store = this.store,
      s = summary(store?.alerts || []);
    const badge = this.localName === "lightweight-status-badge";
    const empty = badge && store?.status === "ready" && s.count === 0;
    const wasHidden = this.hidden;
    this.hidden = Boolean(empty);
    if (wasHidden !== this.hidden)
      this.dispatchEvent(
        new CustomEvent("badge-visibility-changed", {
          detail: { value: !this.hidden },
          bubbles: true,
          composed: true,
        }),
      );
    this.trigger.style.display = empty ? "none" : "";
    this.trigger.className = `trigger ${badge ? "badge" : "card"} s${s.severity}`;
    const title = this.config?.name || (badge ? t.name : t.all);
    const icon = element("span", "⚠", "icon");
    icon.setAttribute("aria-hidden", "true");
    const severity = t[["", "notice", "warning", "critical"][s.severity]] || "";
    const text =
      store?.status === "ready"
        ? badge
          ? `${title} · ${s.count}${severity ? ` · ${severity}` : ""}`
          : `${title} · ${store.alerts.length}`
        : `${title} · ${t[store?.status || "loading"]}`;
    this.trigger.replaceChildren(icon, element("span", text));
    this.trigger.setAttribute("aria-label", text);
    this.trigger.setAttribute("aria-haspopup", "dialog");
    if (this.dialog.open) this.renderDialog();
  }
  renderDialog() {
    const t = this.t,
      store = this.store;
    const focused = this.dialog.getRootNode().activeElement?.dataset?.key;
    const scroll = this.dialog.scrollTop;
    const header = element("header"),
      title = element("h2", t.all);
    title.id = "dialog-title";
    const close = element("button", t.close);
    close.type = "button";
    close.dataset.key = "close";
    close.onclick = () => this.dialog.close();
    header.append(title, close);
    const body = element("div", undefined, "body");
    body.setAttribute("aria-live", "polite");
    if (store?.actionError) {
      const error = element("p", t[store.actionError], "error");
      error.setAttribute("role", "alert");
      body.append(error);
    }
    if (store?.status !== "ready") {
      body.append(element("p", t[store?.status || "loading"], "error"));
      if (store && store.status !== "loading") {
        const retry = element("button", t.retry);
        retry.dataset.key = "retry";
        retry.onclick = () => store.retry();
        body.append(retry);
      }
    } else if (!store.alerts.length) body.append(element("p", t.empty));
    else
      for (const alert of store.alerts) {
        const article = element("article", undefined, `s${alert.severity}`);
        article.append(
          element("h3", decodeText(alert.title)),
          element(
            "p",
            `${t[["", "notice", "warning", "critical"][alert.severity]]}${alert.acknowledged ? ` · ${t.acknowledged}` : ""}`,
            "priority",
          ),
          element("p", decodeText(alert.description)),
        );
        if (alert.recommendation)
          article.append(element("p", decodeText(alert.recommendation)));
        article.append(
          element("p", `${t.raw}: ${decodeText(alert.raw_state)}`, "technical"),
          element("p", `${t.entity}: ${alert.entity_id}`, "technical"),
        );
        const action = element(
          "button",
          alert.can_acknowledge === false
            ? t.readOnly
            : alert.acknowledged
              ? t.undo
              : t.ack,
        );
        action.dataset.key = alert.rule_id;
        action.disabled =
          store.pending.has(alert.rule_id) || alert.can_acknowledge === false;
        action.onclick = () => store.acknowledge(alert);
        article.append(action);
        body.append(article);
      }
    this.dialog.replaceChildren(header, body);
    if (focused) {
      const target = [...this.dialog.querySelectorAll("button")].find(
        (b) => b.dataset.key === focused && !b.disabled,
      );
      (target || close).focus({ preventScroll: true });
    }
    this.dialog.scrollTop = scroll;
  }
}
class StatusBadge extends StatusView {}
class StatusCard extends StatusView {}
class StatusEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }
  set hass(hass) {
    this._hass = hass;
    this.render();
  }
  setConfig(config) {
    this.config = { ...config };
    this.render();
  }
  render() {
    const t = words[language(this._hass)];
    if (!this.input) {
      this.label = element("label");
      this.input = element("input");
      this.input.type = "text";
      this.input.maxLength = 100;
      this.input.style.cssText =
        "display:block;box-sizing:border-box;width:100%;padding:12px;color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color,transparent));border:1px solid var(--divider-color);border-radius:8px;font:inherit";
      this.input.addEventListener("input", () => {
        this.config = { ...this.config, name: this.input.value };
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: this.config },
            bubbles: true,
            composed: true,
          }),
        );
      });
      this.labelText = element("span");
      this.label.append(this.labelText, this.input);
      this.shadowRoot.append(this.label);
    }
    this.labelText.textContent = t.title;
    this.input.placeholder = t.name;
    if (this.shadowRoot.activeElement !== this.input)
      this.input.value = this.config?.name || "";
  }
}
// Registry-sicher registrieren. Lädt eine andere Karte oder ein Add-on den Polyfill
// @webcomponents/scoped-custom-element-registry, ersetzt er window.customElements durch eine
// neue, leere Registry; Home Assistant sucht Badges und Karten dort und meldet sonst
// "Custom element doesn't exist". Das kann auch nach dem Laden dieses Moduls passieren.
// Darum wird idempotent in der jeweils aktuellen Registry angemeldet: sofort, im Start alle
// 500 ms, danach alle 10 s sowie bei load, location-changed und Sichtbarkeitswechsel.
// Ein Durchlauf prüft nur drei Einträge (unter einer Mikrosekunde).
(function keepRegistered(definitions) {
  const ensure = () => {
    for (const [name, component] of definitions) {
      try {
        if (!customElements.get?.(name)) customElements.define(name, component);
      } catch {
        // Name schon vergeben oder Klasse abgelehnt: ein anderer Lader war schneller.
      }
    }
  };
  ensure();
  let rounds = 0;
  const later = (delay) => {
    const timer = setTimeout(() => {
      ensure();
      later(rounds++ < 40 ? 500 : 10000);
    }, delay);
    timer?.unref?.(); // hält in Node-Tests den Prozess nicht offen
  };
  later(500);
  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("load", ensure, { once: true });
    window.addEventListener("location-changed", ensure);
  }
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("visibilitychange", ensure);
  }
})([
  ["lightweight-status-badge", StatusBadge],
  ["lightweight-status-alerts-card", StatusCard],
  ["lightweight-status-badge-editor", StatusEditor],
]);
window.customBadges = window.customBadges || [];
if (!window.customBadges.some((item) => item.type === "lightweight-status-badge")) window.customBadges.push({
  type: "lightweight-status-badge",
  name: "Lightweight Status Badge",
  description: "Live alerts / Aktive Meldungen",
  preview: true,
});
window.customCards = window.customCards || [];
if (!window.customCards.some((item) => item.type === "lightweight-status-alerts-card")) window.customCards.push({
  type: "lightweight-status-alerts-card",
  name: "Lightweight Status Alerts",
  description:
    "All active alerts, including acknowledged / Alle aktiven Meldungen, auch quittierte",
  preview: true,
});
