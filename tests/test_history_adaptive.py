import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from backend.config import Settings,units,now
from backend.db import dumps,uid
from backend.history import calendar_month,career,performance_history,agent_archive,day_window
from backend.reporting import day_view,review_agents
from backend.intelligence import AI,apply_rotations
from backend.ledger import Ledger,RiskError
from backend.news_agents import prepare_strategy,initial_strategy,Thesis,save_thesis
from backend.execution import plan_order
from backend.signals import SignalEngine
from backend.worker import Worker,enqueue
from backend.cloud import allowed_path
from conftest import AT

CFG=Settings(_env_file=None,openai_api_key='fixture')

def dated_roster(db):
    with db.tx() as c:
        c.execute("UPDATE agents SET created_at='2026-10-19T05:30:00+00:00'")
        c.execute("UPDATE portfolios SET created_at='2026-10-19T05:30:00+00:00'")

def rotation(db,first=51,second=76,stamp='2026-10-21T06:00:00+00:00',status='applied',from_first='demo',from_second='fund'):
    did=uid()
    with db.tx() as c:
        c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',(did,'rotation',dumps({'first':first,'second':second,'from_first':from_first,'from_second':from_second}),
            'Belegte Entwicklung über mehrere Tage verglichen.',status,'2026-10-21','2026-10-20T17:00:00+00:00',stamp if status=='applied' else None))
        if status=='applied':
            c.execute('UPDATE agents SET department=? WHERE id=?',(from_second,first));c.execute('UPDATE agents SET department=? WHERE id=?',(from_first,second))
    return did

def test_career_keeps_full_round_trip_and_ignores_approved_swaps(db):
    dated_roster(db);rotation(db);rotation(db,stamp='2026-10-21T07:00:00+00:00',from_first='fund',from_second='demo')
    rotation(db,status='approved')
    result=career(db,51)
    assert [p['department'] for p in result['periods']]==['demo','fund','demo']
    assert len(result['changes'])==2 and result['complete']
    assert result['periods'][0]['ended_at']==result['periods'][1]['started_at']
    assert result['periods'][-1]['ended_at'] is None

def test_history_flags_unrecorded_role_changes_instead_of_inventing_a_career(db):
    with db.tx() as c:c.execute("UPDATE agents SET department='fund' WHERE id=1")
    assert not career(db,1)['complete']

def test_old_day_keeps_fund_trades_after_demotion_and_no_future_reviews(db,monkeypatch):
    dated_roster(db);monkeypatch.setattr('backend.ledger.now',lambda:AT.isoformat())
    order=Ledger(db).submit(76,'AAPL','buy',1,'before-demotion',stop_usd=98,reason='Original valid signal',at=AT)
    fill=Ledger(db).fill(order['id'],AT);rotation(db)
    with db.tx() as c:c.execute('INSERT INTO manager_reviews VALUES(?,?,?,?,?,?,?)',(uid(),76,9,'Later review','{}','fixture','2026-10-21T10:00:00+00:00'))
    past=day_view(db,76,'2026-10-20')
    assert past['trade_count']==1 and past['trades'][0]['id']==fill['id']
    assert past['profile']['department']=='fund' and past['profile']['current_department']=='demo'
    assert past['manager_review'] is None and past['positions']==[]
    assert past['actions'][0]['portfolio_id']=='fund'
    history=performance_history(db,76,'2026-10-20')
    assert next(r for r in history['roles'] if r['department']=='fund')['fills']==1
    assert next(r for r in history['roles'] if r['department']=='demo')['fills']==0
    assert not history['recent_reviews']

def test_calendar_signed_pnl_cashflow_adjustment_ties_and_latest_daily_score(db):
    dated_roster(db)
    with db.tx() as c:
        c.execute("DELETE FROM equity WHERE portfolio_id='fund'")
        for stamp,value in [('2026-10-19T20:00:00+00:00',3000),('2026-10-20T16:40:00+00:00',3150),('2026-10-21T16:40:00+00:00',3120)]:
            c.execute('INSERT INTO equity VALUES(?,?,?,?,?,?,?)',(uid(),'fund',units(value),units(value),0,1,stamp))
        c.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?,?)',(uid(),'fund','capital-flow','deposit',units(100),units(3100),'2026-10-20T10:00:00+00:00'))
        for aid,score,stamp in [(76,8,'2026-10-20T10:00:00+00:00'),(76,6,'2026-10-20T16:30:00+00:00'),(77,7,'2026-10-20T16:30:00+00:00'),(78,7,'2026-10-20T16:30:00+00:00'),(1,10,'2026-10-22T10:00:00+00:00')]:
            c.execute('INSERT INTO manager_reviews VALUES(?,?,?,?,?,?,?)',(uid(),aid,score,'Saved assessment','{}','fixture',stamp))
    result=calendar_month(db,'2026-10',datetime(2026,10,21,17,tzinfo=timezone.utc))
    d20=result['days'][19];d21=result['days'][20];d22=result['days'][21]
    assert d20['pnl_eur']==50 and d20['capital_flow_eur']==100
    assert {r['agent_id'] for r in d20['best_agents']}=={77,78} and d20['best_agent_count']==2
    assert d21['pnl_eur']==-30 and d21['status']=='closed'
    assert d22['status']=='future' and d22['pnl_eur'] is None and not d22['best_agents']
    with db.tx() as c:c.execute("UPDATE equity SET valuation_complete=0 WHERE created_at='2026-10-20T16:40:00+00:00'")
    unknown=calendar_month(db,'2026-10',datetime(2026,10,21,17,tzinfo=timezone.utc))
    assert unknown['days'][19]['pnl_eur'] is None and unknown['days'][20]['pnl_eur'] is None

def test_berlin_day_windows_handle_midnight_and_dst_without_24h_assumption():
    _,start,end=day_window('2026-10-25')
    assert (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()==25*3600
    assert start=='2026-10-24T22:00:00+00:00'

@pytest.mark.parametrize('value',['2026-13','2026-00','bad','2026-01;DROP TABLE agents','1999-01'])
def test_calendar_rejects_invalid_months(db,value):
    with pytest.raises(ValueError):calendar_month(db,value)

def test_cloud_calendar_and_history_allow_only_specific_date_parameters():
    assert allowed_path('GET','calendar?month=2026-10')
    assert allowed_path('GET','agents/76/history?day=2026-10-20&month=2026-10')
    assert not allowed_path('GET','agents/76/history?day=2026-10-20&day=2026-10-21')
    assert not allowed_path('GET','calendar?month=2026-99')
    assert not allowed_path('GET','calendar?sql=secret')

@pytest.mark.asyncio
async def test_manager_receives_previous_days_and_role_results(db,monkeypatch):
    dated_roster(db)
    with db.tx() as c:c.execute('INSERT INTO agent_reports VALUES(?,?,?,?,?,?,?,?)',(uid(),1,'2026-10-19','prior','Previous day: poor source verification.','{}','fixture','2026-10-19T17:00:00+00:00'))
    async def response(self,kind,messages,**kwargs):
        facts=json.loads(messages[0]['content'])['agents'][0]
        assert facts['past_performance']['previous_reports'][0]['report_date']=='2026-10-19'
        assert len(facts['past_performance']['roles'])==3 and 'history_policy' in json.loads(messages[0]['content'])
        return SimpleNamespace(output_text=dumps({'ratings':[{'agent_id':1,'score':6,'reason':'Earlier weakness in source verification considered.'}]}))
    monkeypatch.setattr(AI,'call',response);await review_agents(db,CFG,[1])

def information_setup(db,research_morning,monkeypatch):
    db.set('paper_sizing_mode','strategy')
    with db.tx() as c:c.execute("UPDATE agent_mandates SET approach='news' WHERE agent_id=76")
    prepare_strategy(db,76)
    spec=initial_strategy()|{'stop_pct':None,'take_profit_pct':None}
    with db.tx() as c:c.execute('UPDATE strategies SET spec=? WHERE agent_id=76',(dumps(spec),))
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return AT-timedelta(minutes=20)
    monkeypatch.setattr('backend.news_agents.datetime',Clock)
    monkeypatch.setattr('backend.news_agents.now',lambda:Clock.now().isoformat())
    monkeypatch.setattr('backend.ledger.now',lambda:AT.isoformat())
    def decision(intent,nid='source-1',target=.1,fraction=None):
        with db.tx() as c:c.execute('INSERT OR IGNORE INTO news VALUES(?,?,?,?,?,?,?,?,?,?)',(nid,'Issuer','New relevant fact '+nid,'Verified event report','https://example.org/'+nid,'["AAPL"]',(AT-timedelta(hours=1)).isoformat(),(AT-timedelta(hours=1)).isoformat(),'reported','company'))
        tid=save_thesis(db,76,Thesis(symbol='AAPL',event_type='company',direction='negative' if intent=='exit' else 'positive',confidence=.9,evidence_ids=[nid],summary='Information decision '+intent,company_context='Uncertainty documented.'),spec)
        with db.tx() as c:
            payload=json.loads(c.execute('SELECT payload FROM thesis_dossiers WHERE thesis_id=?',(tid,)).fetchone()[0]);payload.update(intent=intent,target_position_pct=target,reduce_fraction=fraction)
            c.execute('UPDATE thesis_dossiers SET payload=? WHERE thesis_id=?',(dumps(payload),tid))
        return tid
    return decision

def test_information_trader_without_fixed_stop_tp_can_add_reduce_and_hold_idempotently(db,research_morning,monkeypatch):
    decision=information_setup(db,research_morning,monkeypatch)
    def execute(side,key):
        plan=plan_order(db,76,'AAPL',side,AT)
        order=Ledger(db).submit(76,'AAPL',side,client_id=key,reason='New source-grounded decision',at=AT,**plan)
        return Ledger(db).fill(order['id'],AT)
    decision('enter');execute('buy','entry-information')
    pos=db.one('SELECT * FROM positions WHERE agent_id=76');original=float(pos['qty'])
    assert pos['stop_usd']=='0' and pos['take_usd'] is None
    # No timed exit even if the stored event-study horizon is tiny.
    with db.tx() as c:c.execute("UPDATE positions SET created_at='2026-10-19T10:00:00+00:00'")
    assert not SignalEngine(db).evaluate(76,'AAPL','sell',AT).valid
    decision('add',target=.2)
    assert not SignalEngine(db).evaluate(76,'AAPL','buy',AT).valid # same old evidence
    decision('add',nid='source-2',target=.2);execute('buy','add-information')
    expanded=float(db.one('SELECT qty FROM positions WHERE agent_id=76')['qty']);assert expanded>original
    assert not SignalEngine(db).evaluate(76,'AAPL','buy',AT).valid
    decision('reduce',nid='source-3',fraction=.5);execute('sell','reduce-information')
    remaining=float(db.one('SELECT qty FROM positions WHERE agent_id=76')['qty'])
    assert abs(remaining-expanded*.5)<.000002
    assert not SignalEngine(db).evaluate(76,'AAPL','sell',AT).valid
    assert Ledger(db).portfolio('fund')['positions'][0]['value_eur']<=Ledger(db).portfolio('fund')['equity_eur']*.25
    assert Ledger(db).reconcile()

def test_discretionary_agents_research_instead_of_new_automatic_backtests(db,research_morning):
    from backend.news_agents import configure
    with db.tx() as c:c.execute('DELETE FROM agent_mandates')
    configure(db);old=enqueue(db,'backtest',{'symbol':'AAPL'},26)
    w=Worker(db,CFG);w.schedule_research(research_morning.current)
    assert db.one('SELECT status FROM jobs WHERE id=?',(old,))['status']=='superseded'
    pending=db.all("SELECT agent_id FROM jobs WHERE kind='backtest' AND status='pending'")
    assert len(pending)==150
    assert all(db.one('SELECT approach FROM agent_mandates WHERE agent_id=?',(r['agent_id'],))['approach']!='news' for r in pending)


@pytest.mark.parametrize('invalid',['stale','cap','no_signal','research'])
def test_adaptive_orders_still_require_valid_signals_data_cap_and_trading_role(db,research_morning,monkeypatch,invalid):
    decision=information_setup(db,research_morning,monkeypatch);decision('enter')
    with db.tx() as c:
        if invalid=='stale':c.execute('UPDATE quotes SET market_at=?',((AT-timedelta(minutes=15)).isoformat(),))
        if invalid=='no_signal':c.execute('DELETE FROM event_theses')
    with pytest.raises(RiskError):
        Ledger(db).submit(26 if invalid=='research' else 76,'AAPL','buy',10 if invalid=='cap' else 1,'invalid-adaptive-'+invalid,reason='A claim alone is insufficient',at=AT)
    assert not db.all('SELECT * FROM orders') and not db.all('SELECT * FROM fills')


def test_latest_schema_requires_information_intent_and_optional_risk_prices():
    from backend.news_agents import CatalystDecision,EventStrategy
    for model in (CatalystDecision,EventStrategy):
        schema=model.model_json_schema();assert set(schema['required'])==set(schema['properties'])
    assert EventStrategy(**(initial_strategy()|{'stop_pct':None,'take_profit_pct':None})).stop_pct is None


def test_changed_information_cancels_pending_order_before_fill(db,research_morning,monkeypatch):
    decision=information_setup(db,research_morning,monkeypatch);decision('enter')
    plan=plan_order(db,76,'AAPL','buy',AT)
    order=Ledger(db).submit(76,'AAPL','buy',client_id='old-information',reason='Original source decision',at=AT,**plan)
    decision('enter',nid='new-information',target=.05)
    assert Ledger(db).fill(order['id'],AT) is None
    assert db.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status']=='cancelled'
    assert db.one("SELECT reserved_u FROM portfolios WHERE id='fund'")['reserved_u']==0
    assert not db.all('SELECT * FROM fills')
