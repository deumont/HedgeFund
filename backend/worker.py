"""Durable task queue and one autonomous worker, independent of all browser sessions."""
import asyncio
import json
import os
import signal
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_UP
from .config import Settings,ROOT,now
from .db import DB,uid,dumps,event,put
from .catalog import seed
from .calendar import phase,BERLIN
from .ledger import Ledger,RiskError
from .providers import Providers,BrokerValidation,safe_error
from .intelligence import AI,BudgetError,manager_chat,evaluate,apply_rotations,propose_swap
from .backtest import run_backtest
from .signals import SignalEngine
from .research import research_window,require_research,ResearchClosed


def enqueue(db,kind,payload=None,agent_id=None,priority=50,dedupe=None):
    jid=uid()
    stamp=now()
    with db.tx() as c:
        c.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?,?,0,?,?,?,NULL)',
                  (jid,dedupe or jid,kind,agent_id,dumps(payload or {}),priority,'pending',stamp,stamp,stamp))
        row=c.execute('SELECT id FROM jobs WHERE dedupe=?',(dedupe or jid,)).fetchone()
    return row['id']


class Worker:
    def __init__(self,db,cfg):
        self.db,self.cfg=db,cfg
        self.providers=Providers(db,cfg)
        self.ledger=Ledger(db)
        self.ai=AI(db,cfg)
        self.stop=asyncio.Event()
        self.stream_task=None
        self.running_job=None
        self.signals=SignalEngine(db)
        self.backup_dir=ROOT/'backups'

    async def run(self):
        # PID identity + heartbeat guard against accidentally launching a second worker.
        import psutil
        with self.db.tx() as c:
            previous=c.execute("SELECT value FROM meta WHERE key='worker_identity'").fetchone()
            if previous:
                p=json.loads(previous[0])
                if p['pid']>0 and psutil.pid_exists(p['pid']):
                    proc=psutil.Process(p['pid'])
                    if abs(proc.create_time()-p['created'])<1:
                        raise RuntimeError('Ein Worker läuft bereits')
            put(c,'worker_identity',{'pid':os.getpid(),'created':psutil.Process().create_time()})
            # Provider side effects never auto-retry on process death. Internal writes are transactional.
            c.execute("UPDATE jobs SET status=CASE WHEN kind='broker_submit' THEN 'uncertain' ELSE 'pending' END,updated_at=? WHERE status='running' AND kind NOT IN ('agent_report','manager_review','manager_daily')",(now(),))
            c.execute("UPDATE jobs SET priority=45 WHERE kind='backtest' AND status='pending' AND priority>=60")
            put(c,'worker_stop_requested',False)
        self.ledger.reconcile()
        self.db.event('worker','Hintergrund-Engine gestartet; dauerhafter Zustand geladen')
        enqueue(self.db,'diagnose',priority=0,dedupe='startup-'+uid())
        enqueue(self.db,'fx',priority=0,dedupe='fx-start-'+uid())
        self.stream_task=asyncio.create_task(self.providers.market_stream())
        safety=asyncio.create_task(self.safety_loop())
        next_tick=0
        try:
            while not self.stop.is_set():
                self.db.set('worker_heartbeat',now())
                if self.db.get('worker_stop_requested'):
                    break
                clock=phase(self.db)
                if clock['phase']=='stopped':
                    self.db.event('schedule','19:00 erreicht: Arbeiten sichern, Backup und Ende')
                    break
                if asyncio.get_running_loop().time()>=next_tick:
                    await self.tick(clock)
                    next_tick=asyncio.get_running_loop().time()+10
                job=self.claim()
                if job:
                    self.running_job=job
                    try:
                        result=await self.execute(job)
                        with self.db.tx() as c:
                            c.execute("UPDATE jobs SET status='completed',payload=?,updated_at=?,error=NULL WHERE id=?",(dumps(json.loads(job['payload'])|{'result':result}),now(),job['id']))
                    except ResearchClosed as exc:
                        with self.db.tx() as c:
                            c.execute("UPDATE jobs SET status='pending',attempts=MAX(0,attempts-1),available_at=?,error=?,updated_at=? WHERE id=?",
                                (datetime.fromisoformat(research_window()['next_start']).astimezone(timezone.utc).isoformat(),str(exc),now(),job['id']))
                    except BudgetError as exc:
                        self.fail(job,str(exc),'blocked')
                    except (RiskError,ValueError) as exc:
                        self.fail(job,str(exc),'failed')
                    except Exception as exc:
                        # A failed API call can still have been billed. AI.reserve retained its bound.
                        attempts=job['attempts']
                        if attempts<3 and job['kind'] not in ('broker_submit','chat'):
                            stamp=(datetime.now(timezone.utc)+timedelta(seconds=15*2**attempts)).isoformat()
                            with self.db.tx() as c:
                                c.execute("UPDATE jobs SET status='pending',available_at=?,updated_at=?,error=? WHERE id=?",(stamp,now(),safe_error(exc),job['id']))
                        else:
                            self.fail(job,safe_error(exc),'uncertain' if job['kind']=='broker_submit' else 'failed')
                    finally:
                        self.running_job=None
                else:
                    try:
                        await asyncio.wait_for(self.stop.wait(),timeout=1)
                    except asyncio.TimeoutError:
                        pass
        finally:
            safety.cancel()
            await asyncio.gather(safety,return_exceptions=True)
            self.providers.stopping.set()
            if self.stream_task:
                self.stream_task.cancel()
                await asyncio.gather(self.stream_task,return_exceptions=True)
            for row in self.db.all("SELECT id FROM orders WHERE status IN ('pending','triggered')"):
                self.ledger.cancel(row['id'],'Worker-Ende: offene interne Order storniert')
            if self.db.one('SELECT id FROM positions LIMIT 1'):
                self.db.event('overnight_exception','Offene Positionen beim Ende: Schließung konnte nicht bestätigt werden',level='critical')
            self.ledger.record_equity()
            self.db.backup(self.backup_dir)
            self.db.set('worker_stopped_at',now())
            self.db.set('worker_identity',{'pid':0,'created':0})
            self.db.event('worker','Engine beendet; Datenbankbackup geprüft')

    def fail(self,job,error,status):
        with self.db.tx() as c:
            c.execute('UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=?',(status,error,now(),job['id']))
            event(c,'job_'+status,error,job['agent_id'],level='warning',data={'job_id':job['id'],'kind':job['kind']})
        if job['kind']=='chat':
            from .manager import save_reply
            mid=json.loads(job['payload']).get('message_id')
            if mid:
                save_reply(self.db,mid,'Anfrage konnte nicht abgeschlossen werden: '+error,[{'source':'Systemmeldung','job_id':job['id']}])

    def claim(self):
        research_open=research_window()['open']
        with self.db.tx() as c:
            row=c.execute("SELECT * FROM jobs WHERE status='pending' AND kind NOT IN ('agent_report','manager_review','manager_daily') AND (? OR kind NOT IN ('analysis','backtest')) AND available_at<=? ORDER BY priority,created_at LIMIT 1",(research_open,now())).fetchone()
            if row and row['kind'] in ('analysis','backtest'):
                # A continuing stream of historical tests must not starve each
                # agent's analysis. Provider/safety tasks keep their priority.
                other='analysis' if getattr(self,'last_research_kind','backtest')=='backtest' else 'backtest'
                candidate=c.execute("SELECT * FROM jobs WHERE status='pending' AND kind=? AND available_at<=? ORDER BY priority,created_at LIMIT 1",(other,now())).fetchone()
                if candidate:row=candidate
                self.last_research_kind=row['kind']
            if row:
                c.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=?",(now(),row['id']))
                return dict(row)|{'attempts':row['attempts']+1}
        return None

    async def tick(self,clock):
        stamp=datetime.now(timezone.utc)
        local=stamp.astimezone(BERLIN)
        day=clock['date']
        # Safety processing runs while waiting for model I/O too (separate task below).
        self.safety_tick(clock)
        if clock['liquidating'] and self.cfg.has_alpaca:
            enqueue(self.db,'broker_flatten',priority=0,dedupe='broker-flat-'+day)
        if self.db.get('last_equity_minute')!=stamp.isoformat()[:16]:
            self.ledger.record_equity()
            self.db.set('last_equity_minute',stamp.isoformat()[:16])
        apply_rotations(self.db,stamp)
        enqueue(self.db,'fx',priority=2,dedupe='fx-'+day)
        if self.cfg.has_alpaca:
            if self.db.get('universe_scan_bucket')!=stamp.isoformat()[:14]+str(stamp.minute//5):
                from .universe import rotate
                rotate(self.db,self.cfg)
                self.db.set('universe_scan_bucket',stamp.isoformat()[:14]+str(stamp.minute//5))
            enqueue(self.db,'calendar',priority=2,dedupe='calendar-'+day)
            enqueue(self.db,'assets',priority=3,dedupe='assets-'+day)
            enqueue(self.db,'news',priority=5,dedupe='news-'+stamp.isoformat()[:16])
            enqueue(self.db,'broker_reconcile',priority=3,dedupe='broker-'+stamp.isoformat()[:16])
            if clock['trading'] or clock['phase']=='preparing':
                enqueue(self.db,'intraday',priority=4,dedupe='bars15-'+stamp.isoformat()[:16])
            if clock['phase']=='preparing':
                for symbol in self.cfg.symbols:
                    enqueue(self.db,'historical',{'symbol':symbol},priority=30,dedupe='history-'+day+'-'+symbol)
        self.schedule_research(stamp)

    def schedule_research(self,stamp):
        if not self.cfg.openai_api_key or not self.db.get('engine_enabled') or not research_window(stamp)['open']:return
        local=stamp.astimezone(BERLIN);day=local.date().isoformat()
        bucket=max(0,(local.hour*60+local.minute-450)//60)
        if getattr(self,'research_bucket',None)==(day,bucket):return
        catalog=[r['symbol'] for r in self.db.all("SELECT symbol FROM assets WHERE tradable=1 AND asset_class='us_equity' ORDER BY symbol")]
        headlines=self.db.all('SELECT headline,symbols FROM news ORDER BY published_at DESC LIMIT 300')
        rotation=local.date().toordinal()%100
        for agent in self.db.all('SELECT * FROM agents WHERE paused=0 ORDER BY (id+?)%100',(rotation,)):
            from .news_agents import prepare_strategy,mandate
            from .universe import research_symbols
            prepare_strategy(self.db,agent['id'])
            aid=agent['id'];strategy=self.db.one('SELECT * FROM strategies WHERE agent_id=? ORDER BY version DESC LIMIT 1',(aid,))
            symbols=research_symbols(self.db,self.cfg,aid,local,bucket,catalog,headlines)
            symbol=symbols[0] if symbols else 'SPY'
            profile=mandate(self.db,aid)
            assignment={'work_date':day,'department':agent['department'],'focus':profile.get('focus',agent['name']),
                'assignment':profile.get('mandate',agent['mandate']),'approach':profile['approach'],'strategy_id':strategy['id'],'symbol':symbol,'research_symbols':symbols}
            # Resume one durable task per individual agent, instead of accumulating
            # a new paid request every hour while that agent is still waiting.
            with self.db.tx() as c:
                jobs=c.execute("SELECT id,payload,status FROM jobs WHERE agent_id=? AND kind='analysis' AND status IN ('pending','running') ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END,created_at",(aid,)).fetchall()
                if jobs:
                    first=jobs[0];payload=json.loads(first['payload']);updated={**payload,**assignment}
                    if updated!=payload:c.execute('UPDATE jobs SET payload=? WHERE id=?',(dumps(updated),first['id']))
                    for duplicate in jobs[1:]:
                        if duplicate['status']=='pending':
                            c.execute("UPDATE jobs SET status='superseded',error='Doppelter Forschungsauftrag durch individuellen Tagesauftrag ersetzt',updated_at=? WHERE id=?",(now(),duplicate['id']))
            if not jobs:
                enqueue(self.db,'analysis',assignment,aid,60,dedupe=f'analysis-{day}-morning-{bucket}-{aid}')
            if profile['approach']=='news':
                # Discretionary agents study public information, not a fictional
                # fixed-rule backtest. Preserve completed historical studies.
                with self.db.tx() as c:c.execute("UPDATE jobs SET status='superseded',error='Diskretionärer Informationshandel: Online-Recherche statt automatischer Backtests',updated_at=? WHERE agent_id=? AND kind='backtest' AND status='pending'",(now(),aid))
                continue
            for stock in symbols:
                pending=self.db.all("SELECT payload FROM jobs WHERE agent_id=? AND kind='backtest' AND status IN ('pending','running')",(aid,))
                if not any(json.loads(p['payload']).get('strategy_id')==strategy['id'] and json.loads(p['payload']).get('symbol')==stock for p in pending):
                    enqueue(self.db,'backtest',{**assignment,'symbol':stock},aid,45,dedupe=f"morning-test-{day}-{bucket}-{strategy['id']}-{stock}")
        self.research_bucket=(day,bucket)

    def monitor_signals(self,at=None):
        """No inactivity counters, no trade quota, no time-since-last-trade trigger."""
        clock=phase(self.db,at)
        if not clock['trading']:
            return
        from .news_agents import mandate,relevant_news
        from .universe import eligible,active_symbols
        # Runtime news assessment interprets current events; it cannot modify a
        # strategy or run a backtest after the separate research cutoff.
        news_bucket=int((at or datetime.now(timezone.utc)).timestamp())//60
        scan_news=getattr(self,'news_bucket',None)!=news_bucket
        self.news_bucket=news_bucket
        for agent in self.db.all("SELECT id FROM agents WHERE department!='research' AND paused=0"):
            aid=agent['id']
            if not scan_news or mandate(self.db,aid)['approach']!='news' or not self.cfg.openai_api_key:continue
            from .research_desks import watched_symbols
            symbols=watched_symbols(self.db,aid)
            checked=now();matched=0
            import hashlib
            web_hour=news_bucket//60
            for symbol in symbols:
                own=relevant_news(self.db,symbol,8)
                own=[n for n in own if symbol in json.loads(n['symbols'])]
                matched+=len(own)
                digest=hashlib.sha256((symbol+dumps(own)).encode()).hexdigest()[:20]
                # Fresh feed revisions wake assessment even within the same 15m
                # strategy bar. Hosted web background is cached at most one hour.
                key=f'news-thesis-{aid}-{symbol}-{web_hour}-{digest}'
                pending=self.db.all("SELECT payload FROM jobs WHERE agent_id=? AND kind='news_thesis' AND status IN ('pending','running')",(aid,))
                if not any(json.loads(p['payload']).get('symbol')==symbol for p in pending):
                    enqueue(self.db,'news_thesis',{'symbol':symbol},aid,25,dedupe=key)
            self.db.set('agent-news-monitor-'+str(aid),{'checked_at':checked,'symbols':symbols,'relevant_articles':matched,'feed_interval_seconds':60,'web_refresh_seconds':3600,
                'feed':self.db.one("SELECT status,checked_at FROM integrations WHERE name='news_stream'")})
        for agent in self.db.all("SELECT id FROM agents WHERE department!='research' AND paused=0"):
            aid=agent['id']
            positions=self.db.all('SELECT symbol FROM positions WHERE agent_id=?',(aid,))
            from .universe import active_symbols
            candidates=active_symbols(self.db,self.cfg)
            preferred=self.db.get('agent-stock-'+str(aid))
            if mandate(self.db,aid)['approach']=='news':
                thesis=self.db.one('SELECT symbol FROM event_theses WHERE agent_id=? ORDER BY created_at DESC LIMIT 1',(aid,))
                if thesis:preferred=thesis['symbol']
            owned={p['symbol'] for p in positions}
            candidate=preferred or (candidates[(aid-1)%len(candidates)] if candidates else None)
            symbols=list(dict.fromkeys([p['symbol'] for p in positions]+([candidate] if candidate else [])))
            for symbol in symbols:
                side='sell' if symbol in owned else 'buy'
                decision=self.signals.evaluate(aid,symbol,side,at)
                if decision.valid:
                    self.execute_signal(aid,symbol,side,decision,at)
                elif symbol in owned and mandate(self.db,aid)['approach']=='news':
                    addition=self.signals.evaluate(aid,symbol,'buy',at)
                    if addition.valid:self.execute_signal(aid,symbol,'buy',addition,at)

    def execute_signal(self,aid,symbol,side,decision,at=None):
        from .execution import plan_order
        # The stored strategy is the decision maker. LLM research may improve future
        # versions, but unavailable models/budgets must not disable a valid strategy.
        final_action='HOLD'
        order_id=None
        try:
            if side=='buy' and (not self.db.get('trading_enabled') or not self.db.get('risk_confirmed') or self.db.get('kill_switch')):
                raise RiskError('Neue Positionen gesperrt: Handels-/Risikofreigabe oder Not-Aus')
            bar=decision.observations.get('last_bar_end',decision.id)
            key=f'strategy-{aid}-{symbol}-{side}-{decision.strategy_id}-{bar}'
            order=self.db.one('SELECT * FROM orders WHERE client_id=?',(key,))
            if order and order['status'] not in ('pending','triggered'):
                return
            if not order:
                plan=plan_order(self.db,aid,symbol,side,at)
                order=self.ledger.submit(aid,symbol,side,client_id=key,
                    reason=decision.reason+'; gespeicherte Strategie, deterministische Risikogröße',at=at,**plan)
            order_id=order['id']
            fill=self.ledger.fill(order_id,at)
            if fill and self.cfg.openai_api_key:
                from .reporting import queue_report
                queue_report(self.db,self.cfg,aid)
            final_action='FILLED' if fill or order['status']=='filled' else 'ORDER_PENDING'
            reason=decision.reason
        except RiskError as exc:
            reason=str(exc)
        state={'signal_id':decision.id,'symbol':symbol,'side':side,'final_action':final_action,'order_id':order_id,'reason':reason}
        marker=f'execution-decision-{aid}-{symbol}-{side}'
        if self.db.get(marker)!=state:
            self.db.event('trading_decision',reason,aid,data=state)
            self.db.set(marker,state)

    def safety_tick(self,clock=None):
        clock=clock or phase(self.db)
        kill=self.db.get('kill_switch')
        # Independent continuous loss limits, even when no model request is running.
        with self.db.tx() as c:
            from .ledger import effective_limits,cash_caps
            limits=effective_limits(c)
        stamp=datetime.now(timezone.utc)
        day_start=stamp.astimezone(BERLIN).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
        for p in self.db.all("SELECT DISTINCT portfolio_id FROM positions"):
            pid=p['portfolio_id']
            state=self.ledger.portfolio(pid)
            opening=self.db.one('SELECT equity_u FROM equity WHERE portfolio_id=? AND created_at<? AND valuation_complete=1 ORDER BY created_at DESC LIMIT 1',(pid,day_start))
            initial=opening['equity_u']/1e6 if opening else state['initial_eur']
            with self.db.tx() as c:
                caps=cash_caps(c,pid)
            day_limit=min(initial*limits['max_daily_loss_pct'],caps.get('max_daily_loss_eur',float('inf')))
            breach=state['valuation_complete'] and (state['drawdown_pct']/100>=limits['max_drawdown_pct']
                    or initial-state['equity_eur']>=day_limit
                    or state['drawdown_eur']>=caps.get('max_drawdown_eur',float('inf')))
            if breach and not self.db.get('risk_halt_'+pid):
                self.db.set('risk_halt_'+pid,True)
                self.db.event('risk_halt','Portfolio-Verlustlimit erreicht: neue Einstiege gesperrt, Schließung angefordert',level='critical',data={'portfolio':pid})
                if pid=='fund':
                    self.db.set('kill_switch',True)
                    kill=True
        for row in self.db.all("SELECT * FROM orders WHERE status IN ('pending','triggered')"):
            if row['side']=='buy':
                from .ledger import agent_exposure
                state=self.ledger.portfolio(row['portfolio_id'])
                reserved=self.db.one("SELECT COALESCE(SUM(reserved_u),0) n FROM orders WHERE portfolio_id=? AND agent_id=? AND side='buy' AND status IN ('pending','triggered')",(row['portfolio_id'],row['agent_id']))['n']
                if agent_exposure(state['positions'],row['agent_id'])+reserved>state['equity_eur']*1e6*limits['max_agent_pct']:
                    self.ledger.cancel(row['id'],'Kapitalgrenze pro Agent einschließlich offener Kauforders')
                    continue
            if (row['side']=='buy' and (not clock['trading'] or kill or self.db.get('risk_halt_'+row['portfolio_id']))) or clock['phase'] in ('review','stopped','closed','calendar_missing'):
                self.ledger.cancel(row['id'],'Zeit-/Risikosperre')
                continue
            try:
                self.ledger.fill(row['id'])
            except RiskError:
                pass
        # Stops/take profits are deterministic, independent of any LLM response.
        for pos in self.db.all('SELECT * FROM positions'):
            q=self.db.one('SELECT * FROM quotes WHERE symbol=?',(pos['symbol'],))
            if not q:
                continue
            hit=Decimal(q['bid'])<=Decimal(pos['stop_usd']) or (pos['take_usd'] and Decimal(q['bid'])>=Decimal(pos['take_usd']))
            from .ledger import agent_exposure
            state=self.ledger.portfolio(pos['portfolio_id'])
            own=agent_exposure(state['positions'],pos['agent_id'])
            cap=state['equity_eur']*1e6*limits['max_agent_pct']
            excess=own-cap
            if hit or kill or clock['liquidating'] or self.db.get('risk_halt_'+pos['portfolio_id']) or excess>0:
                pending_orders=self.db.all("SELECT id,side FROM orders WHERE agent_id=? AND symbol=? AND status IN ('pending','triggered')",(pos['agent_id'],pos['symbol']))
                if any(x['side']=='sell' for x in pending_orders):
                    continue
                for pending in pending_orders:
                    self.ledger.cancel(pending['id'],'Schutzschließung hat Vorrang')
                try:
                    qty=pos['qty']
                    reason='Schutzstop/Take Profit/Not-Aus/Tagesende'
                    if excess>0 and not (hit or kill or clock['liquidating'] or self.db.get('risk_halt_'+pos['portfolio_id'])):
                        item=next(p for p in state['positions'] if p['id']==pos['id'])
                        basis=max(item['cost_u'],int(item['value_eur']*1e6))
                        fraction=min(Decimal(1),Decimal(str(excess+cap*.01))/Decimal(basis))
                        qty=str(min(Decimal(pos['qty']),(Decimal(pos['qty'])*fraction).quantize(Decimal('.000001'),rounding=ROUND_UP)))
                        reason='CEO-Kapitalgrenze pro Agent: Teilabbau auf unter 25 Prozent'
                    order=self.ledger.submit(pos['agent_id'],pos['symbol'],'sell',qty,
                        f"protect-{pos['id']}-{uid()}",reason=reason)
                    self.ledger.fill(order['id'])
                except RiskError:
                    if not self.db.get('warn-'+pos['id']+'-'+clock['date']):
                        self.db.event('liquidation_exception','Position kann derzeit nicht sicher geschlossen werden; keine Ausführung erfunden',pos['agent_id'],level='critical',data={'position_id':pos['id']})
                        self.db.set('warn-'+pos['id']+'-'+clock['date'],True)

    async def safety_loop(self):
        next_monitor=0
        while not self.stop.is_set():
            try:
                await asyncio.to_thread(self.safety_tick)
                self.db.set('worker_heartbeat',now())
                if asyncio.get_running_loop().time()>=next_monitor:
                    await asyncio.to_thread(self.monitor_signals)
                    next_monitor=asyncio.get_running_loop().time()+10
            except Exception as exc:
                self.db.set('kill_switch',True)
                self.db.event('safety_error',safe_error(exc),level='critical')
            await asyncio.sleep(2)

    async def execute(self,job):
        kind=job['kind']
        payload=json.loads(job['payload'])
        if kind in ('analysis','backtest'):require_research()
        if kind=='fx':
            return await self.providers.fx()
        if kind=='diagnose':
            await asyncio.to_thread(self.providers.diagnose)
            return {'checked':True}
        if kind in ('calendar','assets','news','intraday'):
            await asyncio.to_thread(getattr(self.providers,kind))
            return {'loaded':True}
        if kind=='historical':
            return await asyncio.to_thread(self.providers.historical,payload['symbol'],payload.get('days',365))
        if kind=='prepare_stock':
            await asyncio.to_thread(self.providers.intraday,[payload['symbol']])
            await asyncio.to_thread(self.providers.latest_quotes,[payload['symbol']])
            return {'symbol':payload['symbol'],'prepared':True}
        if kind=='edgar':
            return await self.providers.edgar(payload['cik'],payload['symbol'])
        if kind=='chat':
            return await manager_chat(self.db,self.cfg,payload['text'],payload.get('message_id'))
        if kind=='agent_report':
            from .reporting import write_report
            return await write_report(self.db,self.cfg,job['agent_id'],payload.get('date'))
        if kind=='manager_review':
            from .reporting import review_agents
            return await review_agents(self.db,self.cfg,payload['agent_ids'])
        if kind=='openai_test':
            response=await self.ai.call('connection_test',[{'role':'user','content':'Antworte nur mit OK als Verbindungstest.'}])
            return {'response_id':response.id,'text':response.output_text}
        if kind=='news_thesis':
            from .news_agents import assess_news
            return await assess_news(self.db,self.cfg,job['agent_id'],payload['symbol'])
        if kind=='backtest':
            strategy=self.db.one('SELECT spec FROM strategies WHERE id=? AND agent_id=?',(payload['strategy_id'],job['agent_id']))
            if strategy and json.loads(strategy['spec'])['kind']=='event_driven':
                await asyncio.to_thread(self.providers.company_news,payload['symbol'])
                require_research()
            try:
                return await asyncio.to_thread(run_backtest,self.db,job['agent_id'],payload['strategy_id'],payload['symbol'])
            except ValueError as exc:
                if not str(exc).startswith(('Zu wenig Daten für getrennte','Historische Daten fehlen')):raise
                require_research()
                from .research import progress
                progress(self.db,job['agent_id'],'backtest','Lädt ausreichende Historie für getrennte In-/Out-of-Sample-Tests')
                strategy=self.db.one('SELECT spec FROM strategies WHERE id=? AND agent_id=?',(payload['strategy_id'],job['agent_id']))
                if not strategy:raise ValueError('Strategie fehlt')
                loaded=await asyncio.to_thread(self.providers.strategy_history,payload['symbol'],json.loads(strategy['spec']))
                require_research()
                try:return await asyncio.to_thread(run_backtest,self.db,job['agent_id'],payload['strategy_id'],payload['symbol'])
                except ValueError as missing:
                    if not str(missing).startswith(('Zu wenig Daten für getrennte','Historische Daten fehlen')):raise
                    raise ValueError(f"{payload['symbol']}: Nachladen abgeschlossen, aber Datenabdeckung unzureichend ({loaded.get('bars',0)} Bars, Ziel {loaded.get('target_bars','?')}, {loaded.get('days','?')} Tage). Kein belastbarer Test mit diesem Datensatz.") from missing
        if kind=='analysis':
            if not self.db.get('engine_enabled'):
                raise BudgetError('KI-Engine pausiert')
            from .news_agents import mandate
            if mandate(self.db,job['agent_id'])['approach']=='news' and payload.get('symbol'):
                await asyncio.to_thread(self.providers.company_news,payload['symbol'])
                require_research()
                from .web_research import research_public_web
                from .research_desks import watched_symbols
                symbols=list(dict.fromkeys(watched_symbols(self.db,job['agent_id'])+payload.get('research_symbols',[payload['symbol']])))
                await research_public_web(self.db,self.cfg,job['agent_id'],symbols)
                require_research()
            aid,result=await self.ai.analyze(job['agent_id'])
            agent=self.db.one('SELECT * FROM agents WHERE id=?',(job['agent_id'],))
            final_action='HOLD'
            order_id=None
            final_reason=result.conclusion
            if research_window()['open'] and result.action in ('buy','sell') and agent['department']!='research':
                try:
                    order=self.ledger.submit(job['agent_id'],result.symbol,result.action,result.qty,'analysis-'+aid,
                        stop_usd=result.stop_usd,take_usd=result.take_usd,reason=result.conclusion)
                    final_action='ORDER_PENDING'
                    order_id=order['id']
                except RiskError as exc:
                    final_reason=str(exc)
                    self.db.event('risk_rejected',str(exc),job['agent_id'],level='warning',data={'analysis_id':aid})
            self.db.event('trading_decision',final_reason,job['agent_id'],data={'analysis_id':aid,'proposed_action':result.action,'final_action':final_action,'order_id':order_id})
            # Test every new candidate; jobs fail visibly when data coverage is insufficient.
            strategy=self.db.one('SELECT * FROM strategies WHERE agent_id=? ORDER BY version DESC LIMIT 1',(job['agent_id'],))
            if strategy['status']=='candidate' and self.cfg.symbols and mandate(self.db,job['agent_id'])['approach']!='news':
                from .universe import eligible
                symbol=result.symbol if eligible(self.db,result.symbol) else self.cfg.symbols[job['agent_id']%len(self.cfg.symbols)]
                enqueue(self.db,'backtest',{'strategy_id':strategy['id'],'symbol':symbol},job['agent_id'],45,dedupe='test-'+strategy['id']+'-'+symbol)
            return {'analysis_id':aid,'proposed_action':result.action,'final_action':final_action,'reason':final_reason,'order_id':order_id}
        if kind=='daily_review':
            scores=[evaluate(self.db,a['id']) for a in self.db.all('SELECT id FROM agents')]
            eligible=[x for x in scores if x['score'] is not None]
            # Preserve incumbents unless material evidence supports a swap. No forced daily churn.
            self.db.event('manager_review',f'Tagesbewertung: {len(eligible)} Agenten mit ausreichender Mindeststichprobe; kein Wechsel ohne Begründung.')
            return await manager_chat(self.db,self.cfg,'Erstelle den täglichen CEO-Bericht anhand aktueller Daten, Risiken und Bewertungen. Prüfe begründete Personalvorschläge; bei unzureichender Evidenz Besetzung beibehalten. Nenne die drei wichtigsten Schwachstellen.')
        if kind=='broker_submit':
            return await asyncio.to_thread(BrokerValidation(self.db,self.cfg).submit,**payload)
        if kind=='broker_reconcile':
            await asyncio.to_thread(BrokerValidation(self.db,self.cfg).reconcile)
            return {'reconciled':True}
        if kind=='broker_cancel':
            return await asyncio.to_thread(BrokerValidation(self.db,self.cfg).cancel,payload['oid'])
        if kind=='broker_flatten':
            return await asyncio.to_thread(BrokerValidation(self.db,self.cfg).flatten)
        if kind=='backup':
            return {'path':self.db.backup(ROOT/'backups')}
        raise ValueError('Unbekannter Jobtyp')


async def main():
    cfg=Settings()
    db=DB(cfg.database_path)
    db.init()
    seed(db)
    worker=Worker(db,cfg)
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try:
            signal.signal(sig,lambda *_:loop.call_soon_threadsafe(worker.stop.set))
        except ValueError:
            pass
    try:
        await worker.run()
    finally:
        worker.stop.set()


if __name__=='__main__':
    asyncio.run(main())
