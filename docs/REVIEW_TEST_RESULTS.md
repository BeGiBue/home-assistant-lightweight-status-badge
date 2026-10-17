# Review-Validierung: tatsächliche Ergebnisse

17.10.2026, Linux x86_64 Cloud, HA 2026.10.2 / Python 3.14.8,
Node 24 / Playwright 1.62.1 / systemweites Chromium. Keine physische RPi-Hardware.

## Ausgeführt

| Prüfung | Ergebnis | Aussagegrenze |
| --- | --- | --- |
| Vollständiges pytest mit Timeout/Coverage | 174 bestanden, 5,14 s; 97 % Statements (776, davon 24 nicht ausgeführt) | Echte HA-Testbibliothek; Storage überwiegend Testadapter, separate Atomic-File-Tests |
| Frontend-Store-/Logiktests | 19 bestanden | Deterministische simulierte HA-Verbindung, einschließlich später Action-Antwort und mehrfacher Modulregistrierung |
| Chromium UI | 9 bestanden, 7,21 s | Gebautes Modul, simulierte Verbindung und Badge-Host; kein vollständiger echter Lovelace-Browserlauf |
| npm ci / build / check | Bestanden | Fertiges Modul im Integration-Verzeichnis; 21.583 Bytes, keine Runtime-Abhängigkeiten |
| Ruff lint / format, git diff --check | Bestanden | Statische Prüfung |
| Offizielles Hassfest (Core-Tag 2026.10.2) | 1 Integration, 0 ungültig | Vollständige angebotene Standardprüfungen für Custom Integration; kein Hardwaretest |
| Reale HA-Installation ohne pytest | Setupflow, Optionsreload, Zustandsauswertung, Quittierung, automatische Ressource und HTTP-Modul bestanden | Frische Konfiguration, komplette kopierte Integration, tatsächlicher HA-Prozess; kein HACS-UI-Download |
| Zweiter echter HA-Prozess, gleiche Konfiguration | Regel/Quittierung nach passendem OB-Zustand wiederhergestellt; eine Ressource; HTTP 200 | Persistenz auf echtem Dateisystem, graceful stop |
| Dritter echter HA-Prozess, Quelle zunächst fehlend | Alte Quittierung verworfen, neue fehlende Quelle gemäß unavailable-Policy; eine Ressource; HTTP 200 | Kein physisches Quellgerät |

Die echten Installationsläufe verwendeten HA-Bootstrap, native Flow-Manager,
Lovelace ResourceStorageCollection und aiohttp; keine pytest-Fixtures oder
HA-Mocks. Die bereitgestellte [Smoke-Prüfung](../scripts/ha_smoke.py) reproduziert
diese Schritte in drei separaten Aufrufen. Die lokale HA-Umgebung meldet einen
fehlenden optionalen `libturbojpeg`-Beschleuniger im Camera-Modul und zlib-Fallback;
das betrifft die Testumgebung, nicht die Badge-Integration. Es wird kein insgesamt
warnungsfreier HA-Start behauptet. Der Integration-eigene Listenerfehler aus dem
ersten Installationslauf wurde korrigiert und war bei den Neustarts nicht mehr da.

Erste Fehlversuche transparent: Ein Lauf in der Socket-Sandbox wurde abgebrochen,
weil lokale Socketoperationen nicht möglich waren. Die fertigen HA-/Browserläufe
liefen mit zugelassenem Socketzugriff. Ein früher HA-Test scheiterte während der
Frontend-Bearbeitung an einem noch nicht neu gebauten Artefakt; Build/check und
komplette Suite danach bestanden. Eine Escape-Assertion war zeitabhängig und wurde
auf tatsächliches DOM-Cleanup umgestellt. Hassfest fand zunächst die falsche
Manifestreihenfolge; nach Korrektur erneut bestanden. Diese Fehlversuche zählen
nicht als bestandene Tests.

## Leistung: echte HA-State-Events, Cloud-Hardware

| Quellen | Ausgewählte Events | Prozess-CPU s | Wall s | Tracemalloc retained / peak KiB | Dispatches |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 3000 | 0,2635 | 0,2635 | 371,9 / 858,2 | 4 |
| 100 | 10000 | 0,8801 | 0,8803 | 2710,9 / 2719,8 | 14 |

`tests/test_performance.py`: 2 bestanden, 1,34 s. Eine Regelauswertung je
gewähltem Event, keine Auswertung ungewählter Quellen, keine Quittierungssaves
bei normalen Quellenänderungen. Messschleife inklusive HA-Harness/Tracemalloc;
keine Prozess-RSS, Steady-State-Speicher- oder Raspberry-Pi-Messung.

## Reproduktion

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest --timeout=30 --cov=custom_components.lightweight_status_badge --cov-report=term-missing
.venv/bin/python -m pytest -q -s tests/test_performance.py
npm ci
npm test
npm run build
npm run check
npx playwright install --with-deps chromium
npm run test:browser
.venv/bin/python scripts/ha_smoke.py work/ha-smoke
.venv/bin/python scripts/ha_smoke.py work/ha-smoke matching
.venv/bin/python scripts/ha_smoke.py work/ha-smoke
```

Smoke-Konfiguration ausschließlich zum Testen verwenden, Port 18123 freihalten.
HA-Bootstrap kann beim ersten Start zusätzliche HA-Abhängigkeiten installieren.
Für Hassfest wurde `home-assistant/core` mit Tag `2026.10.2` ausgecheckt und dort
`python -m script.hassfest --integration-path ABSOLUTER_INTEGRATIONSPFAD`
ausgeführt; Ruff muss im PATH sein. CI enthält zusätzlich den offiziellen aktuellen
Hassfest-Actionlauf und die HACS-Action Kategorie `integration`.

## Noch ausstehend

Physischer Raspberry Pi 4, reale Geräte, HACS-Download/Update über die Oberfläche,
komplette Zwei-Browser-Lovelace-Sitzung, andere Browser/HA-Versionen, echte
Screenreader/Touch- und Langzeitprüfung. HACS-Remote-Ergebnis wird separat
protokolliert; eine eingerichtete Action ist noch kein bestandenes Ergebnis.
