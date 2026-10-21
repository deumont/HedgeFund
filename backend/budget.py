"""Conservative audit repair: release only uniquely attributable HTTP 429 rejections."""
import json
from datetime import datetime,timedelta
from .db import event,dumps


def resume_spend_blocked_jobs(db,cfg):
    """Resume work rejected locally before inference; never replay uncertain calls."""
    if cfg.api_spend_limit_enabled:return 0
    from .config import now
    resumed=0
    with db.tx() as c:
        context_migration=not db.get('context_capacity_v2',False)
        rows=c.execute("SELECT * FROM jobs WHERE status='blocked' AND kind IN ('analysis','news_thesis','agent_report','manager_review','manager_daily') AND (error IN (?,?) OR (? AND error=?)) ORDER BY created_at DESC,id DESC",
            ('Lokales Monatsbudget ausgeschöpft; neue KI-Aufgaben gesperrt','Lokales Tages-/Monatsbudget ausgeschöpft; neue KI-Aufgaben gesperrt',context_migration,'KI-Kontext überschreitet lokale Grenze')).fetchall()
        seen=set()
        for row in rows:
            key=(row['kind'],row['agent_id'])
            active=c.execute("SELECT id FROM jobs WHERE kind=? AND agent_id IS ? AND status IN ('pending','running') LIMIT 1",key).fetchone()
            if key in seen or active:
                c.execute("UPDATE jobs SET status='superseded',error='Durch neueren Auftrag ersetzt; lokale Ausgabensperre aufgehoben',updated_at=? WHERE id=?",(now(),row['id']))
            else:
                c.execute("UPDATE jobs SET status='pending',attempts=0,error=NULL,available_at=?,updated_at=? WHERE id=?",(now(),now(),row['id']))
                resumed+=1
            seen.add(key)
        if rows:event(c,'spend_limit_removed','Lokale API-Ausgabensperre aufgehoben; aktuelle Aufgaben fortgesetzt',data={'resumed':resumed,'superseded':len(rows)-resumed})
        from .db import put
        put(c,'context_capacity_v2',True)
    return resumed


def reconcile_rate_rejections(db):
    repaired=[]
    with db.tx() as c:
        errors=c.execute("SELECT * FROM events WHERE kind='job_failed' AND message LIKE 'RateLimitError HTTP 429%' ORDER BY id").fetchall()
        for e in errors:
            data=json.loads(e['data'])
            if data.get('kind')!='analysis' or e['agent_id'] is None:continue
            job=c.execute('SELECT * FROM jobs WHERE id=?',(data.get('job_id'),)).fetchone()
            if not job or job['agent_id']!=e['agent_id'] or job['kind']!='analysis' or not (job['error'] or '').startswith('RateLimitError HTTP 429'):continue
            end=datetime.fromisoformat(e['created_at']);start=end-timedelta(seconds=3)
            if abs((datetime.fromisoformat(job['updated_at'])-end).total_seconds())>1:continue
            rows=c.execute("SELECT * FROM usage WHERE agent_id=? AND kind='agent' AND created_at>=? AND created_at<=?",(e['agent_id'],start.isoformat(),end.isoformat())).fetchall()
            if len(rows)!=1:continue
            u=rows[0]
            if u['status']!='uncertain' or u['cost_u'] or u['input_tokens'] or u['output_tokens']:continue
            c.execute("UPDATE usage SET status='rejected',reserved_u=0 WHERE id=? AND status='uncertain'",(u['id'],))
            event(c,'usage_reconciled','Eindeutig zugeordnete HTTP-429-Ablehnung: lokale Reservierung freigegeben, keine abgerechneten Tokens verändert.',e['agent_id'],data={'usage_id':u['id'],'failure_event_id':e['id'],'job_id':job['id'],'released_reservation_u':u['reserved_u']})
            repaired.append({'usage_id':u['id'],'released_u':u['reserved_u']})
    return repaired
