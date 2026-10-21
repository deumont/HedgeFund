"""Individual public-information mandates. Examples are starting points, never buy lists."""
DESKS = [
 ('Institutionelle Beteiligungen / Gastronomie','MCD YUM QSR','13F 13D institutional ownership restaurant','sec.gov','Meldezeit gegen tatsächlichen Kaufzeitpunkt prüfen; Bankdepot ist keine Übernahme.'),
 ('Spielepublisher / Veröffentlichungskalender','TTWO EA RBLX','game release delay bookings publisher','take2games.com','Offiziellen Termin, Verschiebungsrisiko und bereits eingepreiste Erwartungen prüfen.'),
 ('Halbleiter / Exportkontrollen','NVDA AMD INTC','export controls semiconductor license','bis.gov','Genehmigung, Produkt und Umsatzanteil unterscheiden.'),
 ('Chipfertigung / Investitionszyklen','TSM ASML AMAT','semiconductor capex equipment order','investor.tsmc.com','Auftragseingang von angekündigtem Investitionsbudget trennen.'),
 ('Cloud / Großverträge','MSFT AMZN ORCL','cloud contract backlog capital spending','microsoft.com','Vertragslaufzeit, Marge und Kundenkonzentration prüfen.'),
 ('KI / Rechenzentrum-Stromversorgung','VRT ETN GEV','data center power grid order','energy.gov','Netzanschluss und finanzierte Aufträge statt Absichtserklärungen.'),
 ('Cybersecurity / Sicherheitsvorfälle','CRWD PANW FTNT','cybersecurity breach contract incident','cisa.gov','Betroffenheit und finanzielle Folgen separat belegen.'),
 ('Unternehmenssoftware / Kundenbindung','CRM ADBE NOW','software retention guidance subscription','sec.gov','Umsatzqualität, Verlängerungen und Ausblick prüfen.'),
 ('Digitale Werbung / Datenschutz','GOOGL META APP','advertising privacy antitrust ruling','ftc.gov','Rechtsentscheidung von Spekulation und Berufungsverfahren trennen.'),
 ('Smartphones / Lieferketten','AAPL QCOM SWKS','smartphone supplier production demand','apple.com','Absatzdaten von Kanalbeständen unterscheiden.'),
 ('E-Autos / Subventionen','TSLA RIVN GM','electric vehicle incentive delivery recall','nhtsa.gov','Lieferungen, Rabatte und Förderbedingungen gemeinsam prüfen.'),
 ('Autonomes Fahren / Zulassungen','GOOGL UBER AUR','autonomous vehicle permit safety','nhtsa.gov','Pilotgenehmigung ist keine landesweite Kommerzialisierung.'),
 ('Batterien / Rohstoffabhängigkeit','ALB SQM LAC','lithium battery supply offtake','usgs.gov','Spotpreise, Vertragsbindung und Finanzierung unterscheiden.'),
 ('Öl / Förderpolitik','XOM CVX COP','OPEC production sanction oil supply','eia.gov','Beschluss, tatsächliche Förderung und Nachfrage prüfen.'),
 ('Gas / LNG-Ausfuhr','LNG EQT WMB','LNG export permit gas pipeline','ferc.gov','Genehmigung ist keine fertige Exportkapazität.'),
 ('Solar / Handelspolitik','FSLR ENPH NXT','solar tariff tax credit order','commerce.gov','Zollausnahmen und Lieferkettenherkunft prüfen.'),
 ('Wind / Projektfinanzierung','GEV CWEN NEE','wind project permit financing cancellation','boem.gov','Finanzierungsabschluss von Projektankündigung trennen.'),
 ('Atomkraft / Reaktorgenehmigungen','CEG CCJ BWXT','nuclear reactor approval fuel contract','nrc.gov','Betriebsgenehmigung und langfristige Abnahmeverträge prüfen.'),
 ('Versorger / Regulierte Renditen','DUK SO AEP','utility rate case regulator grid','ferc.gov','Genehmigte Tarife gegen Antrag und Investitionsbedarf abgleichen.'),
 ('Verteidigung / Staatsaufträge','LMT RTX NOC','defense contract appropriation award','defense.gov','Auftragsobergrenze ist kein garantierter Umsatz.'),
 ('Luftfahrt / Zulassungen','BA GE HWM','aircraft certification delivery inspection','faa.gov','Bestellung, Auslieferung und Sicherheitsauflage unterscheiden.'),
 ('Fluglinien / Betriebskosten','DAL UAL LUV','airline capacity fuel booking','transportation.gov','Buchungen und Treibstoffkosten gegen Kapazität prüfen.'),
 ('Schifffahrt / Handelsrouten','ZIM MATX KEX','shipping route disruption freight rate','maritime.dot.gov','Kurzfristige Frachtrate nicht als dauerhafte Marge fortschreiben.'),
 ('Bahn / Industrielogistik','UNP CSX NSC','railroad freight labor regulation','stb.gov','Transportvolumen, Preise und Arbeitskonflikte prüfen.'),
 ('Maschinenbau / Infrastruktur','CAT DE URI','infrastructure equipment order backlog','census.gov','Ausgabenbeschluss, Auftrag und ausgelieferten Umsatz trennen.'),
 ('Banken / Aufsicht und Kapital','JPM BAC C','bank capital stress test provision','federalreserve.gov','Kapitalanforderung und Kreditverluste gegen Zinsertrag abwägen.'),
 ('Regionalbanken / Einlagenrisiko','KRE KEY RF','regional bank deposit liquidity commercial real estate','fdic.gov','Einlagenabfluss und Buchverluste von Gerüchten unterscheiden.'),
 ('Zahlungsverkehr / Regulierung','V MA PYPL','payment interchange regulation volume','consumerfinance.gov','Rechtswirksamkeit und betroffenen Umsatzanteil prüfen.'),
 ('Versicherungen / Katastrophen','PGR ALL TRV','insurance catastrophe reserve premium','noaa.gov','Bruttoschaden, Rückversicherung und Reserven unterscheiden.'),
 ('Börsen / Marktinfrastruktur','CME ICE NDAQ','exchange trading volume clearing regulation','cftc.gov','Volatilität ist erst mit tatsächlichem Volumen ein Umsatztreiber.'),
 ('Pharma / Studienergebnisse','LLY NVO MRK','clinical trial endpoint drug results','clinicaltrials.gov','Primärendpunkt, Vergleichsgruppe und Nebenwirkungen prüfen.'),
 ('Biotech / FDA-Entscheidungen','VRTX REGN GILD','FDA approval advisory committee drug','fda.gov','Zulassung, Studienphase und Finanzierungsbedarf unterscheiden.'),
 ('Medizintechnik / Rückrufe','MDT ABT ISRG','medical device approval recall procedure','fda.gov','Rückrufumfang und betroffene Produktumsätze belegen.'),
 ('Krankenversicherer / Erstattung','UNH HUM CVS','Medicare reimbursement medical cost ratio','cms.gov','Endgültige Erstattung gegen vorgeschlagene Sätze prüfen.'),
 ('Krankenhäuser / Auslastung','HCA THC UHS','hospital reimbursement utilization staffing','cms.gov','Fallzahlen und Personalkosten gemeinsam prüfen.'),
 ('Lebensmittel / Inputkosten','PEP KO MDLZ','food commodity pricing volume earnings','usda.gov','Preiserhöhungen gegen rückläufige Stückzahlen prüfen.'),
 ('Einzelhandel / Konsumverhalten','WMT TGT COST','retail inventory consumer sales membership','census.gov','Lagerabbau, Rabattkosten und vergleichbare Umsätze prüfen.'),
 ('Luxus / China-Nachfrage','TPR RL EL','luxury China demand tourism sales','sec.gov','Regionale Nachfrage statt pauschaler China-Erzählung belegen.'),
 ('Sportartikel / Markenverträge','NKE LULU DECK','sportswear inventory distribution brand contract','sec.gov','Vertriebskanal, Lagerbestände und Margen prüfen.'),
 ('Hotels / Reisenachfrage','MAR HLT BKNG','hotel RevPAR travel reservation demand','ustravel.org','Buchungswachstum gegen Stornoquote und Preise prüfen.'),
 ('Freizeitparks / Unterhaltung','DIS CMCSA SIX','theme park attendance opening content','thewaltdisneycompany.com','Besucherzahlen, Investitionskosten und Margen prüfen.'),
 ('Streaming / Filmrechte','NFLX WBD PARA','streaming subscriber content rights earnings','sec.gov','Abonnenten, Werbeumsatz und Rechtekosten unterscheiden.'),
 ('Telekommunikation / Frequenzen','T VZ TMUS','telecom spectrum auction subscriber capex','fcc.gov','Frequenzgewinn gegen Schulden und Ausbaupflichten bewerten.'),
 ('Immobilien / Refinanzierung','PLD AMT SPG','REIT refinancing occupancy lease','sec.gov','Vermietung, Laufzeiten und Refinanzierungszinsen gemeinsam prüfen.'),
 ('Wohnungsbau / Hypotheken','DHI LEN PHM','housing starts mortgage builder cancellation','census.gov','Stornierungen und Verkaufsanreize gegen Neubestellungen prüfen.'),
 ('Bergbau / Genehmigungen','FCX NEM SCCO','copper gold mine permit disruption','usgs.gov','Fördervolumen und Arbeitskonflikte gegen Rohstoffpreis abgleichen.'),
 ('Landwirtschaft / Exportpolitik','ADM BG MOS','crop export restriction fertilizer harvest','usda.gov','Ernteprognose, Lagerbestände und Handelsbeschränkungen prüfen.'),
 ('Fusionen / Kartellrecht','ABBV CSCO IBM','merger acquisition antitrust approval deal','ftc.gov','Verbindlichen Vertrag, Finanzierung und Vollzugsrisiko prüfen.'),
 ('Aktivisten / Kapitalallokation','PYPL INTC PFE','activist 13D buyback spin off','sec.gov','Gemeldete Beteiligung, Forderung und tatsächlich beschlossene Maßnahme trennen.'),
 ('Zölle / Importabhängige Firmen','F GM BBY','tariff customs import exemption supply chain','ustr.gov','Inkrafttreten, Ausnahmen und konkrete Kostenexponierung prüfen.'),
]
NEWS_IDS = tuple(list(range(26,50))+list(range(61,74))+list(range(76,89)))


def desk(aid):
    if aid not in NEWS_IDS:return None
    focus,stocks,terms,primary,caution=DESKS[NEWS_IDS.index(aid)]
    return dict(focus=focus,watchlist=stocks.split(),search_terms=terms,primary_source=primary,catalyst_check=caution)


def watched_symbols(db,aid):
    """All owned stocks stay covered even if outside the desk's original specialty."""
    from .universe import eligible
    profile=desk(aid) or {}
    symbols=[r['symbol'] for r in db.all('SELECT symbol FROM positions WHERE agent_id=?',(aid,))]
    symbols += [r['symbol'] for r in db.all("SELECT DISTINCT symbol FROM orders WHERE agent_id=? AND status IN ('pending','triggered')",(aid,))]
    symbols += [db.get('agent-stock-'+str(aid))]+profile.get('watchlist',[])
    return [s for s in dict.fromkeys(symbols) if eligible(db,s)]
