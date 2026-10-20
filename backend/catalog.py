from .config import now, units
from .db import uid, dumps, event, put

# Twenty domains x five distinct hypotheses, horizons and datasets = 100 profiles.
DOMAINS = [
 ("Trendfolge", ["MA-Crossover", "Donchian-Ausbruch", "Trendbeschleunigung", "Pullback im Trend", "Trendbruch"], "Preise, Trendstärke und Transaktionskosten"),
 ("Momentum", ["12-1 Momentum", "Kurzfristiges Momentum", "Gewinnrevision", "Residualmomentum", "Relatives Momentum"], "Renditepfade und Marktbereinigung"),
 ("Mean Reversion", ["Bollinger-Rückkehr", "RSI-Extrem", "Gap-Rücklauf", "Überreaktion", "VWAP-Abstand"], "Preise, Spreads und Handelsvolumen"),
 ("Volumen", ["OBV-Divergenz", "Volumenschock", "Akkumulation", "Liquiditätsbruch", "Preis-Volumen-Bestätigung"], "Volumen und Feedabdeckung"),
 ("Volatilität", ["Volatilitätskompression", "Regimewechsel", "ATR-Risikosteuerung", "Volatilitätscluster", "Downside-Volatilität"], "OHLC-Zeitreihen und Tail-Risiko"),
 ("Unternehmensnachrichten", ["Übernahmen", "Produkteinführung", "Führungswechsel", "Rückkäufe", "Rechtsstreitigkeiten"], "Verifizierte Unternehmensmeldungen"),
 ("Geopolitik", ["Handelszölle", "Sanktionen", "Energieversorgung", "Lieferketten", "Politische Überraschungen"], "Datierte Nachrichten mit Quellennachweis"),
 ("Fundamentaldaten", ["Qualität", "Value", "Bilanzstärke", "Cashflow", "Profitabilität"], "SEC-XBRL mit Verfügbarkeitszeitpunkt"),
 ("Quartalsberichte", ["Earnings Surprise", "Guidance", "Margen", "Umsatzqualität", "Post-Earnings Drift"], "Veröffentlichte Quartalsberichte und historische Preise"),
 ("Sektorrotation", ["Zyklische Sektoren", "Defensive Sektoren", "Technologiesektor", "Energie", "Finanzsektor"], "Sektor-ETFs und relative Renditen"),
 ("Relative Stärke", ["Aktie gegen Sektor", "Sektor gegen Markt", "Small gegen Large", "Wachstum gegen Value", "Defensive relative Stärke"], "Zeitlich abgestimmte Benchmarkpreise"),
 ("Statistik", ["Paarstabilität", "Kointegration", "Residualsignal", "Lead-Lag", "Regressionsbruch"], "Synchronisierte Zeitreihen; kein ungedeckter Short"),
 ("Marktstimmung", ["News-Tonalität", "Unsicherheit", "Widerspruch", "Aufmerksamkeitswechsel", "Sentiment-Umkehr"], "Lizenzierte Meldungen; keine erfundenen Social-Daten"),
 ("Makro", ["Inflation", "Arbeitsmarkt", "Zinsentscheidung", "Wachstum", "USD-Einfluss"], "Offizielle zeitgestempelte Veröffentlichungen"),
 ("Institutionelle Flüsse", ["ETF-Flüsse", "Indexänderung", "13F-Verzögerung", "Rebalancing", "Großvolumen"], "Öffentliche Meldungen; keine behaupteten Echtzeit-13F-Daten"),
 ("Marktregime", ["Trendregime", "Seitwärtsregime", "Stressregime", "Liquiditätsregime", "Cross-Asset-Regime"], "Volatilität, Korrelation und Trend"),
 ("Multifaktor", ["Value-Qualität", "Momentum-Qualität", "Defensive Faktoren", "Faktor-Drift", "Faktor-Redundanz"], "Point-in-time-Faktoren und robuste Normalisierung"),
 ("Mikrostruktur", ["Spread-Ausweitung", "Quotenstabilität", "Preisimpact", "Feed-Lücken", "Ausführungsqualität"], "IEX ist kein konsolidierter US-Feed"),
 ("Risikoforschung", ["Korrelation", "Tail-Risiko", "Drawdown-Erholung", "Konzentration", "Kostenempfindlichkeit"], "Portfolioereignisse und historische Renditen"),
 ("Strategierobustheit", ["Walk Forward", "Parameterstabilität", "OOS-Zerfall", "Zufallskontrolle", "Datenqualität"], "Reproduzierbare Tests und Datenherkunft"),
]

RISK_DEFAULTS = dict(max_position_pct=0.08, max_agent_pct=0.08, max_exposure_pct=0.60,
                     max_daily_loss_pct=0.02, max_drawdown_pct=0.08,
                     max_loss_per_position_pct=0.005, max_agent_risk_pct=0.01,
                     max_total_risk_pct=0.04, max_symbol_pct=0.12, max_correlated_pct=0.20,
                     max_spread_bps=60, quote_max_age_seconds=30,
                     slippage_bps=5, fee_bps=2, fx_max_age_days=5)


def seed(db):
    with db.tx() as c:
        for i in range(1, 101):
            domain, hypotheses, evidence = DOMAINS[(i - 1) // 5]
            focus = hypotheses[(i - 1) % 5]
            dept = "research" if i <= 50 else "demo" if i <= 75 else "fund"
            mandate = f"Untersuche {focus} im Gebiet {domain}. Daten: {evidence}. "
            mandate += f"Horizont {['intraday', '2–5 Tage', '1–4 Wochen', '1–3 Monate', 'regimeabhängig'][(i-1)%5]}. "
            mandate += "Keine Overnight-Positionen im Tageshandel. Fehlende Daten offen benennen."
            c.execute("INSERT OR IGNORE INTO agents VALUES(?,?,?,?,?,0,?,NULL)",
                      (i, f"{focus}", domain, mandate, dept, now()))
            spec = dict(kind="momentum" if i % 3 else "mean_reversion", lookback=10 + (i % 8) * 5,
                        threshold=round(0.005 + (i % 5) * 0.004, 3), holding_bars=2 + i % 9,
                        stop_pct=0.02 + (i % 3)*0.005, focus=focus, horizon=(i-1)%5,
                        watchlist_offset=i % 10,timeframe_minutes=15,
                        max_data_delay_minutes=15,requires_full_market=domain=='Mikrostruktur',
                        requires_realtime=False)
            c.execute("INSERT OR IGNORE INTO strategies VALUES(?,?,?,?,?,?,?)",
                      (f"agent-{i:03}-v1", i, 1, dumps(spec), "Initiale ungetestete Forschungshypothese; keine nachgewiesene Eignung.", "candidate", now()))
            if dept == "demo":
                add_portfolio(c, f"demo-{i:03}", "demo", i, 3000)
            elif dept == "research":
                add_portfolio(c, f"research-{i:03}", "research", i, 3000)
        add_portfolio(c, "fund", "fund", None, 3000)
        for key, value in {"risk_limits": RISK_DEFAULTS, "risk_confirmed": False,
                           "kill_switch": False, "trading_enabled": False,
                           "engine_enabled": True}.items():
            c.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", (key, dumps(value)))
        c.execute("INSERT OR IGNORE INTO meta VALUES('market_data_policy',?)",
                  (dumps({'delay_minutes':15,'feed':'iex','min_timeframe_minutes':15}),))
        # In-place policy migration: preserve identities, roles, portfolios and prior versions.
        import json
        for row in c.execute('SELECT id,spec FROM strategies').fetchall():
            spec=json.loads(row['spec'])
            changed=False
            for key,value in {'timeframe_minutes':15,'max_data_delay_minutes':15,
                              'requires_full_market':False,'requires_realtime':False}.items():
                if key not in spec:
                    spec[key]=value
                    changed=True
            if changed:
                c.execute('UPDATE strategies SET spec=? WHERE id=?',(dumps(spec),row['id']))
        if not c.execute("SELECT 1 FROM events LIMIT 1").fetchone():
            event(c, "bootstrap", "100 Agenten gespeichert: 50 Research, 25 Demo, 25 Fund. Anfangsbesetzung ist unbewertet.")
    from .news_agents import configure
    configure(db)


def add_portfolio(c, pid, kind, owner, amount):
    stamp = now()
    result = c.execute("INSERT OR IGNORE INTO portfolios VALUES(?,?,?,?,?,0,0,?)",
                       (pid, kind, owner, units(amount), units(amount), stamp))
    if result.rowcount:
        c.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?)",
                  (uid(), pid, f"initial-{pid}", "initial_virtual_capital", units(amount), units(amount), stamp))
        c.execute("INSERT INTO equity VALUES(?,?,?,?,?,?,?)",
                  (uid(), pid, units(amount), units(amount), 0, 1, stamp))
