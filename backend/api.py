import csv
import hashlib
import hmac
import io
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from typing import Literal
from pathlib import Path
import asyncio
import psutil
from fastapi import FastAPI,Request,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field
from .config import Settings,ROOT,now,eur,units
from .db import DB,uid,dumps,event,put
from .catalog import seed
from .ledger import Ledger,RiskError,snapshot,effective_limits,cash_caps
from .calendar import phase,BERLIN
from .intelligence import read_data,evaluate,propose_swap
from .worker import enqueue


class Login(BaseModel):
    password: str = Field(max_length=256)


class Action(BaseModel):
    action: str
    agent_id: int | None = Field(default=None,ge=1,le=100)
    other_agent_id: int | None = Field(default=None,ge=1,le=100)
    reason: str = Field(default='',max_length=2000)
    confirmed: bool = False


class Chat(BaseModel):
    text: str = Field(min_length=1,max_length=6000)


class Task(BaseModel):
    kind: str
    agent_id: int | None = Field(default=None,ge=1,le=100)
    symbol: str = Field(default='SPY',pattern=r'^[A-Z.]{1,10}$')
    strategy_id: str = ''
    cik: str = ''


class ImportBars(BaseModel):
    symbol: str = Field(pattern=r'^[A-Z.]{1,10}$')
    csv_text: str = Field(max_length=4_000_000)
    source: str = Field(min_length=3,max_length=100)
    licensed: bool
    adjustment: str = Field(pattern=r'^(raw|all)$')


class BrokerTest(BaseModel):
    symbol: str = Field(pattern=r'^[A-Z.]{1,10}$')
    side: Literal['buy','sell']
    order_type: Literal['market','limit','stop']
    limit_price: float | None = Field(default=None,gt=0)
    stop_price: float | None = Field(default=None,gt=0)
    confirmed: bool


def create_app(cfg=None,db=None):
    cfg=cfg or Settings()
    db=db or DB(cfg.database_path)
    db.init()
    seed(db)
    ledger=Ledger(db)
    @asynccontextmanager
    async def lifespan(app):
        from .cloud import CloudBridge
        from .providers import Providers
        from .management import ManagementService
        stop=asyncio.Event()
        cloud=asyncio.create_task(CloudBridge(db,cfg).run(stop))
        provider=Providers(db,cfg)
        news=asyncio.create_task(provider.news_stream())
        management=asyncio.create_task(ManagementService(db,cfg).run(stop))
        try:
            yield
        finally:
            stop.set()
            provider.stopping.set()
            cloud.cancel()
            news.cancel()
            management.cancel()
            await asyncio.gather(cloud,news,management,return_exceptions=True)
    app=FastAPI(title='ATLAS Paper Fund',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.db=db
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

    def authenticated(token):
        if not token:
            return False
        hashed=hashlib.sha256(token.encode()).hexdigest()
        return bool(db.one('SELECT 1 FROM auth_sessions WHERE token_hash=? AND expires_at>?',(hashed,now())))

    @app.middleware('http')
    async def security(request,call_next):
        if request.url.path.startswith('/api/') and request.url.path not in ('/api/login','/api/session','/api/health'):
            if not authenticated(request.cookies.get('atlas_session')):
                return JSONResponse({'detail':'Anmeldung erforderlich'},status_code=401)
        if request.method not in ('GET','HEAD','OPTIONS'):
            if request.url.path.startswith(('/api/broker/','/api/import/')):
                return JSONResponse({'detail':'Die Konsole erlaubt keine manuellen Trades oder Uploads'},status_code=403)
            origin=request.headers.get('origin')
            expected=f'{request.url.scheme}://{request.headers.get("host")}'
            if origin and origin!=expected:
                return JSONResponse({'detail':'Fremder Ursprung blockiert'},status_code=403)
            if request.headers.get('content-length','0').isdigit() and int(request.headers.get('content-length','0'))>4_500_000:
                return JSONResponse({'detail':'Anfrage zu groß'},status_code=413)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; connect-src 'self' ws://127.0.0.1:8765 ws://localhost:8765; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=400)

    @app.get('/api/health')
    def health():
        return {'status':'ok','paper_only':True}

    @app.get('/api/session')
    def session(request:Request):
        return {'authenticated':authenticated(request.cookies.get('atlas_session'))}

    @app.post('/api/login')
    def login(body:Login,request:Request):
        stamp=datetime.now(timezone.utc)
        key='login-rate-'+hashlib.sha256((request.client.host if request.client else 'local').encode()).hexdigest()
        with db.tx() as c:
            row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
            previous=json.loads(row[0]) if row else {'at':stamp.isoformat(),'attempts':0}
            if (stamp-datetime.fromisoformat(previous['at'])).total_seconds()>60:
                previous={'at':stamp.isoformat(),'attempts':0}
            if previous['attempts']>=5:
                raise HTTPException(429,'Zu viele Anmeldeversuche; eine Minute warten')
            previous['attempts']+=1
            put(c,key,previous)
        if ':' not in cfg.ceo_password_hash:
            raise HTTPException(503,'Lokales Setup ausführen')
        salt,expected=cfg.ceo_password_hash.split(':',1)
        actual=hashlib.scrypt(body.password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
        if not hmac.compare_digest(actual,expected):
            raise HTTPException(401,'Passwort ungültig')
        token=secrets.token_urlsafe(32)
        with db.tx() as c:
            c.execute('DELETE FROM auth_sessions WHERE expires_at<?',(now(),))
            c.execute('INSERT INTO auth_sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),(stamp+timedelta(hours=12)).isoformat(),now()))
        response=JSONResponse({'authenticated':True})
        response.set_cookie('atlas_session',token,httponly=True,samesite='strict',max_age=43200,secure=request.url.scheme=='https')
        return response

    @app.post('/api/logout')
    def logout(request:Request):
        token=request.cookies.get('atlas_session','')
        with db.tx() as c:
            c.execute('DELETE FROM auth_sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
        response=JSONResponse({'authenticated':False})
        response.delete_cookie('atlas_session')
        return response

    @app.get('/api/overview')
    def overview():
        fund=ledger.portfolio('fund')
        day=datetime.now(timezone.utc).astimezone(BERLIN).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
        opening=db.one("SELECT equity_u FROM equity WHERE portfolio_id='fund' AND created_at<? ORDER BY created_at DESC LIMIT 1",(day,))
        if not opening:
            opening=db.one("SELECT equity_u FROM equity WHERE portfolio_id='fund' AND created_at>=? ORDER BY created_at LIMIT 1",(day,))
        start=eur(opening['equity_u']) if opening else fund['initial_eur']
        fund['day_pnl_eur']=fund['equity_eur']-start
        fund['day_return_pct']=(fund['equity_eur']/start-1)*100 if start else 0
        heartbeat=db.get('worker_heartbeat')
        worker_online=bool(heartbeat and (datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat)).total_seconds()<45 and db.get('worker_identity',{}).get('pid',0)>0)
        benchmark=db.all('SELECT * FROM benchmark WHERE symbol=\'SPY\' ORDER BY created_at')
        benchmark_result=None
        if benchmark:
            first,last=benchmark[0],benchmark[-1]
            usd_return=float(Decimal(last['price_usd'])/Decimal(first['price_usd'])-1)*100
            eur_return=float((Decimal(last['price_usd'])/Decimal(last['fx']))/(Decimal(first['price_usd'])/Decimal(first['fx']))-1)*100
            benchmark_result={'symbol':'SPY','proxy_for':'S&P 500 ETF, ohne separate Dividendengutschrift',
                              'usd_return_pct':usd_return,'eur_return_pct':eur_return,
                              'start':first['market_at'],'end':last['market_at'],
                              'scope':'Ab erstem tatsächlich empfangenen Benchmarkkurs; kein Rückrechnen vor Datenbeginn'}
        return {'fund':fund,'clock':phase(db),'worker_online':worker_online,'benchmark':benchmark_result,
                'heartbeat':heartbeat,'paper_only':True,'trading_enabled':db.get('trading_enabled'),
                'risk_confirmed':db.get('risk_confirmed'),'kill_switch':db.get('kill_switch'),
                'agent_counts':db.all('SELECT department,COUNT(*) count,SUM(paused) paused FROM agents GROUP BY department'),
                'equity':db.all("SELECT * FROM (SELECT * FROM equity WHERE portfolio_id='fund' ORDER BY created_at DESC LIMIT 500) ORDER BY created_at"),
                'events':db.all('SELECT * FROM events ORDER BY id DESC LIMIT 25'),
                'news':db.all('SELECT * FROM news ORDER BY published_at DESC LIMIT 6'),
                'integrations':db.all('SELECT * FROM integrations ORDER BY name'),
                'recent_fills':db.all("SELECT * FROM fills WHERE portfolio_id='fund' ORDER BY created_at DESC LIMIT 10"),
                'execution':{'fills':db.one('SELECT COUNT(*) n FROM fills')['n'],
                             'pending':db.one("SELECT COUNT(*) n FROM orders WHERE status IN ('pending','triggered')")['n'],
                             'latest_decisions':db.all("SELECT agent_id,created_at,message,data FROM events WHERE kind='trading_decision' ORDER BY id DESC LIMIT 50"),
                             'signals':db.all('SELECT s.* FROM signal_decisions s JOIN (SELECT agent_id,MAX(rowid) seq FROM signal_decisions GROUP BY agent_id) latest ON s.rowid=latest.seq ORDER BY s.agent_id')},
                'decisions':db.all('SELECT * FROM decisions ORDER BY created_at DESC LIMIT 10'),
                'active_traders':db.one("SELECT COUNT(*) n FROM agents WHERE department IN ('fund','demo') AND paused=0")['n'] if worker_online and db.get('risk_confirmed') and db.get('trading_enabled') and not db.get('kill_switch') and phase(db)['trading'] else 0,
                'as_of':now()}

    @app.get('/api/agents')
    def agents():
        from .agent_state import agent_states
        states=agent_states(db)
        rows=db.all('SELECT * FROM agents ORDER BY id')
        for row in rows:
            e=db.one('SELECT * FROM evaluations WHERE agent_id=? ORDER BY created_at DESC LIMIT 1',(row['id'],))
            if not e or (datetime.now(timezone.utc)-datetime.fromisoformat(e['created_at'])).total_seconds()>300:
                evaluate(db,row['id'])
                e=db.one('SELECT * FROM evaluations WHERE agent_id=? ORDER BY created_at DESC LIMIT 1',(row['id'],))
            row.update(evaluation=e,**states[row['id']])
            row['manager_review']=db.one('SELECT * FROM manager_reviews WHERE agent_id=? ORDER BY created_at DESC LIMIT 1',(row['id'],))
        return rows

    @app.get('/api/agents/{aid}')
    def agent(aid:int):
        profile=db.one('SELECT * FROM agents WHERE id=?',(aid,))
        if not profile:
            raise HTTPException(404,'Agent fehlt')
        latest=db.one('SELECT created_at FROM evaluations WHERE agent_id=? ORDER BY created_at DESC LIMIT 1',(aid,))
        if not latest or (datetime.now(timezone.utc)-datetime.fromisoformat(latest['created_at'])).total_seconds()>300:
            evaluate(db,aid)
        result={'profile':profile}
        from .agent_state import agent_states
        result.update(agent_states(db,[aid])[aid])
        for table in ['strategies','memories','analyses','backtests','fills','positions','evaluations','events','agent_equity','signal_decisions']:
            result[table]=db.all(f'SELECT * FROM {table} WHERE agent_id=? ORDER BY '+('id' if table=='events' else 'created_at')+' DESC LIMIT 100',(aid,))
        result['decisions']=[x for x in db.all('SELECT * FROM decisions ORDER BY created_at DESC') if aid in [json.loads(x['payload']).get(k) for k in ('agent_id','first','second')]][:50]
        from .reporting import day_view
        result['day']=day_view(db,aid)
        result['manager_review']=result['day']['manager_review']
        return result

    @app.post('/api/agents/{aid}/report')
    def request_report(aid:int):
        from .reporting import queue_report
        if not 1<=aid<=100:raise HTTPException(404,'Agent fehlt')
        return {'job_id':queue_report(db,cfg,aid)}

    @app.get('/api/trading-floor')
    def trading_floor():
        from .reporting import window
        day,start,end=window()
        return {'date':day,'traders':[r for r in agents() if r['department']=='fund'],
                'activity':db.all("SELECT f.*,o.reason FROM fills f JOIN orders o ON o.id=f.order_id WHERE f.portfolio_id='fund' AND f.created_at>=? AND f.created_at<? ORDER BY f.created_at DESC",(start,end)),
                'as_of':now(),'paper_only':True}

    @app.get('/api/portfolios')
    def portfolios():
        with db.tx() as c:
            return [snapshot(c,x['id']) for x in c.execute("SELECT id FROM portfolios WHERE kind!='research'").fetchall()]

    @app.get('/api/closeout')
    def closeout():
        from .daily import closeout_view
        return closeout_view(db)

    @app.get('/api/research')
    def research(offset:int=0):
        from .daily import research_view
        if offset<0 or offset>1000000:raise HTTPException(400,'Ungültiger Seitenoffset')
        return research_view(db,offset)

    @app.get('/api/research/agents/{aid}')
    def research_agent(aid:int,offset:int=0):
        from .research import agent_research
        if not 1<=aid<=100:raise HTTPException(404,'Agent fehlt')
        if offset<0 or offset>1000000:raise HTTPException(400,'Ungültiger Seitenoffset')
        return agent_research(db,aid,offset)

    @app.get('/api/research-roster')
    def research_roster():
        from .research import research_roster,research_window
        return {'agents':research_roster(db),'window':research_window(),'as_of':now()}

    @app.get('/api/team')
    def team(offset:int=0):
        from .research import team_view
        if offset<0 or offset>1000000:raise HTTPException(400,'Ungültiger Seitenoffset')
        return team_view(db,offset)

    @app.get('/api/portfolio/{pid}')
    def portfolio(pid:str):
        return {'portfolio':ledger.portfolio(pid),
                'ledger':db.all('SELECT * FROM ledger WHERE portfolio_id=? ORDER BY created_at DESC LIMIT 500',(pid,)),
                'fills':db.all('SELECT * FROM fills WHERE portfolio_id=? ORDER BY created_at DESC LIMIT 500',(pid,)),
                'equity':db.all('SELECT * FROM equity WHERE portfolio_id=? ORDER BY created_at DESC LIMIT 500',(pid,))}

    @app.get('/api/data/{dataset}')
    def data(dataset:str,agent_id:int|None=None,offset:int=0):
        if dataset=='quotes':
            return db.all('SELECT * FROM quotes ORDER BY symbol')
        if dataset=='jobs':
            return db.all('SELECT id,kind,agent_id,priority,status,attempts,created_at,updated_at,error FROM jobs ORDER BY created_at DESC LIMIT 200')
        if dataset=='orders_all':
            return db.all('SELECT * FROM orders ORDER BY created_at DESC LIMIT 200')
        if dataset=='broker':
            return db.all('SELECT * FROM broker_orders ORDER BY created_at DESC LIMIT 100')
        return read_data(db,dataset,agent_id,offset)

    @app.get('/api/chats')
    def chats():
        return db.all('SELECT * FROM (SELECT rowid seq,* FROM chats ORDER BY created_at DESC,rowid DESC LIMIT 200) ORDER BY created_at,seq')

    @app.post('/api/chat')
    def chat(body:Chat):
        from .manager import create_request
        return create_request(db,cfg,body.text)

    @app.post('/api/task')
    def task(body:Task):
        allowed={'diagnose','fx','openai_test','analysis','historical','news','calendar','backtest','edgar','backup','daily_review','intraday'}
        if body.kind not in allowed:
            raise ValueError('Aufgabe nicht freigegeben')
        if body.kind in ('analysis','backtest') and body.agent_id is None:
            raise ValueError('Agent erforderlich')
        return {'job_id':enqueue(db,body.kind,body.model_dump(exclude={'kind','agent_id'}),body.agent_id,priority=5)}

    @app.get('/api/jobs/{jid}')
    def job(jid:str):
        row=db.one('SELECT * FROM jobs WHERE id=?',(jid,))
        if not row:
            raise HTTPException(404,'Aufgabe fehlt')
        return row

    @app.post('/api/jobs/{jid}/retry')
    def retry(jid:str):
        with db.tx() as c:
            row=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            if not row or row['status'] not in ('failed','blocked') or row['kind']=='broker_submit':
                raise ValueError('Aufgabe nicht sicher wiederholbar')
            c.execute("UPDATE jobs SET status='pending',available_at=?,updated_at=?,attempts=0 WHERE id=?",(now(),now(),jid))
        return {'job_id':jid}

    @app.post('/api/action')
    def action(body:Action):
        if body.action=='kill':
            db.set('kill_switch',True)
            for row in db.all("SELECT id FROM orders WHERE side='buy' AND status IN ('pending','triggered')"):
                ledger.cancel(row['id'],'CEO-Not-Aus')
            db.event('kill_switch','CEO-Not-Aus aktiviert; kontrollierte Schließung soweit Markt/Daten es erlauben',level='critical')
            return {'kill_switch':True}
        if not body.confirmed:
            raise ValueError('Explizite CEO-Bestätigung erforderlich')
        if body.action in ('pause_agent','resume_agent'):
            if body.agent_id is None:
                raise ValueError('Agent erforderlich')
            with db.tx() as c:
                c.execute('UPDATE agents SET paused=? WHERE id=?',(int(body.action=='pause_agent'),body.agent_id))
                event(c,body.action,body.reason or 'CEO-Anweisung',body.agent_id)
            if body.action=='pause_agent':
                for o in db.all("SELECT id FROM orders WHERE agent_id=? AND side='buy' AND status IN ('pending','triggered')",(body.agent_id,)):
                    ledger.cancel(o['id'],'Agent pausiert')
        elif body.action=='risk_confirm':
            db.set('risk_confirmed',True)
            db.event('risk_confirmed','CEO hat konservative Anfangsgrenzen bestätigt',data=db.get('risk_limits'))
        elif body.action=='start_trading':
            if not db.get('risk_confirmed') or not cfg.has_alpaca or not cfg.openai_api_key or not ledger.reconcile():
                raise ValueError('Risikofreigabe, API-Schlüssel oder Ledger-Abgleich fehlen')
            db.set('kill_switch',False)
            db.set('trading_enabled',True)
        elif body.action=='stop_trading':
            db.set('trading_enabled',False)
            for o in db.all("SELECT id FROM orders WHERE side='buy' AND status IN ('pending','triggered')"):
                ledger.cancel(o['id'],'Trading pausiert')
        elif body.action in ('engine_pause','engine_resume'):
            db.set('engine_enabled',body.action=='engine_resume')
        elif body.action=='worker_stop':
            db.set('worker_stop_requested',True)
            db.set('supervisor_paused',True)
        elif body.action=='rotation':
            return propose_swap(db,body.agent_id,body.other_agent_id,body.reason)
        else:
            raise ValueError('Aktion nicht verfügbar')
        db.event('ceo_action',body.action,data=body.model_dump())
        return {'ok':True}

    @app.post('/api/decisions/{did}/confirm')
    def confirm(did:str,body:Action):
        if not body.confirmed:
            raise ValueError('Explizite CEO-Bestätigung erforderlich')
        with db.tx() as c:
            row=c.execute('SELECT * FROM decisions WHERE id=?',(did,)).fetchone()
            if not row or row['status']!='proposed':
                raise ValueError('Kein offener Vorschlag')
            payload=json.loads(row['payload'])
            status='approved'
            applied=None
            if row['kind'] in ('pause_agent','resume_agent'):
                c.execute('UPDATE agents SET paused=? WHERE id=?',(int(row['kind']=='pause_agent'),payload['agent_id']))
                status='applied'
                applied=now()
            c.execute('UPDATE decisions SET status=?,applied_at=? WHERE id=?',(status,applied,did))
            event(c,'decision_confirmed','CEO bestätigt Manager-Vorschlag',data={'decision_id':did})
        return {'status':status}

    @app.post('/api/orders/{oid}/cancel')
    def cancel(oid:str):
        return ledger.cancel(oid)

    @app.post('/api/evaluate')
    def evaluations():
        return [evaluate(db,i) for i in range(1,101)]

    @app.post('/api/broker/submit')
    def broker_submit(body:BrokerTest):
        if not body.confirmed:
            raise ValueError('CEO-Bestätigung für getrennte Broker-Paper-Testorder erforderlich')
        return {'job_id':enqueue(db,'broker_submit',body.model_dump(exclude={'confirmed'})|{'qty':1,'client_id':'atlas-test-'+uid()},priority=2)}

    @app.post('/api/broker/{oid}/cancel')
    def broker_cancel(oid:str):
        if not db.one('SELECT id FROM broker_orders WHERE id=?',(oid,)):
            raise HTTPException(404,'Brokerorder fehlt')
        return {'job_id':enqueue(db,'broker_cancel',{'oid':oid},priority=1)}

    @app.post('/api/import/bars')
    def import_bars(body:ImportBars):
        if not body.licensed:
            raise ValueError('Zulässige Datennutzung muss bestätigt werden')
        reader=csv.DictReader(io.StringIO(body.csv_text))
        if not {'time','open','high','low','close','volume'}.issubset(reader.fieldnames or []):
            raise ValueError('CSV-Spalten: time,open,high,low,close,volume')
        count=0
        with db.tx() as c:
            for row in reader:
                count+=1
                if count>20000:
                    raise ValueError('Maximal 20.000 Bars je Import')
                stamp=datetime.fromisoformat(row['time'].replace('Z','+00:00'))
                if stamp.tzinfo is None or stamp>datetime.now(timezone.utc):
                    raise ValueError('Historischer Zeitstempel mit Zeitzone erforderlich')
                values=[Decimal(row[x]) for x in ('open','high','low','close')]
                if not all(x.is_finite() and x>0 for x in values) or min(values[0],values[3])<values[2] or max(values[0],values[3])>values[1] or int(row['volume'])<0:
                    raise ValueError('Ungültiger OHLCV-Bar')
                c.execute('INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',(body.symbol,stamp.isoformat(),'1Day',*[str(x) for x in values],int(row['volume']),'Import: '+body.source,body.adjustment))
        db.event('import',f'{body.symbol}: {count} historische Bars importiert',data={'source':body.source,'adjustment':body.adjustment})
        return {'imported':count}

    @app.get('/api/system')
    def system():
        memory=psutil.virtual_memory()
        with db.tx() as c:
            active_risk=effective_limits(c)
            active_caps=cash_caps(c,'fund')
        disk=psutil.disk_usage(ROOT.anchor)
        usage=db.all("SELECT agent_id,model,COUNT(*) requests,SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(CASE WHEN status='settled' THEN cost_u ELSE reserved_u END) cost_bound_u FROM usage GROUP BY agent_id,model")
        stamp=datetime.now(timezone.utc).astimezone(BERLIN)
        totals={}
        for name,start in [('day',stamp.replace(hour=0,minute=0,second=0,microsecond=0)),('month',stamp.replace(day=1,hour=0,minute=0,second=0,microsecond=0))]:
            rows_cost=db.one("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost_u ELSE reserved_u END),0) amount FROM usage WHERE created_at>=?",(start.astimezone(timezone.utc).isoformat(),))
            totals[name+'_cost_bound_eur']=eur(rows_cost['amount'])
        return {'cpu_pct':psutil.cpu_percent(),'ram_pct':memory.percent,'ram_available_gb':memory.available/1e9,
                'disk_free_gb':disk.free/1e9,'integrations':db.all('SELECT * FROM integrations ORDER BY name'),
                'worker_heartbeat':db.get('worker_heartbeat'),'engine_enabled':db.get('engine_enabled'),
                'queue':db.all('SELECT status,COUNT(*) count FROM jobs GROUP BY status'),
                'usage':usage,'budget_monthly_eur':float(cfg.monthly_budget_eur),'budget_daily_eur':None,**totals,
                'risk':active_risk,'fund_cash_limits':active_caps,'paper_sizing_mode':db.get('paper_sizing_mode','capped'),'risk_confirmed':db.get('risk_confirmed'),
                'configured':{'openai':bool(cfg.openai_api_key),'alpaca':cfg.has_alpaca,'sec':bool(cfg.sec_user_agent)},
                'model':cfg.openai_model,'manager_model':cfg.openai_manager_model,'feed':cfg.alpaca_feed,
                'stock_universe':{'tradable_count':db.one("SELECT COUNT(*) n FROM assets WHERE tradable=1 AND asset_class='us_equity'")['n'],
                                  'data_scope':'Alpaca US-Aktien/ETFs; Daten nach Bedarf, IEX ist kein Gesamtmarktfeed'},
                'market_data_policy':db.get('market_data_policy'),
                'watchlist':cfg.symbols,'fx':db.one('SELECT * FROM fx ORDER BY date DESC LIMIT 1'),
                'backups':len(list((ROOT/'backups').glob('fund-*.sqlite3'))),'paper_only':True,
                'remote_access':'Supabase: geschützte Cloud-Konsole; lokale Engine führt geprüfte Aktionen aus' if cfg.cloud_sync_enabled else 'blocked: nur Loopback. Supabase-Konsole noch nicht eingerichtet.'}

    @app.websocket('/api/live')
    async def live(ws:WebSocket):
        origin=ws.headers.get('origin','')
        if not authenticated(ws.cookies.get('atlas_session')) or origin not in ('http://127.0.0.1:8765','http://localhost:8765'):
            await ws.close(code=4401)
            return
        await ws.accept()
        after=0
        try:
            while True:
                if not authenticated(ws.cookies.get('atlas_session')):
                    await ws.close(code=4401)
                    break
                events=db.all('SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100',(after,))
                if events:
                    after=events[-1]['id']
                await ws.send_json({'type':'update','events':events,'at':now()})
                await asyncio.sleep(3)
        except (WebSocketDisconnect,RuntimeError):
            pass

    dist=ROOT/'frontend'/'dist'
    if (dist/'assets').exists():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')

    @app.get('/{path:path}')
    def frontend(path:str):
        if path.startswith('api/'):
            raise HTTPException(404)
        if not (dist/'index.html').exists():
            return JSONResponse({'detail':'Frontend noch bauen: npm run build in frontend'},status_code=503)
        return FileResponse(dist/'index.html')

    return app


app=create_app()
