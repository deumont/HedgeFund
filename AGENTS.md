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

Aktueller CEO-Auftrag: Analysen, Backtests und Strategieanpassungen ausschließlich
07:30 einschließlich bis 15:30 ausschließlich, Europe/Berlin. Warteschlange und
direkte Ausführung müssen die Grenze respektieren; verspätete Modellantworten
werden ohne Aktivierung zwischengespeichert und im nächsten Fenster fortgesetzt.
Handels-/Schutzkontrollen und abendliche Eigenbewertungen/Managerentscheidungen
behalten ihre eigenen Zeitpläne. Research Lab jederzeit lesbar, alle 100 Agenten
anklickbar mit aktualisierten Analysen, Backtests, Ergebnissen und Versionsdiffs.
AI Manager zeigt zusätzlich die Historie geplanter und ausgeführter Teamwechsel.

Neuester CEO-Auftrag: Genau 50 Agenten verfolgen Nachrichten-/Politik-/Unternehmens-
ansätze statt technischer Einstiege, übrige 50 technische Strategien. Identitäten,
Abteilungen 50/25/25 und Konten bewahren. Forschungsaufträge rotieren über den
bestätigten handelbaren US-Aktienkatalog und mehrere Aktien je Agent statt nur SPY.
Nachrichtenagenten verwenden belegte Unternehmensthesen und Ereignisstudien;
nachträglich geladene Nachrichten sind kein historischer Point-in-time-Nachweis,
Kursreaktionen keine Strategiegewinne. Ohne geeignete Quellen kein Einstieg und
kein technischer Ersatzhandel. Alle bestehenden Zeit-, Kapital- und Datengrenzen
gelten weiterhin.

CEO-Auftrag vom 21.10.2026: Unterschiedliche Ansätze einschließlich ausdrücklich
als Zufall gekennzeichneter Paper-Experimente zulassen. Zunächst fünf bestehende
Demo-Agenten (51–55) experimentell führen; 50 Nachrichtenagenten, übrige 45
technische Agenten, Abteilungen weiterhin 50/25/25. Kein technischer oder
fundamentaler Vorwand für Zufallskäufe, kein erneutes Auslosen beim Polling.
Manager sieht Ansatz und tatsächliche Ergebnisse; kein automatischer Aufstieg
wegen kurzer Glücksserie. Echtgeldausführung bleibt deaktiviert. 25-Prozent-
Kapitalgrenze, geeignete Ausführungsdaten, mindestens 15-Minuten-Zeitrahmen,
Forschungsfenster und API-Monatsbudget bleiben bestehen.

CEO-Aufträge vom 21.10.2026 (neuester Stand): Forschungs-/Warteschlangenagenten
verwenden gpt-5.4-mini, Demo und Fonds gpt-6.1-sol. Modell bei jedem Aufruf aus
der aktuellen Abteilung bestimmen; Auf-/Abstiege müssen die Wahl sofort ändern.
Manager bleibt gpt-5.4-mini. Budget, Tagesberichte und Modellanzeige konsistent halten.
Ab heute täglich mindestens ein benachbartes Tauschpaar (Aufstieg und Abstieg)
nach dem persönlichen Handelsschluss durchführen, 25 Fonds / 25 Demo / 50 Forschung
atomar bewahren. Kurze Stichproben als Erprobung kennzeichnen. Bei fehlender
Modellantwort darf eine ausdrücklich gekennzeichnete Managerregel gespeicherte
Bewertungen/Ergebnisse nutzen; keine Modellantwort erfinden. Offene Positionen
und Orders verhindern den betroffenen Rollenwechsel; freie Ersatzpaare bevorzugen.
Passwort-Recovery auf der öffentlichen Website unterstützen; RLS und den privaten
ATLAS-Mitgliedszugang erhalten. Neue Passwörter setzt der Benutzer selbst.


CEO request 21 October 2026: Each of the 50 news/fundamental agents has an individual
research desk and its own catalyst questions, starter stocks and primary-source
preferences. Agents conduct actual public web research and monitor every owned
stock plus their watchlist while trading. Persist consulted source URLs and retrieval
times; retrieval is never a verified publication time or a fresh trading catalyst.
Manager assessments prioritize documented pre-execution decision quality over lucky
profit. Research agents cannot execute orders and are judged on research/tests,
never penalized for zero trades. Hosted web fees and retrieved tokens count toward
the existing 30 EUR monthly cap. Paper-only, data and capital gates remain.


Latest CEO requests 21 October 2026: Add a daily calendar with signed fund P&L
and the day's best manager-rated agent(s), explicitly distinguishing valuation
changes, realized P&L, provisional/missing marks and tied ratings. Every agent
needs selectable past days, trades/actions/reports and a full career reconstructed
from the initial roster and actually applied role changes. Historical fills retain
their original fund/demo account after promotion/demotion. Manager assessments,
reports and staffing must consider prior days and role-separated lifetime results.

Discretionary news/fundamental agents prepare by researching public information,
learning, reading sources and tracking events; no automatic backtests or penalty
for missing backtests. Preserve historical studies. Technical/rule-based cohorts
keep their backtests. Information traders may hold longer, add on new source-backed
information, reduce partially or exit. Fixed price stops and take profits are
optional in the authorized internal strategy-sizing paper mode; no stop means
full invested capital at risk. No forced time exit unless explicitly selected.
Existing session end liquidation, at least 15m availability, appropriate execution
data, independent signal/risk checks and 25% total exposure per agent remain.
An information decision is consumed once per action; no repeated add/reduce loop
and no repeated buying on unchanged source evidence. No real money.

Latest explicit CEO override 21 October 2026: Technical-analysis agents use gpt-6-luna in every department, including research; resolve approach at each request. Other research agents retain gpt-5.4-mini, other demo/fund agents gpt-6.1-sol and manager gpt-5.4-mini. Remove the local API spending stop, including the previous 30 EUR monthly cap. API_SPEND_LIMIT_ENABLED=false is the default and deployed configuration. Keep actual cost and uncertain reservation accounting; never fabricate or clear historical usage. Resume latest locally budget-blocked work, consolidate redundant old blocked jobs, never replay uncertain provider calls or broker submissions. Provider rate/quota pauses, research hours, paper-only and all trading capital/data gates remain.
