import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from backend.config import Settings,now
from backend.db import dumps,uid
from backend.models import agent_model,request_model
from backend.intelligence import AI,BudgetError,apply_rotations
from backend.daily import schedule_daily,decide_daily
from backend.budget import reconcile_rate_rejections
from backend.worker import enqueue

CFG=Settings(_env_file=None,openai_api_key='fixture')

def test_models_follow_promotions_and_demotions_in_both_directions(db):
    assert agent_model(db,CFG,1)=='gpt-5.4-mini'
    assert agent_model(db,CFG,51)==agent_model(db,CFG,76)=='gpt-6.1-sol'
    with db.tx() as c:
        c.execute("UPDATE agents SET department='demo' WHERE id=1")
        c.execute("UPDATE agents SET department='research' WHERE id=51")
    assert agent_model(db,CFG,1)=='gpt-6.1-sol' and agent_model(db,CFG,51)=='gpt-5.4-mini'
    assert request_model(db,CFG,'agent_report',51)=='gpt-5.4-mini'
    assert request_model(db,CFG,'manager_daily',76)=='gpt-5.4-mini'
    with pytest.raises(ValueError):agent_model(db,CFG,999)

def test_analysis_is_not_starved_by_a_backtest_backlog(db,research_morning):
    from backend.worker import Worker
    for _ in range(2):enqueue(db,'analysis',{},1,60)
    for _ in range(10):enqueue(db,'backtest',{},1,45)
    w=Worker(db,CFG)
    assert [w.claim()['kind'] for _ in range(4)]==['analysis','backtest','analysis','backtest']

@pytest.mark.asyncio
async def test_daily_minimum_swap_runs_after_close_even_when_budget_blocks_reports(db,monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,21,17,tzinfo=timezone.utc)
    monkeypatch.setattr('backend.intelligence.datetime',Clock);monkeypatch.setattr('backend.daily.datetime',Clock)
    with db.tx() as c:c.execute('INSERT INTO sessions VALUES(?,?,?,?)',('2026-10-21','2026-10-21T09:30:00-04:00','2026-10-21T16:00:00-04:00','fixture'))
    async def unavailable(*a,**kw):raise BudgetError('Fixture budget exhausted')
    monkeypatch.setattr(AI,'call',unavailable)
    schedule_daily(db,CFG,Clock.now())
    assert db.one("SELECT id FROM jobs WHERE kind='manager_daily'")
    result=await decide_daily(db,CFG,'2026-10-21')
    assert len(result['decision_ids'])>=1
    assert len(db.all("SELECT * FROM decisions WHERE status='applied'"))>=1
    assert {r['department']:r['n'] for r in db.all('SELECT department,count(*) n FROM agents GROUP BY department')}=={'research':50,'demo':25,'fund':25}
    assert (await decide_daily(db,CFG,'2026-10-21'))['decision_ids']==result['decision_ids']
    assert not db.all('SELECT * FROM orders')
    payload=json.loads(db.one('SELECT payload FROM decisions')['payload'])
    assert payload['selection_method']=='manager_policy'

@pytest.mark.asyncio
async def test_daily_requirement_does_not_allow_early_role_changes(db,monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,21,8,tzinfo=timezone.utc)
    monkeypatch.setattr('backend.daily.datetime',Clock)
    schedule_daily(db,CFG,datetime(2026,10,21,17,tzinfo=timezone.utc))
    with pytest.raises(ValueError,match='Handelsschluss'):await decide_daily(db,CFG,'2026-10-21')
    assert not db.all('SELECT * FROM decisions')

def test_reconcile_only_unambiguous_terminal_429_and_preserve_other_uncertainty(db):
    at=datetime.now(timezone.utc)
    jid=enqueue(db,'analysis',{},1)
    with db.tx() as c:
        c.execute("UPDATE jobs SET status='failed',error='RateLimitError HTTP 429; fixture',updated_at=? WHERE id=?",(at.isoformat(),jid))
        c.execute('INSERT INTO usage VALUES(?,?,?,?,?,?,?,?,?,?)',('confirmed-429',1,'agent','gpt-6.1-sol',0,0,200000,0,'uncertain',(at-timedelta(seconds=1)).isoformat()))
        c.execute('INSERT INTO usage VALUES(?,?,?,?,?,?,?,?,?,?)',('network-unknown',2,'agent','gpt-6.1-sol',0,0,200000,0,'uncertain',at.isoformat()))
    db.event('job_failed','RateLimitError HTTP 429; fixture',1,data={'job_id':jid,'kind':'analysis'})
    fixed=reconcile_rate_rejections(db)
    assert len(fixed)==1 and fixed[0]['released_u']==200000
    assert db.one("SELECT status FROM usage WHERE id='network-unknown'")['status']=='uncertain'
    assert db.one("SELECT status FROM usage WHERE id='confirmed-429'")['status']=='rejected'
    assert reconcile_rate_rejections(db)==[]
