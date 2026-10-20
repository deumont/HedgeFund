import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from backend.execution import plan_order
from backend.ledger import Ledger,RiskError
from backend.providers import Providers
from backend.backtest import simulate,validate_spec
from backend.db import dumps
from conftest import AT


def test_strategy_sizes_can_exceed_old_caps_but_preserve_cash(db):
    db.set('paper_sizing_mode','strategy')
    db.set('fund_cash_limits',{'max_position_eur':240,'max_exposure_eur':1800})
    spec=json.loads(db.one('SELECT spec FROM strategies WHERE agent_id=76')['spec'])
    spec['position_pct']=.5
    with db.tx() as c:
        c.execute('UPDATE strategies SET spec=? WHERE agent_id=76',(dumps(spec),))
    plan=plan_order(db,76,'AAPL','buy',AT)
    order=Ledger(db).submit(76,'AAPL','buy',client_id='strategy-size',reason='strategy test',at=AT,**plan)
    assert 240e6<order['reserved_u']<1500e6
    fill=Ledger(db).fill(order['id'],AT)
    assert fill
    assert db.one("SELECT cash_u FROM portfolios WHERE id='fund'")['cash_u']>=0


def test_experimental_mode_still_rejects_missing_signals_and_stale_quotes(db):
    db.set('paper_sizing_mode','strategy')
    with db.tx() as c:
        c.execute('UPDATE quotes SET market_at=?',((AT-timedelta(minutes=16)).isoformat(),))
    with pytest.raises(RiskError,match='Veraltete'):
        plan_order(db,76,'AAPL','buy',AT)
    with db.tx() as c:
        c.execute("DELETE FROM bars")
    with pytest.raises(RiskError):
        Ledger(db).submit(76,'AAPL','buy',10,'no-signal',stop_usd=98,reason='test',at=AT)
    assert not db.all('SELECT * FROM fills')


@pytest.mark.parametrize('allocation',[0,-1,1.1,float('nan'),True])
def test_bad_strategy_allocation_rejected(db,allocation):
    spec=json.loads(db.one('SELECT spec FROM strategies WHERE agent_id=76')['spec'])
    with pytest.raises(ValueError):
        validate_spec({**spec,'position_pct':allocation})


def test_partial_allocation_backtest_keeps_uninvested_cash():
    bars=[{'time':str(i).zfill(3),'open':100+i,'low':100+i,'close':100+i} for i in range(60)]
    spec=dict(kind='momentum',lookback=2,holding_bars=3,threshold=0,stop_pct=.02)
    full=simulate(bars,spec)
    partial=simulate(bars,{**spec,'position_pct':.25})
    assert 3000<partial['final_equity']<full['final_equity']


def test_news_off_watchlist_shared_deduplicated_and_corrected(db):
    provider=Providers(db,SimpleNamespace())
    row={'id':123,'headline':'Original','symbols':['OFFWATCH'],'created_at':AT.isoformat()}
    provider.store_news(row)
    provider.store_news(row)
    provider.store_news({**row,'headline':'Corrected'})
    assert db.one('SELECT COUNT(*) n FROM news')['n']==1
    assert db.one('SELECT headline FROM news')['headline']=='Corrected'
    assert db.one("SELECT COUNT(*) n FROM events WHERE kind='news_received'")['n']==1
    from backend.intelligence import agent_context
    for aid in (1,51,76,100):
        assert agent_context(db,aid)['news'][0]['headline']=='Corrected'
