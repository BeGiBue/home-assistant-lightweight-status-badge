# Changelog

Release-Texte der GitHub-Releases. Der Abschnitt `## X.Y.Z` wird vom Workflow
`.github/workflows/release.yml` als Release-Text verwendet.

## 0.1.7

Aufräumen des Repositorys, keine Funktionsänderung.

- Doppelte Datei `frontend/lightweight-status-badge.js` entfernt; das Modul liegt nur noch unter
  `custom_components/lightweight_status_badge/www/lightweight-status-badge.js`. Der Build-Schritt
  (`npm run build`) entfällt, `npm run check` prüft nur noch die Syntax.
- Doppelte Datei `strings.json` entfernt; Texte liegen nur noch in `translations/en.json` und
  `translations/de.json`.
- Unbenutzte Felder `started` und `message_ids` aus den Alarm-Datensätzen der WebSocket-API entfernt.
- Standardliste der gesunden Zustände für `disk_health` als gemeinsame Konstante.
- Versionsangabe in `manifest.json` auf 0.1.7 korrigiert (stand zuvor auf 1.6.0).
- `CHANGELOG.md` und Release-Workflow angelegt.

## 0.1.6

new catalog system for adding entities

## 0.1.5

Geräteimport und auswählbare Fehlerzustände.

### Neu in 0.1.5

- **Gerät oder Integrationsinstanz auswählen und Entitäten per Checkbox hinzufügen.** Mehrere Entitäten werden nacheinander mit jeweils einer eigenen Regel konfiguriert und ausdrücklich gespeichert; Überspringen und Abbrechen sind möglich.
- **Betriebsentitäten von Saug- und Mährobotern sind auswählbar.** Die Liste schließt auch ausgeblendete und deaktivierte registrierte Entitäten ein; deaktivierte Entitäten werden nicht automatisch aktiviert.
- **Fehlerzustände per Checkbox festlegen.** Vorschläge stammen aus gemeldeten Zustandsoptionen, Registry-Metadaten, standardisierten HA-Betriebszuständen und dem aktuellen Zustand. Fehlende Werte können ergänzt werden. Normale Betriebszustände werden nicht automatisch als Fehler behandelt.
- Deutsche und englische Oberfläche sowie Bedienungsdokumentation aktualisiert.

### Qualitätssicherung

- 185 Python-/Home-Assistant-Tests bestanden, 97 % Statement-Abdeckung.
- Automatisierte Prüfungen für Gerätegruppen, Integrationsinstanzen, Mehrfachimport, Speichern/Überspringen/Abbrechen, Fehlerzustände, authentifizierte HTTP-Formulare und Berechtigungen.
- Bestehende Tests für globale Quittierung, Neustartverhalten und Überwachung sind enthalten.
- GitHub-CI für Backend, Frontend/Browser, HACS und Hassfest erfolgreich.

### Installation und Grenzen

Nach dem Update Home Assistant neu starten. Getestet mit Home Assistant 2026.10.2.

Rückwärtskompatibilität ist für dieses Release ausdrücklich nicht zugesichert; vor dem Update eine Sicherung erstellen. Nicht jede Integration stellt eine vollständige Zustandsliste bereit. Fehler, die ausschließlich in beliebigen Attributen stehen, werden von diesem Zustandsimporter nicht automatisch ausgewertet. Praxistests mit echten Robotern und Raspberry Pi 4 stehen weiterhin aus.

## 0.1.0

Initiale Testversion der Home-Assistant-Integration.

### Funktionen

- Vollständige grafische Konfiguration von Überwachungsregeln
- Vordefinierte Vorlagen und individuelle Auswertungsregeln
- Drei Prioritätsstufen: Hinweis, Warnung und Kritisch
- Ereignisbasierte, ressourcenschonende Überwachung
- Dashboard-Badge mit automatischer Ausblendung
- Ausführliche Störungsdetails und Handlungsempfehlungen
- Globale Quittierung mit Speicherung über Neustarts
- Deutsche und englische Oberfläche
- HACS-Installationsstruktur

### Qualitätssicherung

- 175 Python-/Home-Assistant-Tests bestanden
- 28 Frontend-Tests bestanden
- 97 % Codeabdeckung
- Hassfest-Validierung bestanden

### Bekannte Einschränkungen

- Raspberry-Pi-4-Praxistests stehen aus
- HACS-Validierung noch nicht vollständig bestanden
- Getestet mit Home Assistant 2026.10.2

Hinweis: Dies ist eine frühe Testversion. Vor der Installation wird ein Home-Assistant-Backup empfohlen.
