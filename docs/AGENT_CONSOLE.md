# ATLAS Agentenkonsole — 20.10.2026

## Neu: Tagesroutine und geschlossene Börse

**Neueste Präzisierung:** Das Forschungsfenster ist täglich **07:30–15:30 Uhr
Europe/Berlin**, unabhängig von Sommerzeitverschiebungen der US-Börse. Start und
Speichern von Analysen, Backtests und Strategieanpassungen sind serverseitig
gesperrt, sobald dieses Fenster geschlossen ist. Offene Forschungsjobs warten
ohne Fehlversuch auf das nächste Fenster; nach Ablauf eintreffende vollständige
Modellantworten oder Tool-Konversationen werden als Entwurf gespeichert und beim
nächsten Fenster ohne erneutes Anfordern bereits vorhandener Ausgaben fortgesetzt.
Kursdaten, Nachrichten, Handelsschutz und abendliche Berichte/Personalentscheidungen
arbeiten weiter nach ihren gesonderten Regeln. Ältere Forschungsaufzeichnungen
aus der Zeit vor dieser Präzisierung werden nicht rückwirkend umgeschrieben.

Das Research Lab bleibt während und außerhalb der Börsensitzung erreichbar. Alle
100 Agenten können ausgewählt werden. Die Detailansicht aktualisiert lokal alle
fünf Sekunden, über Supabase alle 15 Sekunden: gespeicherte Arbeitsschritte,
Warteschlange, Analysehypothesen und Ergebnisse, vollständige Backtests sowie
Strategieversionen mit genauem Vorher-/Nachher-Vergleich. Keine erfundenen
Fortschrittsprozente oder internen Denkprotokolle. Ein Offline-Worker wird nicht
als laufende Forschung ausgegeben; Abfragen sind lesend und starten keine KI-Jobs.

Im AI Manager steht eine separate Teamhistorie: Vorschlag, beschlossen/geplant,
wegen Positionen/Orders zurückgestellt, Konflikt oder tatsächlich aktiviert mit
Zeitstempel. Beide beteiligten Agenten, vorherige/nächste Abteilung und Begründung
sind sichtbar. Tagesentscheidungen ohne Rollenwechsel bleiben gesondert lesbar.
Die Anzeige einer Planung behauptet keine bereits ausgeführte Beförderung.

Ab 07:30 Europe/Berlin laufen stündliche Vorbereitungsanalysen bis Börsenöffnung.
Agenten erhalten aktuelle Nachrichten, eigene Berichte, Managerbeurteilungen und
die letzte Personalentscheidung. Kandidaten werden weiter über die sichere DSL
und reproduzierbare Backtests geprüft. Die bestehende lokale Sitzung, Signale,
geeignete Ausführungsdaten und 25-%-Kapitalgrenze bleiben Ordervoraussetzungen.
Kandidatentests haben Vorrang vor der nächsten Analyse, damit die Forschungsqueue
sie nicht verdrängt. Signalindikatoren, Zeitangaben und Datenhashes bleiben im
Modellkontext; wiederholte vollständige Candle-Arrays bleiben im Audit statt den
nächsten Modellaufruf durch übergroße Eingaben zu blockieren.

Nach dem persönlichen Handelsende (18:30 Berlin, bei vorzeitigem Börsenschluss
früher) erstellt jeder der 100 Agenten eine Eigenbewertung: tatsächliche Aktionen,
Stärken, Schwächen und nächster Test. Ein dauerhafter Tagesabschluss wartet auf
alle Belege. Danach entscheidet der Manager über Auf-/Abstiege oder ausdrücklich
begründetes Beibehalten. Fehlende oder gesperrte Berichte bleiben sichtbar offen.
Keine automatische Wiederholung unklar abgerechneter Modellanfragen.

Für Research->Demo sind mindestens drei unterschiedliche positive OOS-Tests
über mindestens zwei Symbole mit je fünf geschlossenen Simulationstrades nötig.
Identische Wiederholungstests zählen einmal. Demo->Fonds verwendet die bestehenden
Mindestnachweise von 30 Abschlüssen, 20 Handelstagen und 20 Tagesrenditen. Dies sind
Zugangskriterien, keine Gewinnzusage oder tägliche Aktivitätsquote. Das Modell
entscheidet innerhalb dieser Grenzen. Jede Beförderung tauscht mit einem Agenten
der benachbarten Abteilung; die Besetzung bleibt 50/25/25. Aktivierung frühestens
am Folgetag vor Börsenöffnung; offene Positionen/Orders verschieben den Wechsel.
Nur diese täglichen Paper-Personalentscheidungen sind delegiert; Chatvorschläge
zu anderen administrativen Änderungen benötigen weiterhin die bestehende Freigabe.

Die Startansicht wechselt bei geschlossener Börse automatisch zu Research & Review:
Research Lab, Tagesberichte, Portfolio, Manageraktionen, individuelle Profile und
alle paginierten Strategietests inklusive Parametern und vollständigen Ergebnissen.
Research Lab ist damit gemäß neuestem Auftrag außerhalb der Börsenzeit wieder
vorhanden. Manuelle Orders, Uploads und Manager Office bleiben entfernt. Der
tatsächliche bestätigte Alpaca-Börsenkalender ist unabhängig vom Worker-Ende um
19 Uhr; ein fehlender Kalender wird nicht als bestätigter Börsenschluss ausgegeben.
PC/API und das monatliche Budget bleiben Voraussetzung der Hintergrundarbeit.

Die bestehende Handelsarchitektur bleibt erhalten: 50 Research-, 25 Demo- und
25 Fonds-Agenten. Dashboard, Trading Floor, Portfolio, Agenten, Manager, Markt
und Status bilden die lesende Oberfläche. Manager Office, Research Lab, manuelle
Broker-Orders und Uploadformulare sind entfernt; Broker-/Import-POSTs werden
zusätzlich serverseitig abgewiesen. Der Not-Aus bleibt als Schutzfunktion erhalten.

## Modelle und Kosten

Seit 21.10.2026 verwenden Forschung/Warteschlange und ihre Tagesberichte
`gpt-5.4-mini`; Demo/Fonds verwenden `gpt-6.1-sol`. Die aktuelle Abteilung wird
vor jedem Aufruf gelesen, deshalb wirken Auf-/Abstiege in beide Richtungen.
Einzelagenten und ihre Tagesberichte verwenden die Responses API,
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


## Individual public research and decision quality

The 50 news agents each have a distinct desk (backend/research_desks.py), starter
watchlist, catalyst question and suggested primary publisher. These are examples,
not ticker restrictions or automatic entries. All held stocks and open orders remain
watched, including stocks outside the desk. Feed evidence is checked every minute
during the trading session; hosted web background is refreshed on demand with a
one-hour per-agent/query cache. Morning research runs only in its existing window.

OpenAI Responses web_search uses the current role model, public queries only,
no browser login or arbitrary local HTTP fetch, at most two hosted calls per request.
The worker automatically researches the desk before its analysis, and the agent
can issue its own follow-up queries through research_public_web. Reports retain
provider-consulted sources and citation metadata. No guarantee of every website,
paywall access or complete live coverage. Retrieved pages are untrusted data.
Retrieval timestamps are not publication timestamps: web reports alone never bypass
the timestamped company-news signal gate. A missing web capability or budget is
reported honestly rather than replaced with invented research.

Web charges reserve 128k extra search-context tokens and USD 0.01 per permitted
hosted call (two max), plus ordinary request/output charges and the existing safety
margin. Settlement includes reported token usage plus a conservative fee for each
returned hosted call. Timeouts retain the reservation. The 30 EUR monthly cap stays.
Official references: https://developers.openai.com/api/docs/guides/tools-web-search
and https://developers.openai.com/api/docs/pricing (checked 21 October 2026).

Trading catalyst decisions record a causal case, counterevidence, priced-in
expectations, invalidation and source limitations before a signal can mature.
Source snapshots and dossiers are copied into fill-linked signal observations;
manager reviews use these, not a newer retrospective account. Trader rubric weights:
25 sources/timing, 25 causal case, 20 counterevidence, 20 risk, 10 uncertain outcomes.
Research rubric: 35 sources, 35 test design, 30 falsification/learning; no trading
permission and no penalty for zero orders. Scores remain provisional model judgments.
Daily mandatory staffing still preserves 25/25/50; fallback ties never rank profit.


## Calendar, career and historical manager evidence

Calendar days use Europe/Berlin boundaries including DST, the previous saved fund
valuation and that day's latest valuation. Unknown/incomplete endpoints and gaps
remain null, not invented zero returns. Realized fund fills are separate; demo
results do not affect fund P&L. Deposits/withdrawals are removed from valuation
changes, excluding initial virtual capital from the flow adjustment. Days remain
provisional without a post-personal-close mark. Tagesbeste means highest LAST
manager rating for that day (0-10), with ties and no fabricated winner.

GET calendar?month=YYYY-MM and agents/{id}/history?day=YYYY-MM-DD&month=YYYY-MM
are authenticated locally and synchronized on demand through the existing private
Supabase bridge. Existing RLS and command restrictions remain. History includes
daily trades, analyses, web research, strategy changes, cancellations and applied
team changes, with initial/applied career intervals. Role-history gaps are labeled.
Original fill portfolio IDs survive role changes. Historical profiles and reviews
use that day's role/time; current positions never appear as past holdings.

Managers receive cumulative per-role outcomes, trading sample sizes, recent
daily manager ratings, previous daily reports and career changes in reviews,
self-reports, daily staffing and data tools. Fallback staffing compares sustained
manager ratings rather than lucky P&L. Context excerpts are explicitly bounded;
all original records stay stored.

## Discretionary information management

The 50 news agents now use online research preparation instead of auto-queued
backtests. Pending automatic studies are superseded, completed studies preserved.
Rules-based/experimental agents retain their appropriate tests. Event-study
holding_bars is only a research reference under exit_mode=information; it does
not force an exit. Existing news strategies upgrade during the research window.

CatalystDecision persists intent enter/add/hold/reduce/exit, target allocation,
partial-exit fraction and prior causal/source dossier. Availability is still at
least 15 minutes; fresh company-linked event sources and suitable execution
quotes remain mandatory. A political post never unconditionally triggers a trade.
Same-source re-buy/add is rejected. Each thesis/action is consumed once by fills.

Event strategies can choose nullable stop_pct and take_profit_pct. Optional
price stops are accepted only in the authorized internal strategy paper mode.
The legacy NOT NULL positions.stop_usd field uses '0' solely as the no-price-stop
marker; no order is submitted with a zero stop price. Risk calculations charge
full capital at risk when absent. Signal exits, cash/exposure checks, reservations,
25% agent capital cap, kill/portfolio protections and session-end liquidation stay
independent. Technical cohorts retain their stored rule gates and protective stops.

Current policy (21 October 2026): Technical agents use gpt-6-luna (Standard USD 0.10 input / 0.50 output per million tokens), regardless of department. Other research agents use gpt-5.4-mini and other demo/fund agents gpt-6.1-sol. Manager unchanged. The CEO removed the local monthly/daily API spending stop: API_SPEND_LIMIT_ENABLED=false. Historical cost, reservations and uncertainty remain visible; provider quota/rate failures are still respected. These settings supersede earlier 30 EUR ceiling descriptions above. Source: https://developers.openai.com/api/docs/models/gpt-6-luna
