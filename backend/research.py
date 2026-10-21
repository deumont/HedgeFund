"""Research session gates and read-only, persisted progress for every agent."""
import json
from datetime import datetime,time,timedelta,timezone
from .calendar import BERLIN
from .config import now
from .db import dumps


class ResearchClosed(ValueError):
    pass


def research_window(at=None):
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None:raise ValueError('Zeitzone erforderlich')
    local=at.astimezone(BERLIN)
    start=datetime.combine(local.date(),time(7,30),BERLIN)
    end=datetime.combine(local.date(),time(15,30),BERLIN)
    opened=start<=local<end
    next_start=start if local<start else start+timedelta(days=1)
    return {'open':opened,'timezone':'Europe/Berlin','starts_at':start.isoformat(),'ends_at':end.isoformat(),
            'next_start':next_start.isoformat(),'label':'07:30–15:30 Uhr Berlin','as_of':at.isoformat()}


def require_research():
    if not research_window()['open']:
        raise ResearchClosed('Forschung und Strategieänderungen nur 07:30–15:30 Uhr Europe/Berlin; Fortsetzung im nächsten Zeitfenster')


def progress(db,aid,kind,label):
    # Actual stages only, never generated thoughts or an invented completion percentage.
    with db.tx() as c:
        for row in c.execute("SELECT id,payload FROM jobs WHERE agent_id=? AND kind=? AND status='running'",(aid,kind)).fetchall():
            payload=json.loads(row['payload']);payload['stage']=label
            c.execute('UPDATE jobs SET payload=?,updated_at=? WHERE id=?',(dumps(payload),now(),row['id']))


def research_roster(db):
    window=research_window();heartbeat=db.get('worker_heartbeat')
    online=bool(heartbeat and db.get('worker_identity',{}).get('pid',0)>0 and
                (datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat)).total_seconds()<45)
    rows=db.all("""SELECT a.id,a.name,a.department,a.specialty,a.paused,
        (SELECT COUNT(*) FROM analyses x WHERE x.agent_id=a.id) analyses,
        (SELECT COUNT(*) FROM backtests x WHERE x.agent_id=a.id) backtests,
        (SELECT MAX(version) FROM strategies x WHERE x.agent_id=a.id) strategy_version
        FROM agents a ORDER BY a.id""")
    for a in rows:
        from .news_agents import mandate
        a.update(mandate(db,a['id']))
        job=db.one("SELECT id,kind,status,payload,error,updated_at FROM jobs WHERE agent_id=? AND kind IN ('analysis','backtest') ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,updated_at DESC LIMIT 1",(a['id'],))
        a['job']=job
        if job:job['payload']=json.loads(job['payload'])
        if not window['open']:a['state']='Außerhalb Forschungszeit'
        elif a['paused']:a['state']='Pausiert'
        elif not online:a['state']='Engine offline'
        elif not db.get('engine_enabled'):a['state']='KI pausiert'
        elif job and job['status']=='running':a['state']='Backtest läuft' if job['kind']=='backtest' else 'Analyse läuft'
        elif job and job['status']=='pending':a['state']='In Warteschlange'
        elif job and job['status'] in ('failed','blocked','uncertain'):a['state']='Prüfung erforderlich'
        else:a['state']='Bereit'
    return rows


def agent_research(db,aid,offset=0):
    agent=db.one('SELECT id,name,department,specialty FROM agents WHERE id=?',(aid,))
    if not agent:raise ValueError('Agent fehlt')
    from .news_agents import mandate
    agent.update(mandate(db,aid))
    refs=db.all("""SELECT * FROM (
        SELECT id,'analysis' kind,created_at FROM analyses WHERE agent_id=?
        UNION ALL SELECT id,'backtest',created_at FROM backtests WHERE agent_id=?
        UNION ALL SELECT id,'strategy',created_at FROM strategies WHERE agent_id=?)
        ORDER BY created_at DESC,kind,id LIMIT 10 OFFSET ?""",(aid,aid,aid,offset))
    timeline=[]
    for ref in refs:
        table={'analysis':'analyses','backtest':'backtests','strategy':'strategies'}[ref['kind']]
        columns='id,agent_id,strategy_id,result,created_at' if table=='analyses' else '*'
        row=db.one(f'SELECT {columns} FROM {table} WHERE id=?',(ref['id'],))
        row['kind']=ref['kind']
        for key in ('result','parameters','spec'):
            if key in row:row[key]=json.loads(row[key])
        if table=='strategies':
            previous=db.one('SELECT version,spec FROM strategies WHERE agent_id=? AND version<? ORDER BY version DESC LIMIT 1',(aid,row['version']))
            before=json.loads(previous['spec']) if previous else {}
            row['previous_version']=previous['version'] if previous else None
            row['changes']={k:{'before':before.get(k),'after':row['spec'].get(k)} for k in before.keys()|row['spec'].keys() if before.get(k)!=row['spec'].get(k)}
        timeline.append(row)
    jobs=db.all("SELECT id,kind,status,payload,error,attempts,available_at,created_at,updated_at FROM jobs WHERE agent_id=? AND kind IN ('analysis','backtest') ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,updated_at DESC LIMIT 12",(aid,))
    for job in jobs:job['payload']=json.loads(job['payload'])
    counts={table:db.one(f'SELECT COUNT(*) n FROM {table} WHERE agent_id=?',(aid,))['n'] for table in ('analyses','backtests','strategies')}
    current=db.one('SELECT id,version,spec,status,rationale,created_at FROM strategies WHERE agent_id=? ORDER BY version DESC LIMIT 1',(aid,))
    if current:current['spec']=json.loads(current['spec'])
    draft=db.one('SELECT received_at FROM research_drafts WHERE agent_id=?',(aid,))
    theses=db.all('SELECT * FROM event_theses WHERE agent_id=? ORDER BY created_at DESC LIMIT 10',(aid,))
    from .web_research import recent_research
    return {'agent':agent,'public_research':recent_research(db,aid,3),'news_monitor':db.get('agent-news-monitor-'+str(aid)),
            'execution_eligible':agent['department']!='research','window':research_window(),'jobs':jobs,'timeline':timeline,'counts':counts,'current_strategy':current,'deferred_analysis':draft,'company_theses':theses,
            'offset':offset,'limit':10,'total':sum(counts.values()),'as_of':now()}


def team_view(db,offset=0):
    rows=db.all("SELECT * FROM decisions WHERE kind='rotation' ORDER BY created_at DESC,id LIMIT 20 OFFSET ?",(offset,))
    for row in rows:
        p=json.loads(row['payload']);row['payload']=p
        row['agents']=db.all('SELECT id,name,department FROM agents WHERE id IN (?,?)',(p['first'],p['second']))
        row['deferred']=row['status']=='approved' and bool(db.one('SELECT id FROM positions WHERE agent_id IN (?,?) LIMIT 1',(p['first'],p['second'])) or db.one("SELECT id FROM orders WHERE agent_id IN (?,?) AND status IN ('pending','triggered') LIMIT 1",(p['first'],p['second'])))
    return {'actions':rows,'total':db.one("SELECT COUNT(*) n FROM decisions WHERE kind='rotation'")['n'],'offset':offset,'limit':20,
            'daily_decisions':db.all('SELECT date,status,summary,updated_at FROM daily_cycles ORDER BY date DESC LIMIT 30'),'as_of':now()}
