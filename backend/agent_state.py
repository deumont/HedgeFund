"""Current role-specific agent status and real performance, independent of AI prose."""
import json
from datetime import datetime,timezone
from .ledger import snapshot
from .calendar import phase


def agent_states(db,ids=None):
    result={}; clock=phase(db)
    heartbeat=db.get('worker_heartbeat')
    online=bool(heartbeat and (datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat)).total_seconds()<45 and db.get('worker_identity',{}).get('pid',0)>0)
    with db.tx() as c:
        portfolios={}
        agents=c.execute('SELECT * FROM agents ORDER BY id').fetchall()
        for a in agents:
            aid=a['id']
            if ids and aid not in ids:continue
            pid='fund' if a['department']=='fund' else f"{a['department']}-{aid:03}"
            if pid not in portfolios:
                portfolios[pid]=snapshot(c,pid) if c.execute('SELECT 1 FROM portfolios WHERE id=?',(pid,)).fetchone() else {'positions':[]}
            own=[p for p in portfolios[pid]['positions'] if p['agent_id']==aid]
            stats=dict(c.execute("SELECT COUNT(*) trades,COALESCE(SUM(realized_u),0) pnl_u,SUM(side='sell') closed_trades FROM fills WHERE agent_id=? AND portfolio_id=?",(aid,pid)).fetchone())
            stats.update(realized_eur=stats['pnl_u']/1e6,unrealized_eur=sum(p['unrealized_eur'] for p in own) if all(p['unrealized_eur'] is not None for p in own) else None,
                         valuation_complete=all(p['valuation_complete'] for p in own),positions=len(own),closed_trades=stats['closed_trades'] or 0)
            signal=c.execute('SELECT decision,reason,symbol,created_at FROM signal_decisions WHERE agent_id=? ORDER BY rowid DESC LIMIT 1',(aid,)).fetchone()
            pending=c.execute("SELECT COUNT(*) FROM orders WHERE agent_id=? AND status IN ('pending','triggered')",(aid,)).fetchone()[0]
            running=c.execute("SELECT kind FROM jobs WHERE agent_id=? AND status='running' LIMIT 1",(aid,)).fetchone()
            reason=signal['reason'] if signal else 'Noch kein zulässiger Einstieg erkannt'
            if a['paused']:status='paused'; label='Pausiert'; reason='Neue Einstiege vom CEO pausiert'
            elif own:status='position';label='Position offen';reason=f'{len(own)} Position(en); Schutzkontrolle aktiv' if online else 'Position offen; Engine derzeit offline'
            elif pending:status='pending';label='Order offen';reason=f'{pending} Order(s) in Prüfung'
            elif not online and clock['phase'] in ('stopped','sleeping'):status='session';label='Tagesende' if clock['phase']=='stopped' else 'Ruhezeit';reason=clock['reason']
            elif not online:status='offline';label='Engine offline';reason='Keine aktuelle Worker-Bestätigung'
            elif running:status='working';label='Analyse läuft';reason=running['kind']
            elif a['department']=='research':status='research';label='Research bereit';reason='Forschung; keine direkten Tagesorders'
            elif not clock['trading']:status='session';label='Außerhalb Sitzung';reason=clock['reason']
            elif not db.get('trading_enabled') or db.get('kill_switch'):status='blocked';label='Handel gesperrt';reason='Handelsfreigabe/Not-Aus'
            elif signal and any(term in reason.lower() for term in ('datenlücke','veraltet','feed','echtzeit','zu wenig','keine geeigneten','verzögerung')):status='data';label='Daten gesperrt'
            else:status='waiting';label='Wartet auf Signal';reason='Überwachung aktiv; kein Auftrag erforderlich'
            result[aid]={'stats':stats,'runtime':{'status':status,'label':label,'reason':reason.replace('HOLD / NO TRADE: ','').replace('HOLD: ',''),
                'positions':len(own),'pending_orders':pending,'last_checked_at':heartbeat,'last_signal_at':signal['created_at'] if signal else None}}
    return result
