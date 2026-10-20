"""Deterministic, fail-closed trade gate. Neither an LLM nor a timer can authorize a trade."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import json
from .db import uid,dumps,event
from .config import now
from .calendar import phase,NEW_YORK
from .backtest import validate_spec,signal

MIN_TIMEFRAME=15


@dataclass
class Decision:
    id: str
    valid: bool
    reason: str
    strategy_id: str | None
    timeframe_minutes: int
    observations: dict


def state(c,key,default=None):
    row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default


def evaluate_tx(db,c,agent_id,symbol,side='buy',at=None,expected_strategy=None):
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError('Zeitzone erforderlich')
    strategy=c.execute('SELECT * FROM strategies WHERE agent_id=? ORDER BY version DESC LIMIT 1',(agent_id,)).fetchone()
    agent=c.execute('SELECT * FROM agents WHERE id=?',(agent_id,)).fetchone()
    spec=json.loads(strategy['spec']) if strategy else {}
    tf=spec.get('timeframe_minutes',0)
    observations={'as_of':at.isoformat(),'default':'HOLD / NO TRADE','strategy_spec':spec}
    reason='Keine gültige Einstiegsbedingung'
    valid=False
    sid=strategy['id'] if strategy else None
    pid='fund' if agent and agent['department']=='fund' else f'demo-{agent_id:03}'
    position=c.execute('SELECT * FROM positions WHERE portfolio_id=? AND agent_id=? AND symbol=?',(pid,agent_id,symbol)).fetchone()
    clock=phase(db,at)
    policy=state(c,'market_data_policy',{'delay_minutes':15,'feed':'iex','min_timeframe_minutes':15})
    delay=max(15,int(policy.get('delay_minutes',15)))
    observations.update(policy=policy,position_id=position['id'] if position else None,session=clock['phase'])
    try:
        if not agent or agent['department']=='research':
            raise ValueError('Research-Agent: keine aktuellen Handelsorders')
        if not strategy or expected_strategy and sid!=expected_strategy:
            raise ValueError('Strategie fehlt oder wurde seit Signalerzeugung geändert')
        validate_spec(spec)
        if type(tf) is not int or tf<MIN_TIMEFRAME:
            raise ValueError('Zeitrahmen unter 15 Minuten ist gesperrt')
        if side not in ('buy','sell'):
            raise ValueError('Ungültige Handelsrichtung')
        if side=='buy' and (agent['paused'] or not clock['trading']):
            raise ValueError('Agent pausiert oder außerhalb seiner Handelssitzung')
        if side=='sell' and not (clock['trading'] or clock['liquidating']):
            raise ValueError('Keine erlaubte Ausführungssitzung')
        if side=='buy' and position:
            raise ValueError('Bestehende Position: kein erzwungenes Nachkaufen/Pyramiding')
        if side=='sell' and not position:
            raise ValueError('Keine Position zum Schließen')
        if side=='sell':
            quote=c.execute('SELECT * FROM quotes WHERE symbol=?',(symbol,)).fetchone()
            bid=Decimal(quote['bid']) if quote else None
            protective=state(c,'kill_switch') or state(c,'risk_halt_'+pid) or clock['liquidating']
            from .ledger import over_agent_cap
            protective=protective or over_agent_cap(c,pid,agent_id,at)
            protective=protective or bid is not None and (bid<=Decimal(position['stop_usd']) or position['take_usd'] and bid>=Decimal(position['take_usd']))
            if protective:
                # Explicit pre-defined safety exit, not a discretionary entry override.
                observations['exit_condition']='stop/take_profit/kill/risk_limit/agent_cap/session_liquidation'
                valid=True
                reason='Vordefinierte Schutz-/Tagesendebedingung erfüllt; frische Ausführungsdaten separat erforderlich'
                return record(c,agent_id,symbol,side,sid,tf,valid,reason,observations,at)
        mandate=c.execute('SELECT approach FROM agent_mandates WHERE agent_id=?',(agent_id,)).fetchone()
        if mandate and mandate['approach']=='news' and spec.get('kind')!='event_driven':
            raise ValueError('Nachrichtenagent wartet auf seine Ereignisstrategie; kein technischer Ersatzhandel')
        if spec.get('kind')=='event_driven':
            from .news_agents import event_signal
            valid,reason,proof=event_signal(c,agent_id,symbol,side,position,spec,at)
            observations.update(proof)
            return record(c,agent_id,symbol,side,sid,tf,valid,reason,observations,at)
        if spec.get('requires_realtime',False):
            raise ValueError('Strategie benötigt Echtzeitdaten; 15-Minuten-Verzögerung ungeeignet')
        if (spec.get('requires_full_market',False) or agent['specialty']=='Mikrostruktur') and policy.get('feed','iex')!='sip':
            raise ValueError('Strategie benötigt Gesamtmarktfeed; IEX-Teilmarkt ungeeignet')
        if spec.get('max_data_delay_minutes',0)<delay:
            raise ValueError('Datenverzögerung überschreitet das Strategielimit')
        timeframe='1Day' if tf==1440 else f'{tf}Min'
        dataset=c.execute("SELECT source,adjustment FROM bars WHERE symbol=? AND timeframe=? AND source LIKE 'Alpaca %' GROUP BY source,adjustment ORDER BY MAX(time) DESC LIMIT 1",(symbol,timeframe)).fetchone()
        if not dataset:
            raise ValueError(f'Keine geeigneten echten {tf}-Minuten-Bars; Importdaten sind nur Research')
        source=dataset['source']
        if 'IEX' in source.upper() and (spec.get('requires_full_market') or agent['specialty']=='Mikrostruktur'):
            raise ValueError('Datensatz selbst ist IEX; Gesamtmarktstrategie gesperrt')
        rows=[dict(x) for x in c.execute('SELECT * FROM bars WHERE symbol=? AND timeframe=? AND source=? AND adjustment=? ORDER BY time DESC LIMIT ?',
                                       (symbol,timeframe,source,dataset['adjustment'],max(spec['lookback']+5, spec['holding_bars']+5)*4)).fetchall()]
        closed=[]
        duration=timedelta(minutes=tf)
        for row in reversed(rows):
            start=datetime.fromisoformat(row['time'])
            if start.tzinfo is None or start>at:
                raise ValueError('Zukünftiger/zeitzonenloser Bar; Datenqualität ungeeignet')
            if tf<1440:
                session=c.execute('SELECT opens_at,closes_at FROM sessions WHERE date=?',(start.astimezone(NEW_YORK).date().isoformat(),)).fetchone()
                # These traders operate during regular sessions. Sparse extended-hours
                # bars must not be interpreted as holes in the regular-session series.
                if not session or start<datetime.fromisoformat(session['opens_at']) or start+duration>datetime.fromisoformat(session['closes_at']):
                    continue
            if start+duration+timedelta(minutes=delay)>at:
                continue  # never read forming or not-yet-available delayed candles
            vals=[Decimal(row[k]) for k in ('open','high','low','close')]
            if not all(v.is_finite() and v>0 for v in vals) or vals[2]>min(vals[0],vals[3]) or vals[1]<max(vals[0],vals[3]) or row['volume']<=0:
                raise ValueError('OHLCV-Daten ungültig oder ohne Volumen')
            if closed and start-datetime.fromisoformat(closed[-1]['time'])<duration:
                raise ValueError('Überlappende Bars/Dateninkonsistenz')
            closed.append(row)
        if len(closed)<=spec['lookback']:
            raise ValueError('Zu wenig abgeschlossene, tatsächlich verfügbare Bars')
        for previous,current in zip(closed,closed[1:]):
            before=datetime.fromisoformat(previous['time'])
            after=datetime.fromisoformat(current['time'])
            if tf<1440 and before.date()==after.date() and after-before>duration:
                raise ValueError('Fehlende Bars innerhalb einer Handelssitzung; Datenlücke')
        last_end=datetime.fromisoformat(closed[-1]['time'])+duration
        # Explicit 15min delay is permitted for strategy research, not unlimited staleness.
        if at-last_end>timedelta(minutes=delay+tf):
            raise ValueError('Verzögerte Strategie-Bars zusätzlich veraltet')
        if side=='buy' and datetime.fromisoformat(strategy['created_at'])>last_end:
            raise ValueError('Neue Strategie erst mit nachfolgendem abgeschlossenen Bar handeln; keine rückwirkend erzwungenen Signale')
        closed=closed[-max(spec['lookback']+5,spec['holding_bars']+5):]
        closes=[float(x['close']) for x in closed]
        entry=signal(closes,spec)
        observations.update(bars=closed,last_bar_end=last_end.isoformat(),
            available_after=(last_end+timedelta(minutes=delay)).isoformat(),
            bar_hash=hashlib.sha256(dumps(closed).encode()).hexdigest(),
            indicators={'lookback_return':closes[-1]/closes[-1-spec['lookback']]-1,
                        'moving_average':sum(closes[-spec['lookback']:])/spec['lookback'],
                        'threshold':spec['threshold'],'entry_condition':entry})
        if side=='buy':
            valid=entry
            reason='Vordefinierte technische Einstiegsbedingung erfüllt' if valid else 'HOLD: Vordefinierte Einstiegsbedingung nicht erfüllt; kein Aktivitätsziel'
            prior=c.execute("SELECT s.observations FROM fills f JOIN order_signals os ON os.order_id=f.order_id JOIN signal_decisions s ON s.id=os.signal_id WHERE f.agent_id=? AND f.symbol=? AND f.side='buy' ORDER BY f.created_at DESC LIMIT 1",(agent_id,symbol)).fetchone()
            if valid and prior and json.loads(prior['observations']).get('last_bar_end')==observations['last_bar_end']:
                valid=False
                reason='HOLD: Einstiegsbedingung dieses abgeschlossenen Bars bereits gehandelt'
        else:
            bars_held=sum(datetime.fromisoformat(x['time'])>=datetime.fromisoformat(position['created_at']) for x in closed)
            valid=not entry or bars_held>=spec['holding_bars']
            observations['completed_bars_held']=bars_held
            reason='Vordefinierte Strategie-Ausstiegsbedingung erfüllt' if valid else 'HOLD: weder Strategieausstieg noch Schutzbedingung erfüllt'
    except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
        reason='HOLD / NO TRADE: '+str(exc)
        valid=False
    return record(c,agent_id,symbol,side,sid,tf if type(tf) is int else 0,valid,reason,observations,at)


def record(c,agent_id,symbol,side,strategy_id,tf,valid,reason,observations,at):
    # Persist every distinct decision state; identical monitoring polls do not invent new actions.
    material={'agent':agent_id,'symbol':symbol,'side':side,'strategy':strategy_id,'valid':valid,
              'reason':reason,'bar_hash':observations.get('bar_hash'),'position':observations.get('position_id'),
              'bucket':int(at.timestamp())//900}
    dedupe=hashlib.sha256(dumps(material).encode()).hexdigest()
    existing=c.execute('SELECT id FROM signal_decisions WHERE dedupe=?',(dedupe,)).fetchone()
    did=existing['id'] if existing else uid()
    if not existing:
        c.execute('INSERT INTO signal_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  (did,dedupe,agent_id,strategy_id,symbol,side,side.upper() if valid else 'HOLD',reason,tf,dumps(observations),at.isoformat()))
        event(c,'valid_signal' if valid else 'hold_decision',reason,agent_id,data={'decision_id':did,'symbol':symbol,'timeframe_minutes':tf})
    return Decision(did,valid,reason,strategy_id,tf,observations)


class SignalEngine:
    def __init__(self,db):
        self.db=db

    def evaluate(self,agent_id,symbol,side='buy',at=None):
        with self.db.tx() as c:
            return evaluate_tx(self.db,c,agent_id,symbol,side,at)
