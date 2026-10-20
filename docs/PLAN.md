# ATLAS — Forschungs- und Paper-Trading-System

Auftrag: MASTER_PROMPT.md. Keine Echtgeldfunktion. Keine erfundenen Marktdaten,
KI-Antworten oder Ausführungen. Lokaler Windows-Betrieb, Browser unabhängig.
Freigegebenes OpenAI-Budget: 30 EUR/Monat (CEO, 20.10.2026).

## Architekturentscheidung
FastAPI + Python-Worker, React/TypeScript/Vite, SQLite WAL. Eine lokale Datenbank
spart einen Windows-Dienst. Schreiboperationen laufen mit BEGIN IMMEDIATE,
Geldbeträge als ganze Mikro-EUR, Preise als USD-Dezimalwerte. Ein Worker mit
persistenter Queue und einem KI-Aufruf gleichzeitig. Keine 100 OS-Prozesse.
PostgreSQL bleibt eine spätere Migration für mehrere Rechner, kein vorgetäuschter
Bestandteil dieser Installation. Frontend und API werden gemeinsam lokal ausgeliefert.

## Phasen und Abnahmekriterien
1. Laufzeitumgebung, Datenbank, geschützte API, Start/Stopp, Backup.
2. Offizielle SDKs, feste Paper-URL, echte Verbindungsdiagnostik, Kostenreservierung.
3. Zentraler IEX/SIP-Stream, Zeitstempel, Historie, News, EZB-FX, EDGAR.
4. Getrennte Ledgers, atomare Reservierung, idempotente Ausführungen,
   unabhängige Risikolimits, reproduzierbare Tests mit Folgetagsausführung.
5. 100 persistente Profile, Strategien, Gedächtnis, Analysen und Aufgaben.
6. 25 Demo-Portfolios, ein 3.000-EUR-Fonds, 25 Fund-Agenten; interne Simulation
   und separate Broker-Validierung mit eindeutigen Kennzeichnungen.
7. Datenbasierte Bewertung, gehaltene Rollen bei unzureichender Evidenz,
   vorbereitete Tauschentscheidungen mit Wirksamkeitsdatum.
8. Manager-Chat über kontrollierte Datenabfragen; Bestätigung administrativer Aktionen.
9. Alle Dashboard-Bereiche mit tatsächlichen Daten und ehrlichen Leerzuständen.
10. Tagessteuerung, Wiederanlauf, Authentifizierung, Windows-Watchdog, Tests.

## Externe Abhängigkeiten
OpenAI-Schlüssel und Alpaca-Paper-Schlüsselpaar trägt der CEO lokal ein.
Live-Abnahmen bleiben bis dahin blockiert. Erster automatischer Handel bleibt
zusätzlich bis zur Bestätigung der konservativen Risikolimits gesperrt.
Kein Konto wird gekauft oder umgestellt. Fernzugriff wird ohne separate sichere
Verbindung nicht veröffentlicht. Öffentliches Hosting mit Offline-Snapshot ist
eine gesonderte Integration; lokal wird der letzte Snapshot im Browser gespeichert.

## Fortsetzung
STATUS.md enthält Abnahmebefunde, START.md Bedienung und fehlende Angaben.
Nach abgeschlossenen Entwicklungsphasen lokale Git-Checkpoints anlegen.
