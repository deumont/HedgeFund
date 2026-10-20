# Tatsächlicher Stand — 20.10.2026

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
- Trading Floor zeigt nun Signal-/HOLD-Gründe, Ausführungsablehnungen und Fillzahl.
- Lokaler Passwort-Login, sämtliche Datenendpunkte und authentifizierter WebSocket
  funktionieren im Smoke-Test. Die Vercel-Website hat keine angeschlossene API;
  statt eines kaputten Passwortformulars führt sie zur lokalen geschützten Konsole.
- Für geräteübergreifenden Login fehlt weiterhin ein geschützter Backend-Host.
  Deployment-Details: DEPLOYMENT.md. Zugangsdaten bleiben ausschließlich lokal.
