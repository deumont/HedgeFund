from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import timedelta
import pytest
from backend.ledger import Ledger,RiskError
from backend.db import DB
from backend.config import units
from conftest import AT


def order(ledger,aid=76,key='first',**kwargs):
    at=kwargs.pop('at',AT)
    return ledger.submit(aid,'AAPL','buy','1',key,stop_usd='98',reason='Testentscheidung',at=at,**kwargs)


def test_seed_persistent_and_counts(db):
    assert db.one('SELECT COUNT(*) AS n FROM agents')['n']==100
    assert {x['department']:x['n'] for x in db.all('SELECT department,COUNT(*) n FROM agents GROUP BY department')}=={'research':50,'demo':25,'fund':25}
    assert db.one("SELECT COUNT(*) n FROM portfolios WHERE kind='demo'")['n']==25
    assert db.one("SELECT cash_u FROM portfolios WHERE id='fund'")['cash_u']==units(3000)
    assert len({x['mandate'] for x in db.all('SELECT mandate FROM agents')})==100
    reopened=DB(db.path)
    assert reopened.one('SELECT COUNT(*) n FROM strategies')['n']==100


def test_fill_idempotent_conserves_money(db):
    l=Ledger(db)
    o=order(l)
    assert order(l)['id']==o['id']
    f=l.fill(o['id'],AT)
    assert f['source']=='Interne Simulation'
    assert l.fill(o['id'],AT) is None
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==1
    p=db.one("SELECT * FROM portfolios WHERE id='fund'")
    assert p['cash_u']==units(3000)+f['cash_delta_u']
    assert p['reserved_u']==0
    db.set('kill_switch',True)
    sell=l.submit(76,'AAPL','sell',1,'close',reason='Schließen',at=AT)
    sf=l.fill(sell['id'],AT)
    assert sf['realized_u']<0  # spread + slippage + costs
    assert db.one('SELECT COUNT(*) n FROM positions')['n']==0
    assert l.reconcile()


def test_demo_separate(db):
    l=Ledger(db)
    o=order(l,51)
    l.fill(o['id'],AT)
    assert db.one("SELECT cash_u FROM portfolios WHERE id='fund'")['cash_u']==units(3000)
    assert db.one("SELECT cash_u FROM portfolios WHERE id='demo-052'")['cash_u']==units(3000)
    assert db.one("SELECT cash_u FROM portfolios WHERE id='demo-051'")['cash_u']<units(3000)


def test_concurrent_reservations_no_double_spend(db):
    l=Ledger(db)
    limits=db.get('risk_limits')
    limits.update(max_position_pct=1,max_agent_pct=1,max_exposure_pct=1,max_symbol_pct=1,max_correlated_pct=1,
                  max_loss_per_position_pct=1,max_agent_risk_pct=1,max_total_risk_pct=1)
    db.set('risk_limits',limits)
    def submit(aid):
        try:
            return l.submit(aid,'SPY','buy',20,str(aid),stop_usd=98,reason='test',at=AT)
        except RiskError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(submit,range(76,101)))
    assert sum(x is not None for x in results)==1
    p=db.one("SELECT * FROM portfolios WHERE id='fund'")
    assert 0<=p['reserved_u']<=p['cash_u']
    assert l.reconcile()


def test_cancel_returns_reservation(db):
    l=Ledger(db)
    o=order(l)
    l.cancel(o['id'])
    l.cancel(o['id'])
    assert db.one("SELECT reserved_u FROM portfolios WHERE id='fund'")['reserved_u']==0


@pytest.mark.parametrize('qty',['NaN','Infinity','-1','0','0.0000001'])
def test_invalid_quantity(db,qty):
    with pytest.raises(RiskError):
        Ledger(db).submit(76,'AAPL','buy',qty,'bad',stop_usd=98,at=AT)


def test_research_short_and_limits(db):
    l=Ledger(db)
    with pytest.raises(RiskError):
        order(l,1)
    with pytest.raises(RiskError):
        l.submit(76,'AAPL','sell',1,'short',at=AT)
    with pytest.raises(RiskError):
        l.submit(76,'AAPL','buy',30,'oversize',stop_usd=98,reason='x',at=AT)


def test_freshness_kill_and_missing_calendar(db):
    l=Ledger(db)
    with pytest.raises(RiskError):
        order(l,at=AT+timedelta(seconds=31))


def test_kill_between_reservation_and_fill(db):
    l=Ledger(db)
    o=order(l)
    db.set('kill_switch',True)
    assert l.fill(o['id'],AT) is None
    l.cancel(o['id'])
    with pytest.raises(RiskError):
        order(l,key='second')


def test_no_fill_through_limit(db):
    l=Ledger(db)
    o=order(l,order_type='limit',limit_usd=99)
    assert l.fill(o['id'],AT) is None
    assert db.one('SELECT status FROM orders WHERE id=?',(o['id'],))['status']=='pending'


def test_gaps_do_not_spend_other_cash(db):
    l=Ledger(db)
    o=order(l)
    with db.tx() as c:
        c.execute("UPDATE quotes SET bid='199.95',ask='200' WHERE symbol='AAPL'")
    assert l.fill(o['id'],AT) is None
    assert db.one("SELECT cash_u FROM portfolios WHERE id='fund'")['cash_u']==units(3000)


def test_fx_and_equity(db):
    l=Ledger(db)
    o=order(l)
    l.fill(o['id'],AT)
    with db.tx() as c:
        c.execute("UPDATE quotes SET bid='110',ask='110.05'")
        c.execute("UPDATE fx SET usd_per_eur='1.20'")
    db.set('kill_switch',True)
    sell=l.submit(76,'AAPL','sell',1,'sell',reason='test',at=AT)
    f=l.fill(sell['id'],AT)
    assert f['stock_pnl_u']>0
    assert f['fx_pnl_u']<0
    assert abs(f['realized_u']-f['stock_pnl_u']-f['fx_pnl_u'])<units(1)  # explicit costs


def test_restart_reconciles_and_detects_corruption(db,tmp_path):
    l=Ledger(db)
    o=order(l)
    assert Ledger(DB(db.path)).reconcile()
    backup=db.backup(tmp_path/'backup')
    assert Ledger(DB(backup)).reconcile()
    with db.tx() as c:
        c.execute("UPDATE portfolios SET cash_u=cash_u+1 WHERE id='fund'")
    assert not l.reconcile()
    assert db.get('kill_switch')
