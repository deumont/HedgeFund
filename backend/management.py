"""Bounded report/review workers; never execute trades or extend trading hours."""
import asyncio
import json
from datetime import datetime,timezone
from .config import now
from .db import dumps
from .reporting import schedule,write_report,review_agents
from .daily import schedule_daily,decide_daily
from .intelligence import BudgetError
from .providers import safe_error


class ManagementService:
    def __init__(self,db,cfg):self.db,self.cfg=db,cfg;self.daily_bucket=None

    def claim(self):
        with self.db.tx() as c:
            row=c.execute("SELECT * FROM jobs WHERE status='pending' AND kind IN ('agent_report','manager_review','manager_daily') AND (? OR kind='manager_daily' AND json_extract(payload,'$.date')>='2026-10-21') AND available_at<=? ORDER BY priority,created_at LIMIT 1",(self.db.get('engine_enabled'),now())).fetchone()
            if not row:return None
            c.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=?",(now(),row['id']))
            return dict(row)

    async def runner(self,stop):
        while not stop.is_set():
            job=self.claim()
            if not job:
                try:await asyncio.wait_for(stop.wait(),2)
                except asyncio.TimeoutError:pass
                continue
            payload=json.loads(job['payload'])
            status='completed';error=None
            try:
                if job['kind']=='agent_report':result=await write_report(self.db,self.cfg,job['agent_id'],payload.get('date'))
                elif job['kind']=='manager_daily':result=await decide_daily(self.db,self.cfg,payload['date'])
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
        with self.db.tx() as c:
            c.execute("UPDATE jobs SET status='uncertain',error='Vorheriger Berichtsprozess unterbrochen; keine automatische Wiederholung',updated_at=? WHERE status='running' AND kind IN ('agent_report','manager_review','manager_daily')",(now(),))
        runners=[asyncio.create_task(self.runner(stop)) for _ in range(2)]
        try:
            while not stop.is_set():
                at=datetime.now(timezone.utc)
                if self.db.get('engine_enabled'):
                    # The manager may review continuously; trading-session gates are separate.
                    schedule(self.db,self.cfg,at)
                bucket=int(at.timestamp())//60
                if self.daily_bucket!=bucket:
                    await asyncio.to_thread(schedule_daily,self.db,self.cfg,at)
                    self.daily_bucket=bucket
                try:await asyncio.wait_for(stop.wait(),15)
                except asyncio.TimeoutError:pass
        finally:
            for task in runners:task.cancel()
            await asyncio.gather(*runners,return_exceptions=True)
