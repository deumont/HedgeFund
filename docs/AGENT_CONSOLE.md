# ATLAS Agentenkonsole — 20.10.2026

Die bestehende Handelsarchitektur bleibt erhalten: 50 Research-, 25 Demo- und
25 Fonds-Agenten. Dashboard, Trading Floor, Portfolio, Agenten, Manager, Markt
und Status bilden die lesende Oberfläche. Manager Office, Research Lab, manuelle
Broker-Orders und Uploadformulare sind entfernt; Broker-/Import-POSTs werden
zusätzlich serverseitig abgewiesen. Der Not-Aus bleibt als Schutzfunktion erhalten.

## Modelle und Kosten

Einzelagenten und ihre Tagesberichte verwenden `gpt-6.1-sol`, Responses API,
Reasoning low und ausdrücklich Standard-Service-Tier. Kontozugriff und ein echter
Agentenbericht sind geprüft. Der separate Manager verwendet weiterhin
`gpt-5.4-mini`. Verifizierte Standard-Preiskarten, USD je Million Input/Output:
Sol 2/10, Mini 0,75/4,50. Atomare Monatsreservierungen bleiben auf 30 EUR begrenzt;
kein Tageslimit. Unklare Kosten bleiben angerechnet, kein kostenfreier KI-Betrieb
oder unbegrenzte Nutzung wird behauptet.

Quelle: https://developers.openai.com/api/docs/models/gpt-6.1-sol

## Bewertungen und Tagesberichte

Ein unabhängiger Managementdienst in der vorhandenen API verarbeitet maximal
zwei Berichts-/Bewertungsjobs gleichzeitig. Er kann keine Orders ausführen.
Der Manager geht alle fünf Minuten rollierend zehn Agenten durch, solange PC,
API, KI-Freigabe und Monatsbudget verfügbar sind. Der Handelsworker behält seine
Sitzungsgrenzen; sein Tagesende beendet keine bereits gespeicherte Berichtsaufgabe.

Managerbewertungen 0–10 werden tatsächlich vom Modell anhand gespeicherter
Kennzahlen, Forschung und Regelbefolgung erstellt. Sie sind eine vorläufige
qualitative Beurteilung, getrennt vom statistischen Performance-Evidenzstatus.
Keine Handelsquote und keine Abwertung allein wegen korrektem Nicht-Handeln.
Fehlende Bewertungen werden als ausstehend angezeigt, nicht erfunden.

Jeder Agent kann seinen eigenen Tagesbericht schreiben. Belegt werden Fills,
Ordergründe und gespeicherte Signalindikatoren sowie Analysen und Backtests des
Berliner Kalendertags. Berichte sind in Ich-Form und nennen belegte Gründe statt
interner Denkprozesse. Erfundenen Beleg-IDs wird nicht vertraut. Unveränderte
Tagesdaten erzeugen keine erneute Modellrechnung. Tagesaktionen bleiben gesondert
aus dem Ledger sichtbar. Alle 25 Fondsberichte und alle 100 Bewertungen wurden
im laufenden System tatsächlich gespeichert; laufende Updates haben eigene Zeiten.

## Aktienauswahl und Daten

Der bestätigte Alpaca-Katalog enthält beim Test 13.505 handelbare US-Aktien/ETFs.
Es gibt keine feste Zehn-Aktien-Handelsbeschränkung mehr. Agenten können über
`read_fund_data stocks` den paginierten Katalog lesen und eine bestätigte Aktie
auswählen. Kurse und abgeschlossene 15-Minuten-Bars werden zentral rotierend und
bei Auswahl nachgeladen; offene Positionen werden priorisiert. Ein Katalogeintrag
allein erlaubt keine Order. Signal-, Quote-, Spread-, FX-, Liquiditäts- und
25-%-Agenten-Kapitalprüfungen bleiben vor Reservierung und Fill verbindlich.

IEX ist weiterhin ein Teilmarktfeed. Es wird weder ein vollständiger globaler
Aktienkatalog noch gleichzeitige Echtzeitabdeckung aller Katalogwerte behauptet.
Das Bulk-Kataloglesen verarbeitet neue Börsenkennungen wie TXSE, ohne den gesamten
Katalog an einer älteren SDK-Enum scheitern zu lassen. Rohdaten werden ausschließlich
über den festen offiziellen Paper-Endpunkt gelesen, niemals als Code ausgeführt.
