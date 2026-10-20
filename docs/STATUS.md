# Tatsächlicher Stand — 20.10.2026

## Neue Tagesroutine und Research-Ansicht — 22 Uhr Berlin

Abschlussprüfung: **166 Tests bestanden**, Produktionsbuild erfolgreich.
Alle 100 neuen Eigenbewertungen und die anschließende Manager-Tagesentscheidung
wurden im laufenden System tatsächlich gespeichert; keine nur simulierte Abnahme.

Die bestehende Engine bereitet ab 07:30 Berlin stündlich Nachrichten, Berichte
und Strategiehypothesen auf. Kandidatentests werden vor weiteren Analysen
abgearbeitet. Keine Änderung der Signal-, Daten-, Zeit-, Paper- oder Kapitalgrenzen.

Ein persistenter Tagesabschluss fordert Eigenbewertungen aller 100 Agenten an.
Anschließend trifft der Manager delegierte Paper-Personalentscheidungen, entweder
belegte Tausche zwischen benachbarten Abteilungen oder begründetes Beibehalten.
Aktivierung frühestens am nächsten Morgen, nur ohne offene Positionen/Orders;
50/25/25 bleibt erhalten. Gesperrte/unklare Modellaufgaben bleiben sichtbar offen.

Bei geschlossener Börse zeigt die Startansicht automatisch Research Lab,
Tagesberichte, Portfolio, Manageraktionen, individuelle Agenten und alle
paginierten Strategietests mit vollständigen Ergebnissen. Der echte Börsenstatus
bleibt unabhängig vom persönlichen Worker-Ende um 19 Uhr. Echte lokale API-
Prüfung inklusive beider neuen geschützten Datenendpunkte und Testpagination
erfolgreich. Weitere Details: [Agentenkonsole](AGENT_CONSOLE.md).

## Aktueller Abschlussstand — 22 Uhr Berlin

152 automatisierte Tests bestanden; Frontend-Produktionsbuild, authentifizierter
HTTP-Smoke-Test und Live-WebSocket erfolgreich. Die folgenden älteren Abschnitte
beschreiben Entwicklungsstände; bei Widersprüchen gilt dieser aktuelle Abschnitt.

- Bestehende Architektur 50/25/25, Paper-only, mindestens 15 Minuten und maximal
  25 % Kapital je Agent einschließlich offener Kaufreservierungen bleiben erhalten.
- Ausgewogenes ATLAS-Dashboard mit Portfolio, Organisation und Nachrichten;
  keine manuellen Trades/Uploads, kein Manager Office und kein Research Lab.
- Rechts im Trading Floor genau 25 Fonds-Trader. Profile zeigen tatsächliche
  Tagesaktionen, eigene gespeicherte Berichte und Managerbeurteilung 0–10.
- Alle 25 Fondsberichte und alle 100 Agentenbewertungen tatsächlich erzeugt;
  Einzelagenten verwenden GPT 6.1 Sol, der separate Manager GPT 5.4 Mini.
  Der Managementdienst läuft unabhängig vom Sitzungsende des Handelsworkers.
- 13.505 bestätigte handelbare Alpaca-US-Aktien/ETFs im Katalog. Kurse werden
  rotierend und bei Auswahl geladen; keine gleichzeitige globale Echtzeitabdeckung.
- 30 EUR monatliches KI-Budget, kein Tageslimit. Nach Tagesende keine neuen
  Handelsausführungen erzwingen. Bewertungen sind vorläufig, kein Gewinnnachweis.
- Private Supabase-Snapshots und Befehlswarteschlange eingerichtet. Das persönliche
  CEO-Auth-Konto muss noch vom Nutzer angelegt und freigeschaltet werden.

Details: [Agentenkonsole](AGENT_CONSOLE.md), [Cloud-Zugriff](CLOUD.md).

**Das Gesamtprojekt ist noch nicht vollständig extern abgenommen.** Die lokale
Anwendung ist implementiert. Fehlende Kontozugänge werden nicht durch Testdaten
oder erfundene KI-Ausgaben ersetzt.

## Lokal vorhanden und geprüft

Abschlussprüfung: **79 automatisierte Tests bestanden**, Frontend-Produktionsbuild
erfolgreich. Authentifizierter HTTP-Smoke-Test und echter WebSocket-Aktivitätsfeed
lokal erfolgreich; Ledger-Abgleich erfolgreich, Rollenverteilung weiterhin 50/25/25.

- Python 3.12, Node.js 24, Git, virtuelle Python-Umgebung und installierte SDKs.
- 100 dauerhaft gespeicherte Profile in genau 50/25/25 Abteilungen.
- 25 Demo-Ledgers und ein 3.000-EUR-Fonds; keine 25-fache Fondsfinanzierung.
- Geschützte API, lokaler Login, CSRF-/Origin-/Host-Prüfung, HttpOnly-Sitzung.
- Atomare Reservierung, getrennte Portfolios, idempotente interne Ausführungen,
  Rückgabe von Reservierungen, gedeckte Long-Positionen, Ausführungsherkunft.
- Strategie- und Datenqualitätsprüfung vor Order UND Fill. Standard HOLD,
  keine Inaktivitäts-/Zeitquoten. Untergrenze 15 Minuten, Verzögerungs-/Feed-
  Einschränkungen, persistentes Signal- und HOLD-Protokoll.
- Verlust-/Exposure-/Stop-/Konzentrationsgrenzen, Not-Aus, Schutzschließungen.
  Tech-Korrelationsbudget ist konservativ vorgegeben, keine empirische
  Echtzeit-Korrelationsmatrix. Stops garantieren keine maximalen Verluste.
- Kostenpflichtige KI-Aufgaben mit persistenter Queue, Kostenreservierung,
  Tages-/Monatsgrenze, Retries und getrenntem kontinuierlichem Risikomonitor.
- Manager-Werkzeuge, Datenbelege, Chatpersistenz, bestätigungspflichtige Vorschläge.
- Datierter Rollentausch zwischen benachbarten Abteilungen; offene Positionen
  verhindern den Wechsel. Startbesetzung wird als unbewertet angezeigt.
- Sichere Strategie-DSL, reproducible Bar-Backtests, Kosten, nächste-Bar-
  Ausführung, separate In-/Out-of-Sample-Abschnitte und feste Testfenster.
- CEO-Dashboard mit allen Menüpunkten, Agentendetails, tatsächlichen Daten,
  Leerzuständen und nachvollziehbaren Blockierungsgründen.
- Start/Stopp, Watchdog, Benutzer-Autostart, geplanter Worker-Tagesbetrieb,
  geprüfte SQLite-Backups und erfolgreicher lokaler Wiederanlauf.
- Echter öffentlicher EZB-Kursabruf erfolgreich: mit Datum und Quelle gespeichert.
- Beide API-Schlüssel lokal hinterlegt, außerhalb von Git. Echte OpenAI-Responses-
  Anfrage erfolgreich; Agent 017 hat eine reale Analyse und einen Gedächtniseintrag
  gespeichert. Der Manager hat Fondsstand, Orderzahl und Risikostatus mit tatsächlich
  ausgeführten Datenabfragen beantwortet. Weitere Forschungsanalysen laufen budgetiert.
- Alpaca-Paper-Konto ACTIVE authentifiziert. Börsenkalender, 10 echte Quotes,
  zentraler IEX-Stream, 251 SPY-Tagesbars, 1.739 abgeschlossene 15-Minuten-Bars
  sowie zunächst 50 News tatsächlich geladen. Ein Research-Backtest auf echten
  Alpaca-IEX-Bars mit getrenntem OOS-Abschnitt wurde dauerhaft gespeichert.
- Die echten Tests deckten einen Responses-Tool-Serialisierungsfehler auf. SDK-
  Outputfelder werden jetzt ausdrücklich auf den gültigen Inputvertrag abgebildet;
  verschlüsselte Reasoning-Zustände werden bei stateless Tool-Runden übertragen.
  Für beides bestehen Regressionstests. Keine internen Denkprozesse werden angezeigt.
- Browserprüfung der Navigation aller Hauptbereiche, Suchfilter, Agentendetail
  und sichtbarer OpenAI-Blockierung in einer isolierten Instanz ohne API-Schlüssel.

## Noch nicht abgenommen / freigegeben

| Funktion | Was fehlt |
|---|---|
| Echte Broker-Paper-Testorder/-Bestätigung | Marktöffnung, frische Quote und ausdrückliche Testfreigabe; es wurde noch keine Brokerorder gesendet |
| Autonomer Paper-Handel | Freigegeben und mit echten Signal-/Quote-Daten intern ausgeführt; neue Einstiege bleiben signal-, daten- und risikoabhängig. KI-Budget sperrt die Strategieausführung nicht mehr. |
| SEC Companyfacts | Echte Kontaktangabe für SEC_USER_AGENT und erfolgreicher Abruf |
| Belastbare Rankings/Beförderungsevidenz | Tatsächliche ausreichende Handels-/Equity-/OOS-Stichproben |

SDK-Transporttests verwenden explizite Testantworten. Davon getrennt sind die
oben aufgeführten echten Konto-/Daten-/Reasoning-Tests. Historische Simulationen
werden nicht als tatsächlich gehandelte Fondsgewinne ausgewiesen.

## Bewusste Einschränkungen / weitere Arbeit

- Öffentliches Vercel-Frontend vorhanden; API, Ledger und Worker weiterhin lokal.
  Kein LAN-/geschützter Fernzugriff und kein externer Offline-Snapshot-Host
  eingerichtet. Lokaler Browser-Cache ist nur eine Ansicht
  des letzten geladenen Zustands, kein erreichbarer Server bei ausgeschaltetem PC.
- Keine lizenzierte Echtzeit-Social-/Truth-Social-Quelle und kein vollständiger
  Wirtschaftskalender. Kein garantiertes Nachrichten-Latenzziel.
- Automatische Dividenden-/Splitbuchungen sind nicht freigegeben. Standard ist
  Tageshandel ohne Overnight; ungeschlossen gebliebene Positionen sind Ausnahmen.
- Backtests sind keine biasfreie Marktuniversumsstudie: Watchlist-Survivorship-
  Risiko bleibt dokumentiert. Kein unbeschränktes autonomes Python-Ausführen,
  keine wissenschaftlich abgeschlossene Strategievalidierung oder echtes Fine-Tuning.
- Fund-Agenten-Equity verwendet ein **analytisches** 120-EUR-Referenzkapital je
  Agent für Beiträge; diese Referenz ist kein zusätzliches Ledger-Geld. Demo-
  Performance und frühere Rollen dürfen nicht als Fondsvermögen zusammengezählt werden.
- Ein abrupt ausgeschalteter PC kann keine offenen Orders/Positionen schließen.
  Persistenz und Wiederabgleich sind implementiert; Netzwerk- und Stromausfälle
  können weiterhin offene Paper-Positionen hinterlassen. Keine gegenteilige Garantie.
- Windows verweigerte die Task-Scheduler-Registrierung. Benutzer-Autostart-Link
  wurde als funktionierender Weg ohne zusätzliche Rechte eingerichtet.
- Zwei Upstream-Deprecation-Warnungen aus Starlette/httpx und Alpaca/websockets;
  derzeit kein Testfehler. Ein späteres SDK-Upgrade benötigt erneute Vertragsprüfungen.

## Freigabe durch CEO

**Neueste Kapitalvorgabe, 20.10.2026:** Maximal 25 % Kapital pro Trader, über
alle eigenen Positionen und offenen Kaufreservierungen zusammen. Prüfung vor
Reservierung, erneut vor Fill und in der laufenden Schutzkontrolle. Es zählt
konservativ der höhere Wert aus gebundenem Kapital und bewerteter Position.
Größere Altpositionen erhalten einen deterministischen Schutz-Teilverkauf mit
kleinem Puffer unter der Grenze, ohne Signal-/Daten-/Ledgerprüfungen zu umgehen.
Die größere NVDA-Position von Agent 95 wurde um 8,380575 Stück reduziert.
Eine zwischenzeitliche API-Schemaablehnung ist korrigiert: alle Felder des
strikten Agentenantwortschemas, auch position_pct, werden als erforderlich gesendet.

**Neuester Budgetauftrag, 20.10.2026:** Tägliches OpenAI-API-Limit entfernt.
30 EUR Monatsbudget bleibt atomar durchgesetzt. Historische Tageskosten und
unklare Reservierungen bleiben vollständig erhalten; Tageskosten blockieren
keine weiteren Anfragen. Die unten beschriebenen Tageslimits sind Altstände.

**Aktualisierung 20.10.2026, 18 Uhr Berlin:** Der CEO hat die festen Positions-,
Exposure- und Verlustbudgets für interne Paper-Experimente aufgehoben.
`paper_sizing_mode=strategy` verwendet den selbst gewählten Strategieparameter
`position_pct` auch im Backtest. Bestehende Strategien ohne Parameter verwenden
wie bisher im Backtest das verfügbare Kapital; bis zu 100 % sind möglich.
Kein Kredit, kein Short, keine erfundenen Signale und keine ungeeigneten Daten.
Die folgenden ursprünglichen Eurogrenzen bleiben nur als reversibler Altstand
gespeichert. OpenAI-Budget bleibt unverändert.

Monatsbudget 30 EUR und beide API-Zugänge sind lokal eingerichtet und geprüft.
CEO hat am 20.10.2026 ausdrücklich „Paper-Handel mit diesen Grenzen freigeben“
bestätigt. Die Freigabe ist dauerhaft protokolliert und über die authentifizierte
API aktiviert. Zusätzliche feste Fondsobergrenzen: Position 240 EUR, Exposure
1.800 EUR, Tagesverlust 60 EUR, Drawdown 240 EUR, geplantes Stop-Risiko je Position
15 EUR. Es gilt jeweils auch die bestehende, gegebenenfalls strengere Prozentgrenze.
Diese festen Eurogrenzen steigen bei Kapitalwachstum nicht automatisch mit.

Bei der Freigabe am 20.10.2026 war das lokale Tages-Kostenbudget von 1 EUR
mit einer konservativen Kostenobergrenze von rund 0,9998 EUR praktisch verbraucht.
Neue KI-Aufgaben bleiben deshalb heute gesperrt. Unklare frühere Anfragen zählen
weiter konservativ; es wurden keine unbekannten Kosten gelöscht. Überwachung,
deterministische Signal-/HOLD-Prüfung und Sicherheitskontrollen laufen weiter.
Es gibt keine Bestätigung, die den Paper-only-Modus aufheben könnte.

## Orderausführung und Login — 20.10.2026, 17 Uhr Berlin

- Fehler korrigiert: Der Signalmonitor wartete bisher auf eine weitere KI-Analyse,
  deren Tagesbudget ausgeschöpft war. Die gespeicherte Strategie führt jetzt
  unabhängig von Modellverfügbarkeit und KI-Budget zum risikogeprüften Paper-Auftrag.
- Reguläre Intraday-Bars werden mit dem echten Sitzungskalender abgegrenzt.
  Sparse Vor-/Nachbörsendaten erzeugen keine falsche reguläre Datenlücke.
  Tatsächliche Lücken und ungeeignete Feeds sperren unverändert.
- Laufende Engine hat am 20.10.2026 ab 17:01 Berlin interne Paper-Fills für
  NVDA (Fund-Agent 85), SPY (Demo-Agent 61) und AMZN (Fund-Agent 76) gespeichert.
  Signalnachweis und Ledger-Abgleich geprüft. Keine Alpaca-Brokerfills behauptet.
- Trading Floor zeigt Handelssignale, Ausführungsablehnungen und Fillzahl.
  HOLD-Entscheidungen bleiben ausschließlich im Audit gespeichert und werden in
  den normalen UI-Listen ausgeblendet.
- Lokaler Passwort-Login, sämtliche Datenendpunkte und authentifizierter WebSocket
  funktionieren im Smoke-Test. Die Vercel-Website hat keine angeschlossene API;
  statt eines kaputten Passwortformulars führt sie zur lokalen geschützten Konsole.
- Die frühere reine lokale Login-Lösung wird durch Supabase Auth, private
  Snapshots und eine authentifizierte Befehlswarteschlange ergänzt. Schema und
  Synchronisation funktionieren; CEO-Konto/Freischaltung stehen noch aus.
  Details: CLOUD.md. Servergeheimnisse bleiben ausschließlich lokal.

## Konsole und Nachrichten — 20.10.2026

- Vermögenskurve: echte Zeitachse, lesbare Euro-Achse, keine falschen Zacken aus
  alten Einstandskosten-Fallbacks. Bestätigte Punkte durchgezogen, Verbindungen
  über Bewertungslücken gestrichelt; aktueller Endpunkt entspricht dem Fonds-KPI.
  Letzte bestätigte Kurse werden für neue unvollständige Bewertungen bewahrt,
  dürfen aber keine frischen Ausführungskurse ersetzen. Auditdaten unverändert.
- Manager: kurze Faktenantworten direkt aus Systemdaten, dauerhafte Hintergrundjobs,
  persistierte Antworten auch bei geschlossenem Fenster, idempotente Speicherung.
  Ausgeschöpftes KI-Budget wird konkret gemeldet, nicht durch Fantasieantworten ersetzt.
- Realisierter/unrealisierter P&L farblich hervorgehoben. Jeder Agent hat einen
  aus Positionen, Warteschlange, Sitzung, Daten und Worker abgeleiteten Status.
- Bewertungen aktualisieren sich; fehlende Evidenz wird als Aufbaufortschritt
  statt erfundenem Score gezeigt. Research-OOS-Ergebnisse bleiben separat.
- Ein zentraler, authentifizierter Alpaca-News-WebSocket abonniert `news:["*"]`.
  Alle 100 Agenten haben denselben Feed und können weitere Meldungen paginieren.
  REST-Fallback jede Minute; keine Beschränkung auf die Handelswatchlist.
  Keine Garantie für sämtliche Weltnachrichten oder ungenehmigte Datenquellen.
- 132 automatisierte Tests bestanden, einschließlich Order-Signalen, Datenqualität,
  neuem Paper-Sizing, News-Zugriff, Chat-Persistenz und Cloud-Befehlsvalidierung.
