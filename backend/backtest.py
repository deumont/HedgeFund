"""Bounded declarative strategies only; no eval/exec or model-generated Python execution."""
import hashlib
import json
import math
import statistics
from .db import dumps, uid
from .config import now


def validate_spec(spec):
    timeframe=spec.get('timeframe_minutes',15)
    if type(timeframe) is not int or timeframe<15 or timeframe%15 or timeframe>1440:
        raise ValueError('Strategie-Zeitrahmen mindestens 15 Minuten, in 15-Minuten-Schritten')
    if spec.get('kind') not in ('momentum','mean_reversion','ma_cross','breakout'):
        raise ValueError('Strategietyp nicht in sicherer DSL')
    for k,lo,hi in [('lookback',2,252),('holding_bars',1,126),('threshold',0,0.5),('stop_pct',0.001,0.25)]:
        val=spec.get(k)
        if not isinstance(val,(int,float)) or not math.isfinite(val) or not lo<=val<=hi:
            raise ValueError('Ungültiger Parameter '+k)
    if type(spec['lookback']) is not int or type(spec['holding_bars']) is not int:
        raise ValueError('Lookback/Haltedauer müssen ganzzahlig sein')
    return spec


def signal(closes,spec):
    n=spec['lookback']
    if len(closes)<=n:
        return False
    last=closes[-1]
    ret=last/closes[-1-n]-1
    if spec['kind']=='momentum':
        return ret>spec['threshold']
    if spec['kind']=='mean_reversion':
        return ret < -spec['threshold']
    if spec['kind']=='breakout':
        return last>max(closes[-1-n:-1])*(1+spec['threshold'])
    return last>statistics.mean(closes[-n:])*(1+spec['threshold'])


def simulate(bars,spec,initial=3000,cost_bps=12):
    validate_spec(spec)
    if len(bars)<spec['lookback']+10:
        raise ValueError('Zu wenig echte historische Bars')
    if cost_bps<0 or initial<=0:
        raise ValueError('Ungültige Kosten/Kapital')
    cash=float(initial)
    qty=0.0
    entry=0.0
    held=0
    pending=None
    trades=[]
    curve=[]
    closes=[]
    friction=cost_bps/10000
    high=float(initial)
    drawdown=0.0
    dates=[]
    for bar in bars:
        if dates and bar['time']<=dates[-1]:
            raise ValueError('Bars nicht streng chronologisch/eindeutig')
        dates.append(bar['time'])
        op,lo,close=float(bar['open']),float(bar['low']),float(bar['close'])
        if min(op,lo,close)<=0 or not all(math.isfinite(x) for x in (op,lo,close)):
            raise ValueError('Ungültige Marktdaten')
        # Signals only see previous closes; execution at following open plus friction.
        if pending=='buy' and qty==0:
            entry=op*(1+friction)
            qty=cash/entry
            cash=0
            held=0
        elif pending=='sell' and qty:
            price=op*(1-friction)
            cash=qty*price
            trades.append(dict(time=bar['time'],return_pct=(price/entry-1)*100,pnl=cash-qty*entry))
            qty=0
        pending=None
        if qty:
            held+=1
            stop=entry*(1-spec['stop_pct'])
            if lo<=stop:
                price=min(op,stop)*(1-friction)
                cash=qty*price
                trades.append(dict(time=bar['time'],return_pct=(price/entry-1)*100,pnl=cash-qty*entry))
                qty=0
        equity=cash+qty*close
        high=max(high,equity)
        drawdown=max(drawdown,1-equity/high)
        curve.append(dict(time=bar['time'],equity=equity))
        closes.append(close)
        if qty and (held>=spec['holding_bars'] or not signal(closes,spec)):
            pending='sell'
        elif not qty and signal(closes,spec):
            pending='buy'
    returns=[curve[i]['equity']/curve[i-1]['equity']-1 for i in range(1,len(curve))]
    stdev=statistics.stdev(returns) if len(returns)>1 else 0
    sharpe=statistics.mean(returns)/stdev*math.sqrt(252) if stdev else None
    gains=sum(t['pnl'] for t in trades if t['pnl']>0)
    losses=-sum(t['pnl'] for t in trades if t['pnl']<0)
    return dict(initial=initial,final_equity=curve[-1]['equity'],return_pct=(curve[-1]['equity']/initial-1)*100,
                max_drawdown_pct=drawdown*100,sharpe=sharpe,
                profit_factor=gains/losses if losses else None,win_rate_pct=sum(t['pnl']>0 for t in trades)/len(trades)*100 if trades else None,
                trades=trades,equity=curve,cost_bps=cost_bps,open_position=bool(qty),
                benchmark_return_pct=(float(bars[-1]['close'])/float(bars[0]['close'])-1)*100,
                caveats=['USD-Researchrenditen; nicht Fonds-EUR-P&L','Tagesbar-Ausführung; keine Intraday-Validierung',
                         'Einzelwert-/Watchlist-Auswahl enthält Survivorship-Risiko; keine biasfreie Gesamtmarktstudie',
                         'Corporate-Action-bereinigte Daten sind keine vollständigen Point-in-time-Fundamentaldaten'])


def run_backtest(db,agent_id,strategy_id,symbol):
    strategy=db.one('SELECT * FROM strategies WHERE id=? AND agent_id=?',(strategy_id,agent_id))
    if not strategy:
        raise ValueError('Strategie fehlt')
    spec=json.loads(strategy['spec'])
    validate_spec(spec)
    timeframe='1Day' if spec.get('timeframe_minutes',15)==1440 else str(spec.get('timeframe_minutes',15))+'Min'
    # Never silently use shorter candles or combine vendors/adjustment modes.
    dataset=db.one("SELECT source,adjustment FROM bars WHERE symbol=? AND timeframe=? GROUP BY source,adjustment ORDER BY COUNT(*) DESC LIMIT 1",(symbol,timeframe))
    if not dataset:
        raise ValueError('Historische Daten fehlen; zuerst importieren/laden')
    bars=db.all("SELECT * FROM bars WHERE symbol=? AND timeframe=? AND source=? AND adjustment=? ORDER BY time",(symbol,timeframe,dataset['source'],dataset['adjustment']))
    split=int(len(bars)*0.7)
    if split<=spec['lookback']+10 or len(bars)-split<=spec['lookback']+10:
        raise ValueError('Zu wenig Daten für getrennte In-Sample-/Out-of-Sample-Tests')
    result={'full':simulate(bars,spec),'in_sample':simulate(bars[:split],spec),
            'out_of_sample':simulate(bars[split:],spec),'split_date':bars[split]['time'],
            'walk_forward':[], 'dataset':dataset}
    window=max(spec['lookback']+11,len(bars)//4)
    for start in range(split,len(bars)-window+1,window):
        result['walk_forward'].append(simulate(bars[start:start+window],spec))
    digest=hashlib.sha256(dumps(bars).encode()).hexdigest()
    bid=uid()
    with db.tx() as c:
        c.execute('INSERT INTO backtests VALUES(?,?,?,?,?,?,?,?)',
                  (bid,agent_id,strategy_id,symbol,digest,dumps(spec),dumps(result),now()))
        c.execute("UPDATE strategies SET status='tested' WHERE id=?",(strategy_id,))
    db.event('backtest',f'{symbol}: reproduzierbarer Research-Backtest gespeichert',agent_id,data={'backtest_id':bid,'data_hash':digest})
    return {'id':bid,'result':result,'data_hash':digest}
