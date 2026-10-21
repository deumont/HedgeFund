# Signal-gesteuerter Handel — Ergänzung vom 20.10.2026

Bestehende Architektur und Daten bleiben erhalten: 50 Research-, 25 Demo- und
25 Fund-Agenten. Identitäten, Gedächtnis, Strategieversionen und Ledgers werden
nicht neu erzeugt oder zurückgesetzt.

## Verbindliche Regeln

- Standard ist **HOLD / NO TRADE**. Keine Mindestzahl von Trades und kein
  Einstieg wegen verstrichener Zeit oder langer Inaktivität.
- Jeder Agent nutzt seine gespeicherte, versionierte Strategie. Normale Einstiege
  benötigen deren deterministisch ausgewertete technische Bedingung.
- Mindestens 15 Minuten je Strategie. Kleinere Zeitrahmen sind gesperrt, auch
  wenn ein Modell sie vorschlägt. Neue Strategien dürfen erst nach einem danach
  abgeschlossenen Bar gehandelt werden.
- Der zentrale Alpaca-Bar-Abruf berücksichtigt konservativ mindestens 15 Minuten
  Datenverzögerung. Es werden nur abgeschlossene und bereits verfügbare Bars
  ausgewertet. Die tatsächlichen verfügbaren Daten bleiben abhängig vom Konto.
- Echtzeitstrategien sind mit dieser verzögerten Datenpolitik gesperrt.
  Gesamtmarktstrategien bleiben auf IEX gesperrt. Fehlende, alte, zukünftige,
  überlappende oder lückenhafte Bars erzeugen HOLD.
- Verzögerte Bars können ein zulässiges Strategiesignal liefern. Sie werden
  **niemals als aktueller Ausführungspreis** verwendet: die bestehende Ledger-
  Prüfung verlangt unabhängig eine frische echte Quote, FX, Sitzung, gedeckte
  Positionen, Kapital und Risikofreigabe. Mit ausschließlich 15 Minuten alten
  Quotes werden keine aktuellen Ausführungen behauptet.
- Ein gültiges Signal allein erzwingt keinen Trade. Das Risikosystem kann
  ablehnen, und Liquidität kann eine Ausführung verhindern. Gespeicherte
  Strategien werden ohne zusätzlichen kostenpflichtigen KI-Aufruf ausgeführt;
  das KI-Budget begrenzt Forschung, nicht die technische Orderausführung.
- Vor Reservierung und unmittelbar vor Ausführung wird die Strategie erneut
  geprüft. Fehlender Signalnachweis, Strategieänderung oder ungültig gewordenes
  Signal verhindert den Fill und gibt reserviertes Kapital frei.
- Pro Agent, Aktie und abgeschlossenem Bar wird derselbe Einstieg nicht mehrfach
  gehandelt. Bestehende Positionen erzeugen kein automatisches Nachkaufen.
- Schutzstops, Take Profit, Not-Aus und 18:25-Liquidation sind ausdrücklich
  vordefinierte Ausstiegsbedingungen. Sicherheitsprüfungen laufen häufiger als
  alle 15 Minuten; sie verkürzen nicht den Strategie-Zeitrahmen.

## Dauerhafte Nachweise

`signal_decisions`: Agent, Strategieversion, Zeitrahmen, Datenpolitik, Bar-Hash,
verwendete Preise/Indikatoren, Aktion und Begründung, auch HOLD.
`order_signals`: eindeutige Verbindung jeder internen Order mit dem Signalnachweis.
`events`: zusätzliche finale Handelsentscheidung und Risiko-/Datenablehnungen.
Identische Monitorabfragen werden innerhalb desselben 15-Minuten-Datenzustands
zusammengefasst. Beobachtung ist keine erfundene neue Entscheidung.

Alle 50 Trader werden während ihrer Sitzung alle zehn Sekunden lokal geprüft;
ein zentraler inkrementeller 15-Minuten-Bar-Abruf läuft höchstens einmal pro Minute.
Reguläre Sitzungen aus dem Alpaca-Kalender begrenzen die Intraday-Signalreihe.
Lücken zwischen einzelnen Vor-/Nachbörsenbars sind keine Lücken der regulären
Sitzung; fehlende Bars innerhalb der regulären Reihe sperren weiterhin.
Ein gültiges Signal wird unmittelbar mit konservativer Größe und den Stop-%
der gespeicherten Strategie an das interne Ledger übergeben. Take Profit liegt
zwei Stop-Abstände über dem Einstieg. Kein Nachkaufen bestehender Positionen.
Kapital, Konzentration, Exposure, Verluste und Stop-Risiko werden auch beim Fill
erneut geprüft. Derselbe Bar erzeugt keine mehrfachen Einstiege.
Research und Tagesberichte bleiben budgetiert. Alle Ausführungen sind interne
Paper-Simulationen; sie werden nicht als Alpaca-Brokerorders ausgegeben.

## Prüfungen

`tests/test_signal_gate.py` prüft fehlende Signale, beliebig lange Inaktivität,
unabhängige Strategien, ungeeignete Feed-/Verzögerungsanforderungen, veraltete
Quotes, fehlerhafte Bars, Untergrenze 15 Minuten sowie erneute Prüfung beim Fill.
Transporttests verwenden ausdrücklich Testantworten. Echte Alpaca-/OpenAI-
Kontoberechtigungen sind ohne lokale Schlüssel weiterhin nicht abgenommen.

Daily objective (21 October 2026): Active demo/fund agents seek at least one new position per exchange trading day. Verified absence of a suitable opportunity is an allowed exception, reviewed by the manager with search/signal/execution evidence. Research is exempt. Extra candidate scans retain independent strategy and risk gates; no timer grants order permission. Only gaps inside the actual decision lookback can invalidate that decision; older unrelated gaps remain in historical data.
