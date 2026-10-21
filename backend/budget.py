"""Conservative audit repair: release only uniquely attributable HTTP 429 rejections."""
import json
from datetime import datetime,timedelta
from .db import event,dumps


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
