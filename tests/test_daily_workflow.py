import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from backend.config import Settings,now
from backend.db import dumps,uid
from backend.daily import schedule_daily,decide_daily,closeout_view,research_view,promotion_ready
from backend.reporting import day_evidence,evidence_hash
from backend.intelligence import AI,apply_rotations,agent_context
from backend.calendar import phase
from backend.worker import Worker
from backend.management import ManagementService

END=datetime(2026,10,20,16,30,tzinfo=timezone.utc)
CFG=Settings(_env_file=None,openai_api_key='fixture')


def completed_reports(db):
    schedule_daily(db,CFG,END)
    cycle=db.one('SELECT * FROM daily_cycles')
    for aid,digest in json.loads(cycle['reports']).items():
        with db.tx() as c:
            c.execute('INSERT INTO agent_reports VALUES(?,?,?,?,?,?,?,?)',(uid(),int(aid),cycle['date'],digest,
                'Ich habe meine Leistung geprüft; für weitere Schlüsse fehlen Daten.',dumps({}),CFG.openai_model,now()))
    schedule_daily(db,CFG,END+timedelta(minutes=1))


def test_all_100_self_reviews_are_scheduled_once_after_day_end(db):
    schedule_daily(db,CFG,END-timedelta(seconds=1))
    assert not db.all('SELECT * FROM daily_cycles')
    schedule_daily(db,CFG,END)
    schedule_daily(db,CFG,END+timedelta(seconds=10))
    jobs=db.all("SELECT * FROM jobs WHERE kind='agent_report'")
    assert len(jobs)==100 and len({j['agent_id'] for j in jobs})==100
    assert not db.all("SELECT * FROM jobs WHERE kind='manager_daily'")
    assert closeout_view(db)['report_count']==0
    with db.tx() as c:c.execute('INSERT INTO agent_reports VALUES(?,?,?,?,?,?,?,?)',
        (uid(),76,'2026-10-20','old-unmatched-evidence','Alter Bericht',dumps({}),CFG.openai_model,now()))
    assert closeout_view(db)['report_count']==0  # Old/intraday reports are not the final self-review.
    assert not db.all('SELECT * FROM orders')


def test_early_close_and_next_day_recovery_of_reports(db):
    with db.tx() as c:c.execute("UPDATE sessions SET closes_at='2026-10-20T16:00:00+00:00'")
    schedule_daily(db,CFG,END-timedelta(minutes=30))
    assert len(db.all("SELECT * FROM jobs WHERE kind='agent_report'"))==100
    completed_reports(db)
    with db.tx() as c:c.execute("DELETE FROM jobs WHERE kind='manager_daily'")
    schedule_daily(db,CFG,END+timedelta(hours=14))
    assert db.one("SELECT * FROM jobs WHERE kind='manager_daily'")
    assert len(db.all('SELECT * FROM daily_cycles'))==1


@pytest.mark.asyncio
async def test_daily_manager_waits_for_all_reports_then_persists_no_change_once(db,monkeypatch):
    schedule_daily(db,CFG,END)
    with pytest.raises(ValueError,match='100 Eigenbewertungen'):await decide_daily(db,CFG,'2026-10-20')
    completed_reports(db)
    calls=[]
    async def call(self,kind,messages,**kwargs):
        assert kind=='manager_daily'
        facts=json.loads(messages[0]['content'])['agents']
        assert len(facts)==100 and all(a['report_id'] for a in facts)
        calls.append(kind)
        return SimpleNamespace(output_text=dumps({'summary':'Keine Umbesetzung: derzeit unzureichende Evidenz für einen Aufstieg.','swaps':[]}))
    monkeypatch.setattr(AI,'call',call)
    await decide_daily(db,CFG,'2026-10-20');await decide_daily(db,CFG,'2026-10-20')
    assert len(calls)==1
    view=closeout_view(db)
    assert view['cycle']['status']=='completed' and view['report_count']==100
    assert not view['actions'] and not db.all('SELECT * FROM orders')


@pytest.mark.asyncio
async def test_valid_delegated_swaps_apply_only_next_morning_preserving_50_25_25(db,monkeypatch):
    completed_reports(db)
    monkeypatch.setattr('backend.daily.promotion_ready',lambda d,a:a['id'] in (1,51))
    async def call(*args,**kwargs):return SimpleNamespace(output_text=dumps({'summary':'Zwei belegte Tausche für morgen.',
        'swaps':[{'promote':1,'demote':52,'reason':'Research-Kandidat mit geprüfter OOS-Evidenz.'},{'promote':51,'demote':76,'reason':'Demo-Kandidat mit belastbarer Handelsstichprobe.'}]}))
    monkeypatch.setattr(AI,'call',call)
    result=await decide_daily(db,CFG,'2026-10-20')
    assert len(result['decision_ids'])==2
    effective=result['effective_date']
    assert db.one('SELECT department FROM agents WHERE id=1')['department']=='research'
    assert apply_rotations(db,END)==[]
    with db.tx() as c:c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(effective,effective+'T09:30:00-04:00',effective+'T16:00:00-04:00','fixture'))
    morning=datetime.fromisoformat(effective+'T06:00:00+00:00')
    assert len(apply_rotations(db,morning))==2
    assert apply_rotations(db,morning)==[]
    assert {r['department']:r['n'] for r in db.all('SELECT department,COUNT(*) n FROM agents GROUP BY department')}=={'research':50,'demo':25,'fund':25}
    assert db.one('SELECT department FROM agents WHERE id=51')['department']=='fund'
    assert not db.all('SELECT * FROM orders')


@pytest.mark.asyncio
@pytest.mark.parametrize('swaps',[
    [{'promote':1,'demote':76,'reason':'Direkter Sprung ist nicht zulässig.'}],
    [{'promote':51,'demote':76,'reason':'Fehlende Evidenz darf nicht reichen.'}],
    [{'promote':1,'demote':51,'reason':'Erster Tausch mit Kandidat.'},{'promote':1,'demote':52,'reason':'Doppelter Kandidat ist falsch.'}]])
async def test_invalid_manager_plan_cannot_partially_create_rotations(db,monkeypatch,swaps):
    completed_reports(db)
    monkeypatch.setattr('backend.daily.promotion_ready',lambda d,a:a['id']==1)
    async def call(*a,**kw):return SimpleNamespace(output_text=dumps({'summary':'Ein Personalplan mit ungültigen Vorgaben.','swaps':swaps}))
    monkeypatch.setattr(AI,'call',call)
    with pytest.raises(ValueError):await decide_daily(db,CFG,'2026-10-20')
    assert not db.all('SELECT * FROM decisions')


def test_no_promotion_without_actual_evidence_and_context_reads_reports(db):
    for aid in (1,51,76):assert not promotion_ready(db,db.one('SELECT * FROM agents WHERE id=?',(aid,)))
    completed_reports(db)
    context=agent_context(db,76)
    assert context['previous_reports'] and context['daily_manager']


def test_research_promotion_requires_distinct_oos_tests_across_symbols(db):
    result=dumps({'out_of_sample':{'return_pct':2,'trades':[{}]*5}})
    def insert(symbol,params):
        with db.tx() as c:c.execute('INSERT INTO backtests VALUES(?,?,?,?,?,?,?,?)',
            (uid(),1,'agent-001-v1',symbol,'dataset',dumps(params),result,now()))
    agent=db.one('SELECT * FROM agents WHERE id=1')
    for _ in range(3):insert('SPY',{'lookback':2})
    assert not promotion_ready(db,agent)
    insert('QQQ',{'lookback':2})
    assert not promotion_ready(db,agent)
    insert('SPY',{'lookback':3})
    assert promotion_ready(db,agent)


def test_exchange_open_is_independent_of_worker_stopping(db):
    result=phase(db,datetime(2026,10,20,18,tzinfo=timezone.utc))
    assert result['phase']=='stopped' and result['exchange_open'] is True and not result['trading']
    assert phase(db,datetime(2026,10,20,21,tzinfo=timezone.utc))['exchange_open'] is False


def test_morning_context_omits_duplicate_candles_but_preserves_signal_evidence(db):
    from backend.signals import SignalEngine
    from conftest import AT
    signal=SignalEngine(db).evaluate(76,'AAPL','buy',AT)
    context=agent_context(db,76)
    proof=context['signal_decisions'][0]['observations']
    assert 'bars' not in proof and proof['bars_count']>0
    assert proof['indicators']==signal.observations['indicators']
    original=json.loads(db.one('SELECT observations FROM signal_decisions WHERE id=?',(signal.id,))['observations'])
    assert original['bars']  # No audit evidence is removed.


@pytest.mark.asyncio
async def test_morning_research_continues_hourly_without_placing_orders(db,monkeypatch):
    class Clock(datetime):
        current=datetime(2026,10,20,5,30,tzinfo=timezone.utc)
        @classmethod
        def now(cls,tz=None):return cls.current
    monkeypatch.setattr('backend.worker.datetime',Clock)
    worker=Worker(db,CFG)
    await worker.tick(phase(db,Clock.current))
    await worker.tick(phase(db,Clock.current+timedelta(seconds=10)))
    assert len(db.all("SELECT * FROM jobs WHERE kind='analysis'"))==100
    Clock.current+=timedelta(hours=1)
    await worker.tick(phase(db,Clock.current))
    assert len(db.all("SELECT * FROM jobs WHERE kind='analysis'"))==100
    with db.tx() as c:c.execute("UPDATE jobs SET status='completed' WHERE kind='analysis'")
    Clock.current+=timedelta(hours=1)
    await worker.tick(phase(db,Clock.current))
    assert len(db.all("SELECT * FROM jobs WHERE kind='analysis'"))==200
    assert not db.all('SELECT * FROM orders')


def test_daily_staffing_jobs_are_owned_only_by_management(db):
    from backend.worker import enqueue
    jid=enqueue(db,'manager_daily',{'date':'2026-10-20'})
    assert Worker(db,CFG).claim() is None
    assert ManagementService(db,CFG).claim()['id']==jid


def test_all_strategy_tests_are_paginated_with_full_results(db):
    with db.tx() as c:
        for i in range(12):c.execute('INSERT INTO backtests VALUES(?,?,?,?,?,?,?,?)',
            (str(i),1,'agent-001-v1','SPY','fixture',dumps({'lookback':2}),dumps({'out_of_sample':{'return_pct':i,'trades':[]}}),now()))
    one,two=research_view(db),research_view(db,10)
    assert one['total']==12 and len(one['rows'])==10 and len(two['rows'])==2
    assert {r['id'] for r in one['rows']}.isdisjoint(r['id'] for r in two['rows'])
    assert isinstance(one['rows'][0]['result'],dict)
