# ATLAS — lokales KI-Forschungs- und Paper-Trading-System

Die Anwendung wurde im vorhandenen Projekt aufgebaut und anschließend um eine
verbindliche Signal-/HOLD-Prüfung ergänzt. **Kein Echtgeldmodus.**

## Öffnen

1. `Start.cmd` doppelklicken. Die Anwendung läuft unabhängig vom Browser.
2. Adresse: http://127.0.0.1:8765
3. Das lokal generierte CEO-Passwort steht in `local-access.txt`.
4. `Stopp.cmd` sperrt Einstiege, fordert sichere Schließungen an, stoppt den Worker
   und erstellt ein geprüftes Datenbankbackup. Bei fehlenden Ausführungsdaten
   wird eine offene Position als Ausnahme gespeichert, niemals als geschlossen erfunden.

## Deine noch nötigen Angaben

**Aktueller Stand:** OpenAI und Alpaca Paper sind inzwischen lokal konfiguriert
und mit echten Anfragen geprüft. Forschung und Manager funktionieren. Der CEO
hat die konservativen Risikolimits und den autonomen internen Paper-Handel am
20.10.2026 bestätigt; die Freigabe ist aktiviert. Tages-/Monatsbudget sowie
Signal-, Datenqualitäts- und Zeitkontrollen gelten weiterhin.
Die nachfolgende Anleitung dient auch späteren Schlüsseländerungen.

Die bereits erstellte `.env` im Projektordner öffnen. Nur diese Werte eintragen:

```dotenv
OPENAI_API_KEY=
ALPACA_PAPER_API_KEY=
ALPACA_PAPER_SECRET_KEY=
```

Keine Schlüssel in den Chat schicken. Die Alpaca-Schlüssel müssen aus dem
**Paper-Dashboard** stammen. Die Broker-Adresse ist unveränderlich festgelegt.
Danach `Stopp.cmd`, `Start.cmd`, dann unter Einstellungen die Verbindungen und
den echten OpenAI-Test prüfen. Der OpenAI-Test kann kleine API-Kosten verursachen.
Erst danach die angezeigten Risikolimits im Risk Center bestätigen und den
Paper-Handel explizit freigeben. Bis dahin bleiben Einstiege gesperrt.

Das freigegebene Budget ist **30 EUR/Monat**, ohne zusätzliches Tageslimit. Es wird
vor jedem Modellaufruf atomar reserviert; unbekannte oder unterbrochene Anfragen
bleiben konservativ angerechnet. Preisstand und Modell sind dokumentiert. Neue
Modelle benötigen eine geprüfte Preiskarte. Weitere Anbieterbudgets/-warnungen
im OpenAI-Projekt selbst setzen; es wurden keine Kontoeinstellungen geändert.

Optional für SEC EDGAR: `SEC_USER_AGENT=Organisation echte-kontaktadresse@example.org`
mit deiner tatsächlichen Kontaktadresse eintragen. Ohne diesen Eintrag bleibt
EDGAR blockiert. Zusätzliche Nachrichten-/Social-Media-Abos wurden nicht gebucht.

## Aufbau

- 50 Research-Agenten, 25 unabhängige Demo-Ledgers, 25 Fund-Trader.
- **Ein** gemeinsamer Fonds mit 3.000 EUR virtuellem Anfangskapital.
- Python/FastAPI, React/TypeScript, SQLite WAL mit Transaktionssperren und
  Mikro-EUR-Beträgen; lokaler Watchdog, ein KI-Aufruf gleichzeitig.
- Eigene Profile, Gedächtnis, Strategieversionen, Backtests und Ereignishistorien.
- Manager mit kontrollierten Datenabfragen; Änderungen benötigen CEO-Bestätigung.
- Offizielle OpenAI- und Alpaca-SDKs, ein zentraler Quote-Stream, inkrementelle
  verzögerte 15-Minuten-Bars, Historie/News sowie öffentliche EZB-/SEC-Schnittstellen.

## Handelsregeln

Standard ist **HOLD / NO TRADE**. Kein Einstieg wegen langer Inaktivität oder
eines Zeitplans. Agenten dürfen Wochen ohne Trade bleiben. Alle Strategien haben
mindestens einen 15-Minuten-Zeitrahmen. Ein Signal muss vor Reservierung und
unmittelbar vor Ausführung nachgewiesen werden. [Details](docs/SIGNAL_POLICY.md).

Die Datenpolitik berücksichtigt mindestens 15 Minuten Alpaca-Verzögerung.
Diese Bars können zu verzögerungstoleranten Strategien passen. Für einen aktuellen
Fill ist unabhängig eine tatsächlich frische Quote erforderlich; 15 Minuten alte
Quotes erzeugen keinen angeblich aktuellen Trade. Echtzeitstrategien und
Gesamtmarktstrategien ohne passenden Feed werden gesperrt. IEX ist ein Teilmarkt.

Automatische Schutzkontrollen laufen auch während der KI-Wartezeit. Stops sind
Risikomechanismen, keine Garantie gegen Kurslücken. Keine Shorts, kein Pyramiding,
keine Overnight-Einstiege, keine Freigabe von produktivem Python-Code durch KI.
Die sichere Strategie-DSL unterstützt Momentum, Mean Reversion, MA und Breakout.

Berlin: 07:30 Vorbereitung, tatsächlicher Börsenstart aus Alpaca-Kalender,
18:25 Schließungen, 18:30 Review, 19:00 Worker-Ende und Backup. Der lokale
Webserver bleibt bei eingeschaltetem PC zum Einsehen des Stands verfügbar.
Ohne PC gibt es keinen lokalen Webserver und keine Hintergrundarbeit.

## Speicherung und Betrieb

- `data/fund.sqlite3`: Hauptdatenbank (nicht manuell bearbeiten).
- `backups/`: geprüfte SQLite-Snapshots, die letzten 30 bleiben erhalten.
- `logs/`: API-/Worker-Diagnosen, keine API-Schlüssel.
- `.env`, Daten, Backups und `local-access.txt` sind von Git ausgeschlossen.
- Windows-Aufgabenregistrierung wurde vom Betriebssystem verweigert. Stattdessen
  ist ein **Autostart-Link für diesen Windows-Benutzer** eingerichtet. Nach der
  Anmeldung startet der Supervisor den Worker ab 07:30 Berlin. Er weckt keinen PC
  und umgeht keine Windows-Anmeldung. Fehlerhafte Prozesse werden neu gestartet.
- Ein manuell pausierter Worker wird erst mit `Start.cmd` wieder freigegeben.

Die Vercel-Konsole kann private Snapshots und Befehle über Supabase verwenden.
Schema und lokale Synchronisation sind eingerichtet; das persönliche CEO-Konto
muss noch erstellt und explizit freigeschaltet werden. Die lokale API bleibt auf
Loopback. Bei ausgeschaltetem PC sind gespeicherte Cloud-Snapshots erreichbar,
neue Trades benötigen weiterhin die lokale Engine. Einrichtung und Grenzen:
[Private Cloud-Konsole](docs/CLOUD.md).

Im freigegebenen Paper-Experimentiermodus wählen Strategien ihre Positionsanteile
selbst (`position_pct`, gleicher Parameter im Backtest). Keine festen Eurobudgets;
die neu bestätigte Obergrenze beträgt jedoch 25 % Kapital je Agent über alle
seine Positionen und offenen Kauforders zusammen. Der Backtest darf hypothetische
Anteile untersuchen; die Ausführung begrenzt sie auf diese gemeinsame Obergrenze.
Signal-, Datenqualitäts-, Liquiditäts- und Cash-Prüfungen bleiben verpflichtend.
Ein zentraler Live-Alpaca-News-Feed steht allen 100 Agenten zur Verfügung.

## Technische Prüfung und Fortsetzung

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\smoke_local.py
cd frontend
npm run build
```

`Installation.cmd` kann die lokale Umgebung erneut installieren und prüfen.
Python-Abhängigkeiten sind in `requirements.lock.txt`, Frontend-Abhängigkeiten
in `frontend/package-lock.json` festgehalten.

[Tatsächlicher Funktionsstatus](docs/STATUS.md), [Projektplan](docs/PLAN.md),
[Signalregeln](docs/SIGNAL_POLICY.md).
Der persönliche Originalauftrag bleibt lokal in `docs/MASTER_PROMPT.md`.
Die lokale Git-Historie enthält die Entwicklungs-Checkpoints. Veröffentlichter
Quellcode: [deumont/HedgeFund](https://github.com/deumont/HedgeFund). Neue geprüfte
Codeänderungen werden entsprechend dem CEO-Auftrag ebenfalls dort gespeichert.
Private Zugangsdaten und Betriebsdaten sind von der Veröffentlichung ausgeschlossen.

## Verwendete offizielle Referenzen

- [OpenAI Responses API](https://developers.openai.com/api/reference/python/resources/responses)
- [Modell und Preiskarte](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Alpaca Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca Marktstream](https://docs.alpaca.markets/us/docs/streaming-market-data)
- [Alpaca SDK und Kalender](https://alpaca.markets/sdks/python/api_reference/trading/calendar.html)
- [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [EZB-Wechselkurse](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml)
