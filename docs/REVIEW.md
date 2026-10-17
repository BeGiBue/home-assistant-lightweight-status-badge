# Unabhängiger Gesamtreview von PR #6–#8

Stand: 17.10.2026. Ausgangspunkt: `feat/status-badge-dashboard-issue-4`,
`7b0d8a275a0a008a8d98b0c6f03cb24269e1c020`. PR #6 (`e99d695`), #7 (`7fc0a19`)
und #8 (`7b0d8a2`) sind offen und aufeinander gestapelt, nicht nach main gemergt.
SPEC.md, ARCHITECTURE.md, README und alle Entwicklungsdokumentationen wurden vor
der Implementierung gelesen. Produktanforderungen bleiben unverändert.

## Befunde und Korrekturen

| ID | Schwere | Ursache / Auswirkung | Korrektur / Regression |
| --- | --- | --- | --- |
| R1 | Mittel | Optionsentwurf enthält eine alte Regelkopie; Speichern kann eine zwischenzeitlich aktualisierte Regel überschreiben. Abbrechen nach externer Entfernung wirft StopIteration. | Originalvergleich unmittelbar vor synchronem Speichern; lokalisierter Konfliktfehler, Entwurf verwerfen/neuladen. Entfernte Regel führt zur Übersicht. Echter HA-Flow-Test mit externer Änderung/Entfernung. |
| R2 | Mittel | Asynchrone Quittierungsantwort lebt länger als die letzte Ansicht. Nach erneutem Mounten können alte Fehler, ausstehende Aktionen und Refreshes in die neue Sitzung gelangen. | Lifecycle-Vergleich vor Anwendung der Antwort, Pending/Error beim letzten Detach löschen. Deterministischer Promise-Regressionstest. |
| R3 | Mittel | Echte HA-Abschaltung meldet `Unable to remove unknown job listener`: bereits ausgeführte Einmal-Listener verbleiben in der Cleanup-Liste. Das war von bisherigen Funktionsassertionen nicht erfasst. | Verbrauchte STARTED-Abmeldung aus Cleanup entfernen; STOP bleibt regulärer Listener bis close. Test prüft auch Logs; echter Prozessneustart bestätigt sauberes Integration-Cleanup. |
| R4 | Mittel | HACS-Installation war nicht beschrieben/validiert, Ressource musste grundsätzlich manuell angelegt werden; kein automatischer Update-Cachewechsel. | Gemeinsames Integration-Paket, hacs.json, getrennte HACS-/Hassfest-CI, Installation DE/EN; tatsächliche Storage-Ressourcenregistrierung mit Modul-Hash, Reload-/Update-Test und YAML-Sonderfall. |
| R5 | Niedrig | Erneuter Import unter anderer Modul-URL wirft beim zweiten customElements.define; Picker können doppelt erscheinen. Relevant bei manueller Migration auf versionierte URL. | Element- und Pickerregistrierung idempotent; Test importiert zwei Version-URLs. Neue Implementierung erfordert Browserreload nach Update. |
| R6 | Niedrig | Browserprüfung erwartet synchrones Portal-Cleanup unmittelbar nach Escape; natives close-Event ist asynchron. Ein Lauf scheiterte, Wiederholung bestand. | Test wartet auf DOM-Entfernung statt auf Scheduling zu vertrauen; vollständiger Browserlauf danach erfolgreich. |
| R7 | Niedrig | Offizieller Hassfest-Validator beanstandet Reihenfolge der Manifestfelder. | domain/name zuerst, übrige Felder alphabetisch; erneute offizielle Validierung. |
| R8 | Mittel | Evaluator normalisiert unknown/unavailable, Startup-Restoration prüfte den Rohtext exakt. Großschreibung/Whitespace konnte eine passende Quittierung beim Start verwerfen. | Gleiche Normalisierung im Coordinator, parametrisierter HA-Regressionstest mit ` UNKNOWN `. |

Keine unbelegten kritischen Sicherheitsfehler gefunden. Das ist keine Garantie für
Fehlerfreiheit. R1 wurde mit einer externen Optionsänderung geprüft; es wird nicht
behauptet, dass HA zwei gleichzeitige Optionsflows desselben Eintrags zulässt.

## Geprüfte Bereiche

- **HA/API/Architektur:** aktuelles HA 2026.10.2, ConfigEntry.runtime_data,
  native OptionsFlow-Selektoren, asynchrone StaticPathConfig-Registrierung,
  nichtpollende Aggregate. Reiner Evaluator, Coordinator und Storage sinnvoll
  getrennt. Manifest, Übersetzungsschlüssel, Services und Abhängigkeiten mit
  offiziellem Hassfest geprüft. Interne Lovelace-Collection-API bleibt Versionsrisiko.
- **Persistenz/Neustart:** nur aktive Quittierungsidentitäten; verzögerter Save
  liest aktuellen Snapshot. Auflösen vor Save, Wiederauftreten, fehlerhafte
  Speicherung, Startup unknown/unavailable, graceful final-write und echte
  Prozessneustarts geprüft. Ein harter Stromausfall ist kein getesteter graceful stop.
- **Konkurrenz:** Backend-Mutationen ohne await; Occurrence-Token schützt neue
  Vorkommen vor alten Klicks. Gleiches acknowledge ist idempotent; konkurrierendes
  acknowledge/revoke folgt der Reihenfolge im HA-Eventloop (letzte gültige Aktion).
  Keine Quittierung der Quellentität. GUI-Konfliktprüfung zusätzlich eingeführt.
- **Sicherheit:** authentifiziertes HA-WebSocket-/Service-API, aktiver Benutzer,
  Read/Control auf Quelle vor Mutation, gefilterte Detaildaten, readonly-Aktionen
  deaktiviert. Serverseitige Prüfung bleibt maßgebend. Keine freie Python-/Jinja-
  Ausführung, keine HTML-Interpolation, keine Secrets im Modul. Globale Aggregate
  können Anzahl/Schwere auch von Quellen enthalten, die ein Benutzer nicht lesen
  darf; HA-Berechtigungen für Aggregate entsprechend setzen. WebSocket-
  Invalidierungen verraten weiterhin Aktivität, keine Meldungsinhalte.
- **Leistung/Speicher:** Index nach Quell-ID, nur betroffene Regeln auswerten,
  Dispatch zusammenfassen, kein Polling oder Save bei normalem Zustandswechsel.
  Maximal 1000 Regeln, Detailseiten à 100; frontendseitig konsistente vollständige
  Snapshots. Kein History-Wachstum. Offen: 1000 DOM-Artikel pro geöffnetem Dialog
  sind begrenzt, aber nicht auf RPi gemessen; keine unnötige Virtualisierung ergänzt.
- **WebSocket/Lifecycle:** gemeinsame Store-Instanz je Verbindung/Sprache;
  Invalidierung statt Polling, Pagination-/Revision-Rennen, Disconnect/Ready,
  verspätete Subscription, Fehler bei Unsubscribe, Unload/Reload geprüft.
  Neue Lifecycle-Regression verhindert alte Action-Antworten nach Remount.
- **GUI/Navigation/Locale:** alle Presets/Operatoren, konservative Vorschläge,
  UUID-Auflösung, stabile IDs, Add/Edit/Enable/Disable/Remove/Back, Validierungsfehler,
  echte HA-Übersetzungsladung DE/EN. Konflikthinweis in beiden Sprachen ergänzt.
- **Badge/Popup/Nullzustand:** nur ungelesene Meldungen bestimmen Badge und
  Schwere; vollständig verborgen bei null, unabhängige Karte öffnet alle aktiven
  einschließlich quittierter Meldungen. Empty-, Reappear-, Escape-, Focus-,
  Theme-, mobile und lange Inhalte im Chromium-Fixture geprüft.
- **Fehlende Entitäten:** unavailable-Policy vor normaler Auswertung, GoodWe ignore,
  unknown separat, rohe Zustände sichtbar. Kein automatischer Scan/unbegründete
  Interpretation unbekannter Fehlercodes. Echte Installation mit fehlender
  Entität nach Neustart zusätzlich geprüft.
- **Backend/Frontend:** Permission-Hint ersetzt keine Autorisierung, escaped Text
  wird genau einmal dekodiert und per textContent angezeigt; paginierter Snapshot
  atomar veröffentlicht, Fehlerzustand zeigt kein fälschlich bestätigtes null.

## Offene Risiken und Release-Reife

**Für gezielte Entwicklungstests geeignet; allgemeine Release-Freigabe noch nicht
erteilt.** Kein Merge oder Release wurde durchgeführt.

1. Langzeitbetrieb und echte Geräte nicht getestet. Cloud-Tracemalloc ist kein Hardware-Nachweis.
2. Durchgängiger Browserlauf gegen echtes Lovelace inkl. HACS-Download/Update,
   zwei echten Browsern, realem Theme und Touch/Screenreader fehlt. Native Module
   und HA-APIs wurden getrennt sowie Installation im echten HA-Prozess geprüft.
3. Nur HA 2026.10.2 nachgewiesen; Lovelace-Ressourcen-Collection und Badge-Host sind
   versionsabhängig. Mindestversion bewusst konservativ, spätere Versionen offen.
4. Keine Brand-Registrierung im zentralen HA-brands-Repository. HACS-CI lässt nur
   diesen externen Check explizit aus; Default-List-Aufnahme ist nicht beantragt.
5. Aktueller HACS-Standarddownload enthält den PR erst nach Verfügbarkeit auf einer
   installierbaren Revision. Keine künstliche Veröffentlichung zur Validierung.
6. Abrupter Abbruch kann die letzte Save-Sekunde verlieren; während HA-Ausfall
   vollständig aufgelöste und wiederkehrende Fehler sind ohne Historie nicht
   unterscheidbar. Beides unveränderte, dokumentierte Systemgrenzen.
7. Offizielle HACS-Action: 6/8 Prüfungen bestanden; `license` und `topics`
   fehlgeschlagen. Die Lizenz wurde inzwischen vom Eigentümer als
   AGPL-3.0 festgelegt und als `AGPL-3.0-only` mit vollständigem Text ergänzt.
   GitHubs Erkennung auf dem Standardbranch und Repository-Topics bleiben offen.
   Topics (`home-assistant`, `hacs`, `custom-integration`, `lovelace`) konnten
   über die Verbindung nicht gesetzt werden: GitHub HTTP 403,
   `Resource not accessible by integration`. Eigentümer muss diese unter
   Repository → About → Topics ergänzen. Keine Umgehung dieser Checks.

Die vom Eigentümer gewählte AGPL-3.0-only steht in `LICENSE` sowie im
Integration-Verzeichnis, damit der HACS-Download den Lizenztext enthält.
Die Lizenzentscheidung ist damit abgeschlossen; Merge und Veröffentlichung
sind weiterhin nicht Teil dieses Auftrags.

Die Lizenzprüfung liest GitHubs Repository-Lizenzmetadaten, nicht nur den
PR-Dateibaum. Selbst eine Lizenzdatei im Entwicklungsbranch benötigt später die
Erkennung auf dem Standardbranch. Das rechtfertigt keinen direkten main-Commit
oder Merge; dafür bleibt ein eigener freigegebener PR erforderlich.

Testergebnisse und Grenzen: [REVIEW_TEST_RESULTS.md](REVIEW_TEST_RESULTS.md).
Nachvollziehbare Einrichtung: [INSTALLATION.md](INSTALLATION.md).
