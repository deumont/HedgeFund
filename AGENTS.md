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
