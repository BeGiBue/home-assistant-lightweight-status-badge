"""Bounded, escaped messages; only explicit state/attribute placeholders are supported."""

import re
from html import escape

MESSAGES = {
    "en": {
        "unknown": "The entity state is unknown. Check the source integration.",
        "unavailable": "The entity is unavailable or missing. Check connectivity.",
        "binary_on": "The configured fault indicator is on.",
        "update_available": "An update is available. Review the update instructions.",
        "disk_health": "Drive health is outside the configured healthy states. Check the drive.",
        "positive_count": "The count exceeds the configured threshold. Check the source.",
        "unifi_state": "The UniFi device reports a connection or provisioning problem.",
        "ups_ob": "The UPS is running on battery. Check the mains supply.",
        "ups_lb": "The UPS battery is low. Prepare a safe shutdown.",
        "ups_fsd": "The UPS reports a forced shutdown. Check the UPS and connected systems.",
        "ups_rb": "The UPS reports that its battery needs replacement.",
        "nonzero_code": "The source reports an error code. Consult its documentation for meaning.",
        "diagnostic_state": "The source matches a configured diagnostic fault state.",
        "grid_fault": "The source reports a grid fault. Check the grid connection.",
        "custom": "The configured condition matches the current entity state.",
    },
    "de": {
        "unknown": "Der Zustand ist unbekannt. Prüfe die Quellintegration.",
        "unavailable": "Die Entität ist nicht verfügbar oder fehlt. Prüfe die Verbindung.",
        "binary_on": "Der konfigurierte Störungsindikator ist eingeschaltet.",
        "update_available": "Ein Update ist verfügbar. Prüfe die Update-Hinweise.",
        "disk_health": (
            "Der Laufwerkszustand ist nicht als gesund konfiguriert. Prüfe das Laufwerk."
        ),
        "positive_count": "Der Zähler überschreitet den Grenzwert. Prüfe die Quelle.",
        "unifi_state": "Das UniFi-Gerät meldet ein Verbindungs- oder Einrichtungsproblem.",
        "ups_ob": "Die USV läuft im Batteriebetrieb. Prüfe die Netzversorgung.",
        "ups_lb": "Die USV-Batterie ist fast leer. Bereite ein sicheres Herunterfahren vor.",
        "ups_fsd": (
            "Die USV meldet erzwungenes Herunterfahren. Prüfe USV und angeschlossene Systeme."
        ),
        "ups_rb": "Die USV meldet, dass ihre Batterie ersetzt werden muss.",
        "nonzero_code": (
            "Die Quelle meldet einen Fehlercode. Die Bedeutung steht in ihrer Dokumentation."
        ),
        "diagnostic_state": "Die Quelle meldet einen konfigurierten Diagnose-Fehlerzustand.",
        "grid_fault": "Die Quelle meldet einen Netzfehler. Prüfe die Netzverbindung.",
        "custom": "Die konfigurierte Bedingung trifft auf den aktuellen Zustand zu.",
    },
}
TOKEN = re.compile(r"\{(state|attributes\.[a-zA-Z0-9_]+)\}")


def render(template, state, attributes, whitelist):
    def replace(match):
        key = match[1]
        if key == "state":
            return state
        attr = key.removeprefix("attributes.")
        value = attributes.get(attr) if attr in whitelist else None
        return str(value)[:255] if isinstance(value, (str, int, float, bool)) else ""

    return escape(TOKEN.sub(replace, template)[:1000])
