from datetime import timedelta
import pytest
from backend.config import units
from backend.ledger import Ledger,RiskError
from backend.db import uid
from conftest import AT

CAPS=dict(max_position_eur=240,max_exposure_eur=1800,max_daily_loss_eur=60,
          max_drawdown_eur=240,max_loss_per_position_eur=15)


def grown_fund(db,equity=6000):
    db.set('fund_cash_limits',CAPS)
    with db.tx() as c:
        c.execute("UPDATE portfolios SET initial_u=?,cash_u=? WHERE id='fund'",(units(6000),units(equity)))
        c.execute("DELETE FROM equity WHERE portfolio_id='fund'")
        c.execute('INSERT INTO equity VALUES(?,?,?,?,?,?,?)',(uid(),'fund',units(6000),units(6000),0,1,(AT-timedelta(hours=1)).isoformat()))


def test_position_cap_does_not_increase_with_fund_equity(db):
    grown_fund(db)
    with pytest.raises(RiskError,match='Positionsgröße'):
        Ledger(db).submit(76,'AAPL','buy',3,'cap',stop_usd=98,reason='test',at=AT)


def test_stop_risk_cap_does_not_increase_with_equity(db):
    grown_fund(db)
    with pytest.raises(RiskError,match='Stop-Risiko'):
        Ledger(db).submit(76,'AAPL','buy',2,'risk-cap',stop_usd=90,reason='test',at=AT)


@pytest.mark.parametrize('value,expected',[(5940,'Tagesverlustlimit'),(5759,'Tagesverlustlimit')])
def test_fixed_daily_loss_bound(db,value,expected):
    grown_fund(db,value)
    with pytest.raises(RiskError,match=expected):
        Ledger(db).submit(76,'AAPL','buy',1,'loss',stop_usd=98,reason='test',at=AT)


def test_fixed_drawdown_bound_independent_of_daily_baseline(db):
    grown_fund(db,5759)
    with db.tx() as c:
        c.execute('UPDATE equity SET created_at=?',((AT-timedelta(days=1)).isoformat(),))
        c.execute('INSERT INTO equity VALUES(?,?,?,?,?,?,?)',(uid(),'fund',units(5759),units(5759),0,1,(AT-timedelta(hours=1)).isoformat()))
    with pytest.raises(RiskError,match='Drawdown'):
        Ledger(db).submit(76,'AAPL','buy',1,'dd',stop_usd=98,reason='test',at=AT)


def test_exposure_cap_includes_other_agents_reservations(db):
    grown_fund(db)
    with db.tx() as c:
        c.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid(),'other','fund',77,'SPY','buy','19','limit','99','98',None,'pending',units(1750),'test','internal',AT.isoformat(),AT.isoformat()))
        c.execute("UPDATE portfolios SET reserved_u=? WHERE id='fund'",(units(1750),))
    with pytest.raises(RiskError,match='Gesamtexposure'):
        Ledger(db).submit(76,'AAPL','buy',1,'exposure',stop_usd=98,reason='test',at=AT)
