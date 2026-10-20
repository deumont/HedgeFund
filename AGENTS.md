# Projektregeln

## GitHub-Synchronisierung — ausdrücklicher CEO-Auftrag

Ziel: https://github.com/deumont/HedgeFund (öffentlich), Branch `main`.
Nach jeder abgeschlossenen, passend geprüften Codeänderung den lokalen Stand
committen und den neuen Code dorthin veröffentlichen. Keine erneute Zustimmung
für gewöhnliche Quellcode-Updates erforderlich. Ein fehlgeschlagener Upload ist
als solcher zu melden; lokale Commits ersetzen keinen bestätigten Upload.

- Vor jeder Veröffentlichung `python scripts/check_publish.py` mit der lokalen
  `.venv` ausführen. Der Scanner gibt keine Geheimniswerte aus.
- Ausschließlich den geprüften, versionierten Quellcode veröffentlichen.
  `.env`, Schlüssel, `local-access.txt`, Datenbanken, Logs, Backups und der
  persönliche Originalauftrag `docs/MASTER_PROMPT.md` bleiben lokal.
- Die lokale Git-Historie bewahren. Keine Force-Pushes, keine fremden Commits
  überschreiben, keine privaten Dateien nur für einen Upload freigeben.
- Der initiale Upload verwendet die bereits autorisierte GitHub-Verbindung,
  weil die Windows-Git-Anmeldung noch nicht eingerichtet ist. Auf GitHub werden
  versionierte Quellcode-Snapshots auf `main` geführt; die feinere lokale Historie
  bleibt erhalten. Folge-Uploads über denselben Connector: aktuellen Remote-Head
  lesen, vollständigen geprüften HEAD-Baum veröffentlichen, Commit mit diesem
  Remote-Head als Parent erstellen, Ref nur mit erwarteter SHA aktualisieren.
  Lokale Quellcommit-SHA in die Commitnachricht aufnehmen und abschließend den
  veröffentlichten Tree mit dem lokalen HEAD-Tree vergleichen.
- Wenn reguläres `git push` später authentifiziert wird, zunächst die bestehenden
  Historien korrekt zusammenführen; niemals den Snapshot-Branch force-pushen.
- Keine Hintergrundüberwachung für beliebige Dateiänderungen einrichten. Diese
  Regel gilt für abgeschlossene Änderungen während der Arbeit an diesem Projekt.

## Handelsarchitektur bewahren

50 Research-, 25 Demo- und 25 Fund-Agenten. Paper-only, HOLD als Standard,
mindestens 15-Minuten-Zeitrahmen. Keine Order ohne deterministisches Signal,
geeignete Marktdaten und unabhängige Risiko-/Kapitalprüfung. Die bestätigten festen
Fondsgrenzen und API-Budgets respektieren. Keine erfundenen Integrationsberichte.

CEO-Änderung vom 20.10.2026: Im ausdrücklich freigegebenen internen Paper-Modus
`paper_sizing_mode=strategy` wählen die Strategien `position_pct` selbst; feste
Euro-, Allokations- und Verlustbudgets sind dort aufgehoben. Verfügbares virtuelles
Kapital, Reservierungen, Liquidität, valide Signale, Datenqualität, mindestens
15-Minuten-Zeitrahmen und Paper-only bleiben zwingend. API-Budgets unverändert.

CEO-Budgetänderung vom 20.10.2026: Das zusätzliche tägliche OpenAI-Limit entfällt.
Das monatliche Limit bleibt 30 EUR; atomare Reservierungen und die konservative
Anrechnung unklarer Anfragen bleiben erhalten. Tageskosten sind nur eine Statistik.

Neuester CEO-Auftrag: Jeder Trader darf höchstens 25 % seines Portfolios nutzen
(Fund: gemeinsames Fondsvermögen; Demo: eigenes virtuelles Portfolio). Alle
Positionen und offenen Kaufreservierungen des Agenten zusammen zählen. Diese
Obergrenze gilt auch im Strategie-Modus. Überhöhte bestehende Positionen werden
mit geeigneten Daten kontrolliert reduziert; keine erfundenen oder veralteten Fills.

Weitere CEO-Aufträge: Einzelagenten verwenden gpt-6.1-sol; Managerbewertungen
rollieren 0–10, sind als vorläufige Beurteilung statt Gewinnnachweis bezeichnet.
Alle bestätigten handelbaren Alpaca-US-Aktien sind auswählbar; Echtzeitabdeckung
nicht behaupten. Website ohne manuelle Trades/Uploads, Manager Office und Research
Lab. Bestehende Architektur 50/25/25 erhalten. Visuell wieder näher am ursprünglichen
ATLAS-Dashboard, mit weniger Verwaltungsbedienung. Rechts im Trading Floor genau
25 Fonds-Trader; Profile zeigen Tagesaktionen und eigene belegte Tagesberichte.

Neuester CEO-Auftrag: Ab 07:30 Berlin wiederholte Vorbereitung mit Nachrichten,
Berichten, Strategieverbesserungen und Backtests. Nach dem persönlichen Handelsende
Eigenbewertungen aller 100 Agenten; danach delegierte tägliche Managerentscheidung
über belegte Auf-/Abstiege oder Beibehalten. Automatische Tausche zwischen Nachbar-
abteilungen dürfen frühestens am Folgetag vor Börsenöffnung wirksam werden und
bewahren 50/25/25. Offene Positionen/Orders verschieben einen Wechsel. Keine
erzwungenen Trades oder Rollenwechsel. Bei geschlossener Börse automatisch eine
Research-/Review-Ansicht, dort Research Lab wieder sichtbar. Keine manuellen
Orders/Uploads und kein Manager Office. Der tatsächliche Börsenkalender bestimmt
die Dashboardumschaltung, nicht die persönliche Worker-Endzeit.
