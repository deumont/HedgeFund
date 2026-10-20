import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from backend.config import Settings,now
from backend.db import dumps,uid
from backend.research import research_window,ResearchClosed,agent_research,research_roster,team_view
from backend.worker import Worker,enqueue
from backend.intelligence import AI,apply_rotations
from backend.backtest import run_backtest
from conftest import AT

CFG=Settings(_env_file=None,openai_api_key='fixture')


@pytest.mark.parametrize('at,opened',[
    ('2026-10-20T05:29:59+00:00',False),('2026-10-20T05:30:00+00:00',True),
    ('2026-10-20T13:29:59+00:00',True),('2026-10-20T13:30:00+00:00',False),
    ('2026-12-20T06:30:00+00:00',True),('2026-12-20T14:30:00+00:00',False)])
def test_research_window_berlin_including_dst(at,opened):
    assert research_window(datetime.fromisoformat(at))['open'] is opened


def test_outside_window_queue_does_not_claim_research_but_safety_data_can_run(db,research_morning):
    research_morning.current=datetime(2026,10,20,13,30,tzinfo=timezone.utc)
    analysis=enqueue(db,'analysis',agent_id=1,priority=0)
    enqueue(db,'backtest',{'strategy_id':'agent-001-v1','symbol':'SPY'},1,priority=0)
    news=enqueue(db,'news',priority=50)
    worker=Worker(db,CFG)
    assert worker.claim()['id']==news
    assert worker.claim() is None
    assert db.one('SELECT attempts FROM jobs WHERE id=?',(analysis,))['attempts']==0
    research_morning.current+=timedelta(hours=18)
    assert worker.claim()['kind'] in ('analysis','backtest')


@pytest.mark.asyncio
async def test_direct_execution_and_model_entry_cannot_bypass_session(db,research_morning,monkeypatch):
    research_morning.current=datetime(2026,10,20,13,30,tzinfo=timezone.utc)
    calls=[]
    async def forbidden(*a,**kw):calls.append(True);raise AssertionError('No model call outside research')
    monkeypatch.setattr(AI,'call',forbidden)
    with pytest.raises(ResearchClosed):await AI(db,CFG).analyze(1)
    with pytest.raises(ResearchClosed):await Worker(db,CFG).execute({'kind':'analysis','agent_id':1,'payload':'{}'})
    with pytest.raises(ResearchClosed):run_backtest(db,1,'agent-001-v1','SPY')
    assert calls==[] and not db.all('SELECT * FROM analyses') and not db.all('SELECT * FROM backtests')


def decision():
    return {'action':'research','symbol':'SPY','qty':'0','stop_usd':None,'take_usd':None,'hypothesis':'Schwelle nach OOS prüfen.',
        'conclusion':'Weitere Prüfung statt Order.','evidence_ids':[],'rejected_alternatives':['Ungeprüfter Einstieg'],'memory':'Testen.',
        'proposed_strategy':{'kind':'momentum','lookback':3,'holding_bars':4,'threshold':.02,'stop_pct':.02,'position_pct':.25,
        'timeframe_minutes':15,'max_data_delay_minutes':15,'requires_realtime':False,'requires_full_market':False}}


@pytest.mark.asyncio
async def test_late_model_result_is_saved_without_adaptation_and_resumed_without_new_call(db,research_morning,monkeypatch):
    calls=[]
    async def reply(*a,**kw):
        calls.append(True);research_morning.current=datetime(2026,10,20,13,30,tzinfo=timezone.utc)
        return SimpleNamespace(output=[],output_text=dumps(decision()))
    monkeypatch.setattr(AI,'call',reply)
    with pytest.raises(ResearchClosed):await AI(db,CFG).analyze(1)
    assert len(db.all('SELECT * FROM strategies WHERE agent_id=1'))==1
    assert not db.all('SELECT * FROM analyses') and db.one('SELECT * FROM research_drafts WHERE agent_id=1')
    research_morning.current=datetime(2026,10,21,5,30,tzinfo=timezone.utc)
    await AI(db,CFG).analyze(1)
    assert len(calls)==1 and not db.all('SELECT * FROM research_drafts')
    assert len(db.all('SELECT * FROM strategies WHERE agent_id=1'))==2
    assert not db.all('SELECT * FROM orders')


def test_backtest_stops_at_cutoff_without_result_or_strategy_change(db,research_morning,monkeypatch):
    from test_calendar_backtest import bars,SPEC
    import backend.backtest as backtest
    with db.tx() as c:
        c.execute("UPDATE strategies SET spec=?,status='candidate' WHERE id='agent-001-v1'",(dumps(SPEC|{'timeframe_minutes':1440}),))
        for b in bars(400):c.execute('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(b.values()))
    original=backtest.simulate
    def crossing(*a,**kw):
        research_morning.current=datetime(2026,10,20,13,30,tzinfo=timezone.utc)
        return original(*a,**kw)
    monkeypatch.setattr(backtest,'simulate',crossing)
    with pytest.raises(ResearchClosed):run_backtest(db,1,'agent-001-v1','SPY')
    assert not db.all('SELECT * FROM backtests')
    assert db.one("SELECT status FROM strategies WHERE id='agent-001-v1'")['status']=='candidate'


def test_research_timeline_updates_exact_changes_results_and_no_raw_context(db):
    before=agent_research(db,1)
    with db.tx() as c:
        c.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?)',('analysis-new',1,'agent-001-v1',dumps({'private':'context'}),dumps(decision()),now()))
        spec=json.loads(c.execute("SELECT spec FROM strategies WHERE id='agent-001-v1'").fetchone()['spec']);spec['threshold']=.02
        c.execute('INSERT INTO strategies VALUES(?,?,?,?,?,?,?)',('v2',1,2,dumps(spec),'Neue Schwelle anhand eines Tests.','candidate',now()))
    after=agent_research(db,1)
    assert after['counts']['analyses']==before['counts']['analyses']+1
    change=next(r for r in after['timeline'] if r['id']=='v2')
    assert change['changes']['threshold']=={'before':.01,'after':.02}
    assert 'context' not in next(r for r in after['timeline'] if r['kind']=='analysis')
    assert len(research_roster(db))==100


def test_team_view_distinguishes_planned_deferred_and_actual_changes(db):
    from backend.ledger import Ledger
    order=Ledger(db).submit(76,'AAPL','buy',1,'team-position',stop_usd=98,reason='fixture valid entry',at=AT)
    Ledger(db).fill(order['id'],AT)
    payload={'first':51,'second':76,'from_first':'demo','from_second':'fund','source':'manager_daily'}
    with db.tx() as c:c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',('swap','rotation',dumps(payload),'Belegter Tausch.','approved','2026-10-21',now(),None))
    row=team_view(db)['actions'][0]
    assert row['deferred'] and row['applied_at'] is None
    assert not apply_rotations(db,datetime(2026,10,21,6,tzinfo=timezone.utc))
    with db.tx() as c:c.execute("UPDATE decisions SET status='applied',applied_at=? WHERE id='swap'",(now(),))
    row=team_view(db)['actions'][0]
    assert row['status']=='applied' and row['applied_at'] and not row['deferred']


def test_cloud_allows_only_scoped_research_and_team_reads():
    from backend.cloud import allowed_path
    for p in ['research-roster','research/agents/1','research/agents/100?offset=10','team?offset=20']:
        assert allowed_path('GET',p) and not allowed_path('POST',p)
    assert not allowed_path('GET','research/agents/101')
