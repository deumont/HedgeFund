"""Provider boundary: fixed broker origin, honest entitlement diagnostics."""
import asyncio
import json
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse
import httpx
import requests
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest, MarketOrderRequest, LimitOrderRequest, StopOrderRequest,StopLossRequest,TakeProfitRequest
from alpaca.trading.enums import OrderSide, TimeInForce,OrderClass
from alpaca.data.historical import StockHistoricalDataClient, NewsClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, NewsRequest
from alpaca.data.enums import DataFeed, Adjustment
from alpaca.data.timeframe import TimeFrame,TimeFrameUnit
from websockets.asyncio.client import connect
from .config import PAPER_URL, now
from .db import dumps, uid
from .calendar import NEW_YORK


class PaperOnlyAdapter(requests.adapters.HTTPAdapter):
    def send(self, request, **kwargs):
        parsed = urlparse(request.url)
        if parsed.scheme != 'https' or parsed.netloc != 'paper-api.alpaca.markets':
            raise RuntimeError("Broker-Ziel durch Paper-only-Sperre blockiert")
        kwargs['timeout'] = 20
        return super().send(request, **kwargs)


def paper_client(cfg):
    if not cfg.has_alpaca:
        raise ValueError("Alpaca-Paper-Zugangsdaten fehlen")
    client = TradingClient(cfg.alpaca_paper_api_key, cfg.alpaca_paper_secret_key,
                           paper=True, url_override=PAPER_URL)
    client._session.trust_env = False
    client._retry=0
    guard = PaperOnlyAdapter(max_retries=0)
    client._session.mount('https://', guard)
    client._session.mount('http://', guard)
    return client


class DataOnlyAdapter(requests.adapters.HTTPAdapter):
    def send(self,request,**kwargs):
        parsed=urlparse(request.url)
        if parsed.scheme!='https' or parsed.netloc!='data.alpaca.markets' or request.method!='GET':
            raise RuntimeError('Nur offizielle lesende Alpaca-Marktdatenzugriffe erlaubt')
        kwargs['timeout']=20
        return super().send(request,**kwargs)


def data_client(cls,cfg):
    if not cfg.has_alpaca:
        raise ValueError('Alpaca-Paper-Schlüsselpaar fehlt')
    client=cls(cfg.alpaca_paper_api_key,cfg.alpaca_paper_secret_key)
    client._session.trust_env=False
    client._retry=0
    client._session.mount('https://',DataOnlyAdapter(max_retries=0))
    client._session.mount('http://',DataOnlyAdapter(max_retries=0))
    return client


def plain(value):
    return json.loads(value.model_dump_json()) if hasattr(value,'model_dump_json') else value


class Providers:
    def __init__(self, db, cfg):
        self.db, self.cfg = db, cfg
        self.stopping = asyncio.Event()

    def diagnose(self):
        if not self.cfg.has_alpaca:
            for name in ['alpaca_paper','historical','news','market_stream','calendar']:
                self.db.integration(name,'blocked','Alpaca-Paper-Schlüsselpaar fehlt in .env')
        else:
            try:
                account = paper_client(self.cfg).get_account()
                self.db.integration('alpaca_paper','connected',f"Paper-Konto bestätigt; Status {account.status}. Brokerkapital ist unabhängig vom internen 3.000-EUR-Fonds.")
                self.calendar()
                self.assets()
                self.latest_quotes()
            except Exception as exc:
                self.db.integration('alpaca_paper','error',safe_error(exc))
        verified=bool(self.cfg.openai_api_key and self.db.get('openai_verified_key_digest')==hashlib.sha256(self.cfg.openai_api_key.encode()).hexdigest())
        self.db.integration('openai','connected' if verified else 'configured' if self.cfg.openai_api_key else 'blocked',
                            'Aktueller Schlüssel durch echte Responses-Anfrage bestätigt' if verified else
                            'Schlüssel vorhanden; echter Reasoning-Test noch erforderlich' if self.cfg.openai_api_key else 'OPENAI_API_KEY fehlt in .env')
        self.db.integration('social_realtime','blocked','Keine lizenzierte Truth-Social-/Social-Media-API eingerichtet')
        self.db.integration('economic_calendar','blocked','Keine zeitgenaue Wirtschaftskalenderquelle eingerichtet')
        self.db.integration('corporate_actions','blocked','Automatisches Split-/Dividenden-Ledger noch nicht freigegeben; keine Overnight-Strategien')

    def calendar(self):
        start = datetime.now(timezone.utc).date()-timedelta(days=5)
        end = start+timedelta(days=45)
        records = paper_client(self.cfg).get_calendar(GetCalendarRequest(start=start,end=end))
        with self.db.tx() as c:
            c.execute("DELETE FROM sessions WHERE date BETWEEN ? AND ?",(start.isoformat(),end.isoformat()))
            for item in records:
                opens = item.open if item.open.tzinfo else item.open.replace(tzinfo=NEW_YORK)
                closes = item.close if item.close.tzinfo else item.close.replace(tzinfo=NEW_YORK)
                c.execute("INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)",(item.date.isoformat(),opens.isoformat(),closes.isoformat(),'Alpaca calendar'))
        self.db.set('calendar_coverage',{'start':start.isoformat(),'end':end.isoformat()})
        self.db.integration('calendar','connected',f'{start} bis {end}, inklusive tatsächlicher verkürzter Sitzungen')

    def assets(self):
        client = paper_client(self.cfg)
        for symbol in self.cfg.symbols:
            item = client.get_asset(symbol)
            with self.db.tx() as c:
                c.execute("INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?)",(symbol,int(item.tradable),item.asset_class.value,item.exchange.value,now()))

    def latest_quotes(self):
        client = data_client(StockHistoricalDataClient,self.cfg)
        data = client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=self.cfg.symbols,feed=DataFeed(self.cfg.alpaca_feed)))
        for symbol, q in data.items():
            self.store_quote(symbol,str(q.bid_price),str(q.ask_price),q.bid_size,q.ask_size,q.timestamp.isoformat())
        self.db.integration('quotes','connected',f'{len(data)} tatsächliche Quotes; Feed {self.cfg.alpaca_feed}. Alter wird je Order geprüft.')

    def store_quote(self,symbol,bid,ask,bsize,asize,stamp):
        current = self.db.one("SELECT market_at FROM quotes WHERE symbol=?",(symbol,))
        if current and datetime.fromisoformat(current['market_at']) >= datetime.fromisoformat(stamp):
            return
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO quotes VALUES(?,?,?,?,?,?,?,?)",
                      (symbol,bid,ask,int(bsize),int(asize),stamp,now(),'Alpaca '+self.cfg.alpaca_feed.upper()))

    def historical(self,symbol,days=365):
        if symbol not in self.cfg.symbols or not 30<=days<=3650:
            raise ValueError("Symbol/Zeitraum nicht erlaubt")
        client = data_client(StockHistoricalDataClient,self.cfg)
        end = datetime.now(timezone.utc)-timedelta(days=1)
        records = client.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,start=end-timedelta(days=days),end=end,
            adjustment=Adjustment.ALL,feed=DataFeed(self.cfg.alpaca_feed)))
        count = 0
        with self.db.tx() as c:
            for item in records.data.get(symbol,[]):
                c.execute("INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (symbol,item.timestamp.isoformat(),'1Day',str(item.open),str(item.high),str(item.low),str(item.close),int(item.volume),'Alpaca '+self.cfg.alpaca_feed.upper(),'all'))
                count += 1
        self.db.integration('historical','connected',f'{symbol}: {count} echte bereinigte Tagesbars geladen; keine vollständige IPO-Historie zugesichert')
        self.db.event('historical',f'{symbol}: {count} historische Bars gespeichert')
        return {'symbol':symbol,'bars':count}

    def intraday(self):
        """Central 15min historical poll; explicitly waits out the declared 15min delay."""
        client=data_client(StockHistoricalDataClient,self.cfg)
        end=datetime.now(timezone.utc)-timedelta(minutes=15)
        latest=self.db.all("SELECT symbol,MAX(time) stamp FROM bars WHERE timeframe='15Min' AND source=? AND adjustment='raw' GROUP BY symbol",('Alpaca '+self.cfg.alpaca_feed.upper(),))
        start=end-timedelta(days=8)
        stamps=[datetime.fromisoformat(x['stamp']) for x in latest if x['symbol'] in self.cfg.symbols]
        if len(stamps)==len(self.cfg.symbols):
            start=max(start,min(stamps)-timedelta(minutes=45))
        records=client.get_stock_bars(StockBarsRequest(symbol_or_symbols=self.cfg.symbols,
                    timeframe=TimeFrame(15,TimeFrameUnit.Minute),start=start,end=end,
                    adjustment=Adjustment.RAW,feed=DataFeed(self.cfg.alpaca_feed)))
        count=0
        with self.db.tx() as c:
            for symbol,items in records.data.items():
                for item in items:
                    if item.timestamp+timedelta(minutes=15)>end:
                        continue
                    c.execute('INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (symbol,item.timestamp.isoformat(),'15Min',str(item.open),str(item.high),str(item.low),str(item.close),
                         int(item.volume),'Alpaca '+self.cfg.alpaca_feed.upper(),'raw'))
                    count+=1
        self.db.integration('intraday_bars','connected',f'{count} echte abgeschlossene 15-Minuten-Bars; mindestens 15 Minuten verzögert. Keine Echtzeit-Ausführung aus diesen Bars.')
        return {'bars':count,'timeframe_minutes':15,'declared_delay_minutes':15}

    def news(self):
        client = data_client(NewsClient,self.cfg)
        previous = self.db.get('last_news_at')
        start = datetime.fromisoformat(previous) if previous else datetime.now(timezone.utc)-timedelta(days=1)
        result = client.get_news(NewsRequest(start=start,limit=50,include_content=False,sort='asc'))
        # NewsSet exposes .news; version-safe fallback to .data['news'].
        items = getattr(result,'news',None)
        if items is None:
            items = result.data.get('news',[])
        newest = previous
        for item in items:
            row = plain(item)
            stamp = str(row['created_at'])
            self.store_news(row)
            if newest is None or datetime.fromisoformat(stamp)>datetime.fromisoformat(newest):
                newest=stamp
        if newest:
            self.db.set('last_news_at',newest)
        self.db.integration('news','connected',f'{len(items)} Meldungen abgerufen; tatsächliche Empfangszeiten gespeichert, keine 1-Sekunden-Garantie')

    def store_news(self,row):
        """One shared, deduplicated feed for all roles, including off-watchlist news."""
        if not row.get('id') or not row.get('headline') or not row.get('created_at'):
            raise ValueError('Unvollständige Nachrichtenmeldung')
        stamp=datetime.fromisoformat(str(row['created_at']).replace('Z','+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Nachrichtenzeit ohne Zeitzone')
        with self.db.tx() as c:
            old=c.execute('SELECT * FROM news WHERE id=?',(str(row['id']),)).fetchone()
            c.execute("INSERT INTO news VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET headline=excluded.headline,summary=excluded.summary,url=excluded.url,symbols=excluded.symbols",(
                str(row['id']),row.get('source') or 'Alpaca News',row['headline'],row.get('summary') or '',
                row.get('url') or '',dumps(row.get('symbols',[])),stamp.isoformat(),now(),
                'Quellenmeldung, nicht unabhängig verifiziert','Für alle 100 Agenten verfügbar'))
        if not old:
            self.db.event('news_received',row['headline'],data={'news_id':str(row['id'])})

    async def news_stream(self):
        if not self.cfg.has_alpaca:
            self.db.integration('news_stream','blocked','Alpaca-Schlüsselpaar fehlt')
            return
        delay=2
        while not self.stopping.is_set():
            try:
                async with connect('wss://stream.data.alpaca.markets/v1beta1/news',open_timeout=15,ping_interval=20,max_queue=256) as ws:
                    await asyncio.wait_for(ws.recv(),15)
                    await ws.send(dumps({'action':'auth','key':self.cfg.alpaca_paper_api_key,'secret':self.cfg.alpaca_paper_secret_key}))
                    auth=json.loads(await asyncio.wait_for(ws.recv(),15))
                    if not any(x.get('msg')=='authenticated' for x in auth):
                        raise RuntimeError('News-Authentifizierung fehlgeschlagen')
                    await ws.send(dumps({'action':'subscribe','news':['*']}))
                    subscribed=False
                    while not self.stopping.is_set():
                        try:
                            items=json.loads(await asyncio.wait_for(ws.recv(),30))
                        except asyncio.TimeoutError:
                            await ws.ping()
                            continue
                        for row in items:
                            if row.get('T')=='error':
                                raise RuntimeError('News-Feed nicht verfügbar')
                            if row.get('T')=='subscription' and '*' in row.get('news',[]):
                                subscribed=True
                                delay=2
                                self.db.integration('news_stream','connected','Live-Alpaca-News: alle verfügbaren Symbole, gemeinsam für 100 Agenten; keine Garantie vollständiger Weltnachrichten.')
                            if row.get('T')=='n' and subscribed:
                                self.store_news(row)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.db.integration('news_stream','error',safe_error(exc))
                try:
                    await asyncio.wait_for(self.stopping.wait(),delay)
                except asyncio.TimeoutError:
                    pass
                delay=min(60,delay*2)
        self.db.integration('news_stream','offline','News-Verbindung beendet')

    async def fx(self):
        async with httpx.AsyncClient(timeout=20,follow_redirects=False,trust_env=False) as client:
            r = await client.get('https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml')
            r.raise_for_status()
            root = ET.fromstring(r.content)
        date, rate = None, None
        for node in root.iter():
            if 'time' in node.attrib:
                date=node.attrib['time']
            if node.attrib.get('currency')=='USD':
                rate=node.attrib['rate']
        if not date or not rate or not Decimal(rate)>0:
            raise ValueError('Kein EUR/USD-EZB-Referenzkurs in Antwort')
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO fx VALUES(?,?,?,?)",(date,rate,'ECB eurofxref daily',now()))
        self.db.integration('fx','connected',f'{date}: 1 EUR = {rate} USD. Tagesreferenz, kein handelbarer Intraday-FX-Kurs.')
        return {'date':date,'usd_per_eur':rate}

    async def edgar(self,cik,symbol):
        if not self.cfg.sec_user_agent or '@' not in self.cfg.sec_user_agent:
            raise ValueError('SEC_USER_AGENT benötigt Organisation und echte Kontakt-E-Mail')
        cik=str(cik).zfill(10)
        if not cik.isdigit() or len(cik)!=10:
            raise ValueError('Ungültige CIK')
        url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
        async with httpx.AsyncClient(timeout=25,trust_env=False) as client:
            response=await client.get(url,headers={'User-Agent':self.cfg.sec_user_agent})
            response.raise_for_status()
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?)",(f'sec-{cik}','SEC companyfacts',symbol,url,dumps(response.json()),now(),now()))
        self.db.integration('edgar','connected',f'CIK {cik}: SEC-Unternehmensdaten gespeichert; Filed-Datum jedes Faktums beachten')
        return {'cik':cik,'stored':True}

    async def market_stream(self):
        if not self.cfg.has_alpaca:
            return
        feed=self.cfg.alpaca_feed
        if feed not in ('iex','sip'):
            raise ValueError('Nur IEX/SIP-Feed erlaubt')
        delay=2
        while not self.stopping.is_set():
            try:
                async with connect(f'wss://stream.data.alpaca.markets/v2/{feed}',open_timeout=15,ping_interval=20,max_queue=128) as ws:
                    await ws.recv()
                    await ws.send(dumps({'action':'auth','key':self.cfg.alpaca_paper_api_key,'secret':self.cfg.alpaca_paper_secret_key}))
                    auth=json.loads(await ws.recv())
                    if any(x.get('T')=='error' for x in auth):
                        raise RuntimeError('Marktstream-Authentifizierung/Berechtigung fehlgeschlagen')
                    await ws.send(dumps({'action':'subscribe','quotes':self.cfg.symbols}))
                    subscribed=json.loads(await ws.recv())
                    if any(x.get('T')=='error' for x in subscribed):
                        raise RuntimeError('Feed/Symbol-Limit: Subscription abgelehnt')
                    self.db.integration('market_stream','connected',f'{feed.upper()}: zentraler Quote-Stream. '+('Nur IEX, kein konsolidierter Gesamtmarkt.' if feed=='iex' else 'SIP-Berechtigung bestätigt.'))
                    delay=2
                    while not self.stopping.is_set():
                        try:
                            data=await asyncio.wait_for(ws.recv(),timeout=25)
                        except asyncio.TimeoutError:
                            await ws.ping()
                            continue
                        for item in json.loads(data):
                            if item.get('T')=='q':
                                self.store_quote(item['S'],str(item['bp']),str(item['ap']),item['bs'],item['as'],item['t'])
                            elif item.get('T')=='error':
                                raise RuntimeError('Marktdatenstream meldet Fehler '+str(item.get('code')))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.db.integration('market_stream','error',safe_error(exc))
                self.db.event('connection','Marktdaten getrennt; neue Orders gesperrt',level='warning')
                try:
                    await asyncio.wait_for(self.stopping.wait(),timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay=min(60,delay*2)
        self.db.integration('market_stream','offline','Worker/Stream beendet')


def safe_error(exc):
    # Do not persist provider exception bodies/headers: they can echo credentials or inputs.
    code=getattr(exc,'status_code',None)
    if code is None and getattr(exc,'response',None) is not None:
        code=exc.response.status_code
    return f'{type(exc).__name__}'+(f' HTTP {code}' if code else '')+'; Verbindung/Berechtigung prüfen. Details enthalten keine Zugangsdaten.'


class BrokerValidation:
    """Separate Alpaca paper account. Never masquerades as 50 internal subaccounts."""
    def __init__(self,db,cfg):
        self.db,self.cfg=db,cfg

    def submit(self,client_id,symbol,side,qty,order_type='market',limit_price=None,stop_price=None):
        from .calendar import phase
        clock=phase(self.db)
        if (not clock['trading'] and not (side=='sell' and clock['liquidating'])) or (side=='buy' and self.db.get('kill_switch')) or not self.db.get('risk_confirmed'):
            raise ValueError('Broker-Validierung durch Zeit/Risikofreigabe gesperrt')
        # Validation orders are limited to 1 whole share and watchlist only.
        if symbol not in self.cfg.symbols or side not in ('buy','sell') or Decimal(str(qty))!=1:
            raise ValueError('Broker-Validierung: nur 1 Aktie aus Watchlist')
        from .ledger import valid_quote,latest_fx,meta
        with self.db.tx() as c:
            quote=valid_quote(c,symbol,meta(c,'risk_limits'))
            fx=latest_fx(c)
            ask=Decimal(quote['ask'])
            if ask/fx>Decimal('240'):
                raise ValueError('Broker-Test maximal 240 EUR Notional; günstigere Aktie wählen')
        for price in (limit_price,stop_price):
            if price is not None:
                value=Decimal(str(price))
                if not value.is_finite() or not ask*Decimal('.8')<value<ask*Decimal('1.2'):
                    raise ValueError('Broker-Testpreis muss innerhalb 20% des echten Kurses liegen')
        prior=self.db.one('SELECT * FROM broker_orders WHERE client_id=?',(client_id,))
        if prior:
            return prior
        client=paper_client(self.cfg)
        if side=='sell':
            p=client.get_open_position(symbol)
            if Decimal(p.qty)<1:
                raise ValueError('Kein Broker-Long-Bestand')
        params=dict(symbol=symbol,qty=1,side=OrderSide(side),time_in_force=TimeInForce.DAY,client_order_id=client_id)
        if side=='buy':
            entry=min(ask,Decimal(str(limit_price))) if limit_price else ask
            params.update(order_class=OrderClass.BRACKET,
                          stop_loss=StopLossRequest(stop_price=round(float(entry*Decimal('.98')),2)),
                          take_profit=TakeProfitRequest(limit_price=round(float(entry*Decimal('1.04')),2)))
        if order_type=='market':
            req=MarketOrderRequest(**params)
        elif order_type=='limit':
            req=LimitOrderRequest(**params,limit_price=limit_price)
        elif order_type=='stop' and side=='sell':
            req=StopOrderRequest(**params,stop_price=stop_price)
        else:
            raise ValueError('Ordertyp nicht unterstützt')
        oid=uid()
        with self.db.tx() as c:
            c.execute('INSERT INTO broker_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (oid,client_id,symbol,side,'1',order_type,dumps(plain(req)),'submitting',None,'{}',now(),now()))
        # On ambiguous network failure, keep 'submitting'; reconcile by client ID, never resubmit.
        result=client.submit_order(req)
        with self.db.tx() as c:
            c.execute('UPDATE broker_orders SET broker_id=?,status=?,result=?,updated_at=? WHERE id=?',
                      (str(result.id),result.status.value,dumps(plain(result)),now(),oid))
        return self.db.one('SELECT * FROM broker_orders WHERE id=?',(oid,))

    def reconcile(self):
        client=paper_client(self.cfg)
        for row in self.db.all("SELECT * FROM broker_orders WHERE status NOT IN ('filled','canceled','expired','rejected')"):
            result=client.get_order_by_client_id(row['client_id'])
            with self.db.tx() as c:
                c.execute('UPDATE broker_orders SET broker_id=?,status=?,result=?,updated_at=? WHERE id=?',
                          (str(result.id),result.status.value,dumps(plain(result)),now(),row['id']))

    def cancel(self,oid):
        row=self.db.one('SELECT * FROM broker_orders WHERE id=?',(oid,))
        if not row or not row['broker_id']:
            raise ValueError('Brokerorder noch unklar; erst abgleichen')
        paper_client(self.cfg).cancel_order_by_id(row['broker_id'])
        return {'status':'cancel_requested','id':oid}

    def flatten(self):
        self.reconcile()
        client=paper_client(self.cfg)
        rows=self.db.all('SELECT * FROM broker_orders')
        symbols=set()
        for row in rows:
            if row['status'] not in ('filled','canceled','expired','rejected') and row['broker_id']:
                client.cancel_order_by_id(row['broker_id'])
            if row['side']=='buy' and row['status']=='filled':
                symbols.add(row['symbol'])
        for symbol in symbols:
            positions={p.symbol:Decimal(p.qty) for p in client.get_all_positions()}
            if positions.get(symbol,Decimal(0))>=1:
                # Only symbols bought by this application's explicit paper validations.
                self.submit('atlas-flatten-'+datetime.now(timezone.utc).date().isoformat()+'-'+symbol,symbol,'sell',1)
        return {'close_requested':sorted(symbols)}
