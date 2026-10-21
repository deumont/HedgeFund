"""Daily paper-entry objective, with evidence-based exceptions; never order authority."""
from datetime import datetime,time,timezone
from contextlib import closing
import json
from .calendar import BERLIN,phase

POLICY={'enabled':True,'effective_from':'2026-10-21','minimum_new_positions':1,
        'scope':'demo_and_fund','exception':'No suitable opportunity after documented search; manager reviews the exception.'}
MANAGER_POLICY=('Aktive Demo-/Fonds-Trader sollen jeden Handelstag mindestens eine neue Position eröffnen. '
    'Nur ausgeführte neue Käufe zählen, keine offenen Orders, Aufstockungen oder Altpositionen. '
    'Bei Nichterfüllung die belegte Kandidatensuche und Ausführungshindernisse prüfen und eine Ausnahme ausdrücklich begründen. '
    'Wiederholt fehlende Initiative oder unbegründete Nichterfüllung bei der Bewertung und Abstiegsauswahl negativ berücksichtigen. '
    'Begründete fehlende Gelegenheiten sind zulässig; Daten-/Kapitalgrenzen nicht übergehen und keinen Kauf erfinden. '
    'Research-Agenten haben kein Handelsziel und können nicht handeln. Frühere Leistung und kleine Stichproben berücksichtigen.')


def progress(db,aid,day=None,at=None):
    at=at or datetime.now(timezone.utc)
    day=day or at.astimezone(BERLIN).date().isoformat()
    start=datetime.combine(datetime.fromisoformat(day).date(),time(),BERLIN)
    from datetime import timedelta
    end=start+timedelta(days=1)
    with closing(db.connect()) as c:
        agent=c.execute('SELECT department FROM agents WHERE id=?',(aid,)).fetchone()
        row=c.execute("SELECT value FROM meta WHERE key='daily_entry_policy'").fetchone()
        policy=json.loads(row[0]) if row else POLICY
        openings=c.execute("""SELECT COUNT(*) FROM fills f
          LEFT JOIN order_signals os ON os.order_id=f.order_id
          LEFT JOIN signal_decisions s ON s.id=os.signal_id
          WHERE f.agent_id=? AND f.side='buy' AND f.created_at>=? AND f.created_at<?
          AND json_extract(COALESCE(s.observations,'{}'),'$.position_id') IS NULL""",
          (aid,start.astimezone(timezone.utc).isoformat(),end.astimezone(timezone.utc).isoformat())).fetchone()[0]
        row=c.execute('SELECT value FROM meta WHERE key=?',('daily-entry-search-'+day+'-'+str(aid),)).fetchone()
        search=json.loads(row[0]) if row else {}
        session=c.execute('SELECT date FROM sessions WHERE date=?',(day,)).fetchone()
    today=at.astimezone(BERLIN).date().isoformat()
    if agent and day<today:
        from .history import department_at
        agent={'department':department_at(db,aid,end.astimezone(timezone.utc).isoformat())}
    eligible=bool(agent and agent['department']!='research' and policy.get('enabled') and day>=policy['effective_from'])
    if search.get('date')!=day:search={}
    clock=phase(db,at)
    due=day<today or day==today and clock['phase'] in ('liquidating','review','stopped')
    eligible=eligible and bool(session)
    status='not_applicable' if not eligible else 'met' if openings>=1 else 'review_required' if due else 'searching'
    return {'date':day,'applies':eligible,'minimum':1 if eligible else 0,'new_positions':openings,
            'status':status,'due':bool(due and eligible),'search':search,
            'exception_requires_manager_review':bool(eligible and due and openings<1),
            'documented_search':bool(search.get('symbols_checked')),'policy':MANAGER_POLICY}


def manager_evidence(db,aid,day=None):
    value=progress(db,aid,day)
    from .reporting import window
    _,start,end=window(value['date'])
    value['signal_obstacles']=db.all("SELECT reason,COUNT(*) checks FROM signal_decisions WHERE agent_id=? AND requested_side='buy' AND decision='HOLD' AND created_at>=? AND created_at<? GROUP BY reason ORDER BY checks DESC LIMIT 4",(aid,start,end))
    value['execution_obstacles']=db.all("SELECT message,created_at FROM events WHERE agent_id=? AND kind='trading_decision' AND json_extract(data,'$.final_action')='HOLD' AND created_at>=? AND created_at<? ORDER BY id DESC LIMIT 2",(aid,start,end))
    return value


def record_search(db,aid,at,symbols,valid):
    day=at.astimezone(BERLIN).date().isoformat()
    key='daily-entry-search-'+day+'-'+str(aid)
    old=db.get(key,{})
    if old.get('date')!=day:old={}
    merged=list(dict.fromkeys(old.get('symbols',[])+list(symbols)))
    db.set(key,{'date':day,'checked_at':at.isoformat(),
        'symbols':merged[:100],'symbols_checked':max(len(merged),old.get('symbols_checked',0)),
        'signal_checks':old.get('signal_checks',0)+len(symbols),'valid_signal_checks':old.get('valid_signal_checks',0)+valid})


def candidates(db,cfg,aid,at,preferred=None):
    """Search more stocks using the agent's own strategy; never relax its conditions."""
    from .news_agents import mandate
    from .universe import active_symbols,eligible
    if mandate(db,aid)['approach']=='news':
        # Each source-backed thesis may authorize a different watched company.
        rows=db.all('SELECT symbol FROM event_theses WHERE agent_id=? AND expires_at>? ORDER BY created_at DESC LIMIT 20',(aid,at.isoformat()))
        pool=[r['symbol'] for r in rows]
    else:
        pool=active_symbols(db,cfg)
        if pool:
            offset=(aid+int(at.timestamp())//900)%len(pool)
            pool=pool[offset:]+pool[:offset]
    symbols=list(dict.fromkeys(([preferred] if preferred else [])+pool))
    return [s for s in symbols if eligible(db,s)][:12]
