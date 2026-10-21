import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from backend.db import DB,dumps
from backend.catalog import seed
from backend.config import Settings
from backend.news_agents import initial_strategy,prepare_strategy,save_thesis,Thesis,run_event_study
from backend.signals import SignalEngine
from backend.worker import Worker,enqueue
from backend.ledger import Ledger
from conftest import AT

CFG=Settings(_env_file=None,openai_api_key='',watchlist='SPY')

def cohort(db,aid=76):
    with db.tx() as c:c.execute("UPDATE agent_mandates SET approach='news' WHERE agent_id=?",(aid,))

def article(db,nid='news-1',symbol='AAPL',published=None,received=None):
    published=published or AT-timedelta(hours=1)
    with db.tx() as c:c.execute('INSERT INTO news VALUES(?,?,?,?,?,?,?,?,?,?)',
        (nid,'Test company source','Company wins government contract','New contract reported, effect uncertain.',
         'https://example.test/news',dumps([symbol]),published.isoformat(),(received or published).isoformat(),'verified','company'))

def thesis(db,monkeypatch,**changes):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return AT-timedelta(minutes=16)
    monkeypatch.setattr('backend.news_agents.datetime',Clock)
    value=dict(symbol='AAPL',event_type='company',direction='positive',confidence=.9,evidence_ids=['news-1'],
               summary='Test hypothesis: contract may increase revenue.',company_context='Contract headline only; financial reports absent.')
    value.update(changes)
    return save_thesis(db,76,Thesis(**value))

def test_exactly_half_news_preserves_departments_and_accounts(tmp_path):
    db=DB(tmp_path/'cohorts.sqlite3');db.init();seed(db);seed(db)
    assert db.one("SELECT COUNT(*) n FROM agent_mandates WHERE approach='news'")['n']==50
    rows=db.all("SELECT department,COUNT(*) n FROM agents JOIN agent_mandates ON id=agent_id WHERE approach='news' GROUP BY department")
    assert {r['department']:r['n'] for r in rows}=={'research':24,'demo':13,'fund':13}
    assert db.one('SELECT COUNT(*) n FROM agents')['n']==100
    assert db.one('SELECT COUNT(*) n FROM portfolios')['n']==76

def test_news_agent_never_falls_back_to_technical_signal(db):
    cohort(db)
    assert not SignalEngine(db).evaluate(76,'AAPL','buy',AT).valid
    assert not db.all('SELECT * FROM orders')

@pytest.mark.parametrize('bad',[None,'missing','uncertain','confidence','stale_quote','future','unlinked','expired'])
def test_news_execution_evidence_and_market_gates(db,research_morning,monkeypatch,bad):
    cohort(db);prepare_strategy(db,76)
    article(db,symbol='MSFT' if bad=='unlinked' else 'AAPL',published=AT+timedelta(hours=1) if bad=='future' else None)
    if bad in ('future','unlinked','missing'):
        with pytest.raises(ValueError):thesis(db,monkeypatch,**({'evidence_ids':['invented']} if bad=='missing' else {}))
    else:
        thesis(db,monkeypatch,**({'direction':'uncertain'} if bad=='uncertain' else {'confidence':.5} if bad=='confidence' else {}))
    with db.tx() as c:
        c.execute('UPDATE agents SET paused=1 WHERE id!=76')
        c.execute('DELETE FROM bars')  # News entries cannot depend on technical indicators.
        if bad=='stale_quote':c.execute('UPDATE quotes SET market_at=?',((AT-timedelta(minutes=15)).isoformat(),))
        if bad=='expired':c.execute('UPDATE event_theses SET expires_at=?',((AT-timedelta(seconds=1)).isoformat(),))
    db.set('engine_enabled',False)
    Worker(db,CFG).monitor_signals(AT)
    fills=db.all('SELECT * FROM fills')
    assert len(fills)==(1 if bad is None else 0)
    if fills:
        proof=json.loads(db.one('SELECT s.observations FROM signal_decisions s JOIN order_signals os ON os.signal_id=s.id')['observations'])
        assert proof['event_thesis']['evidence_ids']=='["news-1"]' and proof['indicators']=={}
        assert Ledger(db).reconcile()
        assert Ledger(db).portfolio('fund')['positions'][0]['value_eur']<=750

def test_event_study_distinguishes_retrospective_results_from_profit(db,research_morning):
    cohort(db);prepare_strategy(db,76)
    strategy=db.one('SELECT * FROM strategies WHERE agent_id=76 ORDER BY version DESC LIMIT 1')
    spec=initial_strategy()|{'holding_bars':1}
    strategy['spec']=dumps(spec)
    article(db,published=AT-timedelta(minutes=120),received=AT)
    result=run_event_study(db,76,strategy,'AAPL')['result']
    assert result['observations']==1 and result['point_in_time_observations']==0
    assert result['full']['return_pct'] is None and result['full']['trades']==[]
    assert result['events'][0]['entry_time']>=result['events'][0]['available_at']
    empty=run_event_study(db,76,strategy,'MSFT')['result']
    assert empty['status']=='insufficient_event_history' and empty['mean_price_change_pct'] is None

def test_morning_assigns_each_agent_multiple_stocks_and_coalesces_old_backlog(db,research_morning):
    from backend.news_agents import configure
    with db.tx() as c:c.execute('DELETE FROM agent_mandates')
    configure(db)
    enqueue(db,'analysis',{},1);enqueue(db,'analysis',{},1)
    worker=Worker(db,Settings(_env_file=None,openai_api_key='fixture'))
    worker.schedule_research(research_morning.current)
    pending=db.all("SELECT * FROM jobs WHERE kind='analysis' AND status='pending'")
    assert len(pending)==100 and len({j['agent_id'] for j in pending})==100
    assert all(len(json.loads(j['payload'])['research_symbols'])==3 for j in pending)
    assert sum(json.loads(j['payload'])['approach']=='news' for j in pending)==50
    tests=db.all("SELECT * FROM jobs WHERE kind='backtest'")
    assert len(tests)==150 and all(t['agent_id'] not in set(range(26,50))|set(range(61,74))|set(range(76,89)) for t in tests) and any(json.loads(t['payload'])['symbol']!='SPY' for t in tests)
    assert db.one("SELECT COUNT(*) n FROM strategies WHERE json_extract(spec,'$.kind')='event_driven'")['n']==50
    assert not db.all('SELECT * FROM orders')

@pytest.mark.asyncio
async def test_morning_news_analysis_persists_real_model_result_and_thesis(db,research_morning,monkeypatch):
    from backend.intelligence import AI
    cohort(db);prepare_strategy(db,76);article(db)
    thesis(db,monkeypatch)  # freeze source clock; subsequent model thesis is independently validated.
    async def reply(*a,**kw):
        assert kw['schema']['properties']['event_thesis']
        return SimpleNamespace(output=[],output_text=dumps(dict(action='research',symbol='AAPL',qty='0',stop_usd=None,take_usd=None,
            hypothesis='Contract hypothesis needs verification.',conclusion='Company research completed.',evidence_ids=['news-1'],
            rejected_alternatives=['Technical entry'],memory='Verify contract contribution.',proposed_strategy=None,
            event_thesis=dict(symbol='AAPL',event_type='company',direction='uncertain',confidence=.8,evidence_ids=['news-1'],summary='Insufficient financial evidence.',company_context='Financial report unavailable.'))))
    monkeypatch.setattr(AI,'call',reply)
    aid,result=await AI(db,Settings(_env_file=None,openai_api_key='fixture')).analyze(76)
    assert db.one('SELECT * FROM analyses WHERE id=?',(aid,)) and result.action=='research'
    assert db.one('SELECT COUNT(*) n FROM event_theses')['n']==2
    assert not SignalEngine(db).evaluate(76,'AAPL','buy',AT).valid
    assert not db.all('SELECT * FROM orders')

def test_company_news_accepts_actual_sdk_dataset_shape(db,monkeypatch):
    from backend.providers import Providers
    provider=Providers(db,CFG)
    seen=[]
    row={'id':'sdk-news','content':'Actual company article body','created_at':AT.isoformat()}
    monkeypatch.setattr('backend.providers.data_client',lambda *a:SimpleNamespace(get_news=lambda r:SimpleNamespace(data={'news':[row]})))
    monkeypatch.setattr(provider,'store_news',seen.append)
    assert provider.company_news('AAPL')['articles']==1 and seen==[row]
    assert json.loads(db.one("SELECT payload FROM documents WHERE symbol='AAPL'")['payload'])['content']==row['content']
    assert provider.company_news('AAPL')['cached'] is True

def test_history_aggregates_complete_90min_bars_without_filling_gaps(db,monkeypatch):
    from backend.providers import Providers
    start=AT-timedelta(minutes=120)
    values=[SimpleNamespace(timestamp=start+timedelta(minutes=15*i),open=100,high=102,low=99,close=101,volume=500) for i in range(6)]
    requests=[]
    def get_bars(request):requests.append(request);return SimpleNamespace(data={'AAPL':values})
    monkeypatch.setattr('backend.providers.data_client',lambda *a:SimpleNamespace(get_stock_bars=get_bars))
    provider=Providers(db,CFG)
    assert provider.strategy_history('AAPL',initial_strategy()|{'timeframe_minutes':90})['bars']==1
    assert str(requests[0].timeframe)=='15Min'
    assert db.one("SELECT volume FROM bars WHERE timeframe='90Min'")['volume']==3000
    values.pop(2)
    with db.tx() as c:c.execute("DELETE FROM bars WHERE timeframe='90Min'")
    assert provider.strategy_history('AAPL',initial_strategy()|{'timeframe_minutes':90})['bars']==0

@pytest.mark.asyncio
async def test_worker_loads_missing_history_then_persists_event_test(db,research_morning,monkeypatch):
    cohort(db);prepare_strategy(db,76)
    strategy=db.one('SELECT * FROM strategies WHERE agent_id=76 ORDER BY version DESC LIMIT 1')
    with db.tx() as c:c.execute('DELETE FROM bars')
    worker=Worker(db,CFG);calls=[]
    monkeypatch.setattr(worker.providers,'company_news',lambda s:calls.append(('news',s)))
    def load(symbol,spec):
        calls.append(('history',symbol))
        with db.tx() as c:c.execute('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',
            (symbol,(AT-timedelta(days=1)).isoformat(),'15Min','100','101','99','100',1000,'Alpaca IEX','raw'))
    monkeypatch.setattr(worker.providers,'strategy_history',load)
    result=await worker.execute({'kind':'backtest','agent_id':76,'payload':dumps({'strategy_id':strategy['id'],'symbol':'MSFT'})})
    assert calls==[('news','MSFT'),('history','MSFT')]
    assert db.one('SELECT * FROM backtests WHERE id=?',(result['id'],))
    assert result['result']['status']=='insufficient_event_history'

def test_revised_story_is_not_marked_as_known_before_revision(db):
    from backend.providers import Providers
    provider=Providers(db,CFG)
    row={'id':'revision','headline':'Initial earnings report','summary':'Initial figures','symbols':['AAPL'],'created_at':AT.isoformat()}
    provider.store_news(row)
    with db.tx() as c:c.execute("UPDATE news SET received_at=? WHERE id='revision'",((AT-timedelta(days=1)).isoformat(),))
    provider.store_news(row)
    assert db.one("SELECT received_at FROM news WHERE id='revision'")['received_at']==(AT-timedelta(days=1)).isoformat()
    provider.store_news(row|{'summary':'Corrected earnings figures'})
    assert db.one("SELECT received_at FROM news WHERE id='revision'")['received_at']!=(AT-timedelta(days=1)).isoformat()
