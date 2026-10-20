"""Bounded report/review workers; never execute trades or extend trading hours."""
import asyncio
import json
from datetime import datetime,time,timezone
from .calendar import BERLIN
from .config import now
from .db import dumps
from .reporting import schedule,queue_report,write_report,review_agents
from .intelligence import BudgetError
from .providers import safe_error


class ManagementService:
    def __init__(self,db,cfg):self.db,self.cfg=db,cfg

    def claim(self):
        with self.db.tx() as c:
            row=c.execute("SELECT * FROM jobs WHERE status='pending' AND kind IN ('agent_report','manager_review') AND available_at<=? ORDER BY priority,created_at LIMIT 1",(now(),)).fetchone()
            if not row:return None
            c.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=?",(now(),row['id']))
            return dict(row)

    async def runner(self,stop):
        while not stop.is_set():
            if not self.db.get('engine_enabled'):
                try:await asyncio.wait_for(stop.wait(),5)
                except asyncio.TimeoutError:pass
                continue
            job=self.claim()
            if not job:
                try:await asyncio.wait_for(stop.wait(),2)
                except asyncio.TimeoutError:pass
                continue
            payload=json.loads(job['payload'])
            status='completed';error=None
            try:
                if job['kind']=='agent_report':result=await write_report(self.db,self.cfg,job['agent_id'],payload.get('date'))
                else:result=await review_agents(self.db,self.cfg,payload['agent_ids'])
                payload['result']=result
            except asyncio.CancelledError:
                with self.db.tx() as c:c.execute("UPDATE jobs SET status='uncertain',error=?,updated_at=? WHERE id=?",('Berichtsprozess unterbrochen; keine automatische Wiederholung',now(),job['id']))
                raise
            except BudgetError as exc:status='blocked';error=str(exc)
            except Exception as exc:status='failed';error=safe_error(exc)
            with self.db.tx() as c:
                c.execute('UPDATE jobs SET status=?,payload=?,error=?,updated_at=? WHERE id=?',(status,dumps(payload),error,now(),job['id']))
            self.db.set('manager_heartbeat',now())

    async def run(self,stop):
        if not self.cfg.openai_api_key:return
        with self.db.tx() as c:
            c.execute("UPDATE jobs SET status='uncertain',error='Vorheriger Berichtsprozess unterbrochen; keine automatische Wiederholung',updated_at=? WHERE status='running' AND kind IN ('agent_report','manager_review')",(now(),))
        runners=[asyncio.create_task(self.runner(stop)) for _ in range(2)]
        try:
            while not stop.is_set():
                at=datetime.now(timezone.utc);local=at.astimezone(BERLIN)
                if self.db.get('engine_enabled'):
                    # The manager may review continuously; trading-session gates are separate.
                    schedule(self.db,self.cfg,at)
                    if local.time()>=time(18,30):
                        for a in self.db.all("SELECT id FROM agents WHERE department='fund'"):
                            queue_report(self.db,self.cfg,a['id'],local.date().isoformat())
                try:await asyncio.wait_for(stop.wait(),15)
                except asyncio.TimeoutError:pass
        finally:
            for task in runners:task.cancel()
            await asyncio.gather(*runners,return_exceptions=True)
