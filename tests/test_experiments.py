import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from backend.db import DB,dumps
from backend.catalog import seed
from backend.experiments import initial_strategy,draw,prepare_strategy
from backend.config import Settings
from backend.worker import Worker
from backend.ledger import Ledger
from backend.backtest import simulate,signal
from backend.intelligence import AI
from conftest import AT

CFG=Settings(_env_file=None,openai_api_key='',watchlist='AAPL')

def fixture_spec(selected,stamp):
    # Fixture seeds cover both outcomes; production never searches for a winning seed.
    for i in range(1000):
        spec=initial_strategy(51)|{'seed':f'fixture-seed-{i}'}
        if draw(spec,'AAPL',stamp)['selected']==selected:return spec
    raise AssertionError('Fixture seed unavailable')

def setup(db,selected=True):
    stamp=(AT-timedelta(minutes=30)).isoformat();spec=fixture_spec(selected,stamp)
    with db.tx() as c:
        c.execute("UPDATE agent_mandates SET approach='experimental' WHERE agent_id=51")
        c.execute('UPDATE agents SET paused=1 WHERE id!=51')
        c.execute('UPDATE strategies SET spec=?,created_at=? WHERE agent_id=51',(dumps(spec),(AT-timedelta(days=1)).isoformat()))
        c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
    db.set('agent-stock-51','AAPL')
    return Worker(db,CFG),spec

def test_experimental_cohort_preserves_50_news_and_50_25_25(tmp_path):
    d=DB(tmp_path/'experiment.sqlite');d.init();seed(d);seed(d)
    assert {r['approach']:r['n'] for r in d.all('SELECT approach,count(*) n FROM agent_mandates GROUP BY approach')}=={'news':50,'technical':45,'experimental':5}
    assert {r['department']:r['n'] for r in d.all('SELECT department,count(*) n FROM agents GROUP BY department')}=={'research':50,'demo':25,'fund':25}
    assert [r['agent_id'] for r in d.all("SELECT agent_id FROM agent_mandates WHERE approach='experimental' ORDER BY agent_id")]==list(range(51,56))

@pytest.mark.parametrize('bad',[None,'no_selection','stale','gap','feed','paused','capital','realtime'])
def test_chance_entry_uses_real_ledger_and_never_bypasses_data_or_capital(db,bad):
    worker,spec=setup(db,bad!='no_selection')
    with db.tx() as c:
        if bad=='stale':c.execute('UPDATE quotes SET market_at=?',((AT-timedelta(minutes=15)).isoformat(),))
        if bad=='gap':c.execute('DELETE FROM bars WHERE time=?',((AT-timedelta(minutes=60)).isoformat(),))
        if bad=='paused':c.execute('UPDATE agents SET paused=1 WHERE id=51')
        if bad=='capital':c.execute("UPDATE portfolios SET reserved_u=cash_u WHERE id='demo-051'")
        if bad=='realtime':c.execute('UPDATE strategies SET spec=? WHERE agent_id=51',(dumps(spec|{'requires_realtime':True}),))
    if bad=='feed':db.integration('market_stream','error','Fixture disconnection')
    worker.monitor_signals(AT);worker.monitor_signals(AT+timedelta(seconds=1))
    fills=db.all('SELECT * FROM fills')
    assert len(fills)==(1 if bad is None else 0)
    if fills:
        assert fills[0]['source']=='Interne Simulation'
        proof=json.loads(db.one('SELECT s.observations FROM signal_decisions s JOIN order_signals o ON o.signal_id=s.id')['observations'])
        assert proof['experiment']['selected'] and proof['indicators']=={}
        assert 'Zufall' in proof['entry_basis']
        assert Ledger(db).portfolio('demo-051')['positions'][0]['value_eur']<750
        assert Ledger(db).reconcile()

def test_draw_is_stable_across_polls_and_timezone_representations():
    spec=initial_strategy(51);stamp=AT.isoformat()
    assert draw(spec,'AAPL',stamp)==draw(spec,'AAPL',stamp)
    alternate=AT.astimezone(__import__('datetime').timezone(timedelta(hours=2))).isoformat()
    assert draw(spec,'AAPL',stamp)['draw']==draw(spec,'AAPL',alternate)['draw']
    assert draw(spec,'MSFT',stamp)['draw']!=draw(spec,'AAPL',stamp)['draw']
    assert signal([100]*5,spec) is False

def test_random_backtest_honors_delayed_data_and_has_no_future_price_dependency():
    start=AT-timedelta(days=1)
    data=[dict(symbol='AAPL',time=(start+timedelta(minutes=15*i)).isoformat(),open='100',high='100',low='100',close='100') for i in range(40)]
    spec=fixture_spec(True,data[2]['time'])
    result=simulate(data,spec)
    assert all(p['equity']==3000 for p in result['equity'][:4])  # first signal bar 2; execution not before bar 4
    assert result['equity'][4]['equity']<3000  # actual friction, no invented profit
    assert result==simulate(data,spec)
    changed=[dict(b) for b in data];changed[-1]['close']='101'
    assert result['equity'][:-1]==simulate(changed,spec)['equity'][:-1]

@pytest.mark.asyncio
async def test_agent_can_adapt_experiment_but_cannot_select_new_seed(db,research_morning,monkeypatch):
    from backend.experiments import configure
    configure(db);prepare_strategy(db,51)
    spec=json.loads(db.one('SELECT spec FROM strategies WHERE agent_id=51 ORDER BY version DESC LIMIT 1')['spec'])
    proposal=spec|{'holding_bars':8}
    async def reply(*a,**kw):return SimpleNamespace(output=[],output_text=dumps(dict(action='research',symbol='AAPL',qty='0',
        stop_usd=None,take_usd=None,hypothesis='Compare chance-entry horizons.',conclusion='Paper experiment; no forecast.',
        evidence_ids=[],rejected_alternatives=['Claiming a technical edge'],memory='Compare net results.',proposed_strategy=proposal)))
    monkeypatch.setattr(AI,'call',reply)
    await AI(db,Settings(_env_file=None,openai_api_key='fixture')).analyze(51)
    assert json.loads(db.one('SELECT spec FROM strategies WHERE agent_id=51 ORDER BY version DESC LIMIT 1')['spec'])['holding_bars']==8
    before=db.one('SELECT COUNT(*) n FROM analyses')['n']
    proposal['seed']='different-seed-forbidden'
    with pytest.raises(ValueError,match='Seed'):await AI(db,Settings(_env_file=None,openai_api_key='fixture')).analyze(51)
    assert db.one('SELECT COUNT(*) n FROM analyses')['n']==before

@pytest.mark.asyncio
async def test_manager_receives_experimental_approach_without_invented_performance(db,monkeypatch):
    from backend.reporting import review_agents
    from backend.experiments import configure
    configure(db)
    async def reply(self,kind,messages,**kw):
        profile=json.loads(messages[0]['content'])['agents'][0]['profile']
        assert profile['approach']=='experimental' and 'Zufall' in profile['mandate']
        return SimpleNamespace(output_text=dumps({'ratings':[{'agent_id':51,'score':5,'reason':'Experiment erlaubt; noch keine Handelsstichprobe.'}]}))
    monkeypatch.setattr(AI,'call',reply)
    await review_agents(db,Settings(_env_file=None,openai_api_key='fixture'),[51])
    assert db.one('SELECT score FROM manager_reviews WHERE agent_id=51')['score']==5
    assert not db.all('SELECT * FROM orders')
