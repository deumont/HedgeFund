from datetime import timedelta
import pytest
import backend.ledger as ledger
from backend.ledger import Ledger,RiskError,agent_exposure,snapshot
from backend.execution import plan_order
from backend.signals import SignalEngine
from backend.config import units
from conftest import AT


def test_aggregate_agent_cap_includes_other_symbols_and_reservations(db):
    db.set('paper_sizing_mode','strategy')
    book=Ledger(db)
    first=book.submit(76,'AAPL','buy',4,'one',stop_usd=98,reason='test',at=AT)
    with pytest.raises(RiskError,match='Kapitalbudget'):
        book.submit(76,'SPY','buy',5,'two',stop_usd=98,reason='test',at=AT)
    assert book.fill(first['id'],AT)
    with pytest.raises(RiskError,match='Kapitalbudget'):
        book.submit(76,'SPY','buy',5,'three',stop_usd=98,reason='test',at=AT)
    plan=plan_order(db,76,'SPY','buy',AT)
    remaining=book.submit(76,'SPY','buy',client_id='within',reason='test',at=AT,**plan)
    with db.tx() as c:
        state=snapshot(c,'fund',AT)
        assert agent_exposure(state['positions'],76)+remaining['reserved_u']<=units(state['equity_eur'])*.25


def test_fill_rechecks_reduced_agent_budget(db):
    db.set('paper_sizing_mode','strategy')
    book=Ledger(db)
    order=book.submit(76,'AAPL','buy',8,'pending',stop_usd=98,reason='test',at=AT)
    with db.tx() as c:
        # Another independent agent incurs a real loss between reservation and execution.
        c.execute("UPDATE portfolios SET cash_u=cash_u-? WHERE id='fund'",(units(200),))
    with pytest.raises(RiskError,match='Kapital-/Exposurelimit'):
        book.fill(order['id'],AT)
    assert not db.all('SELECT * FROM fills')


def test_legacy_oversized_position_has_valid_protective_partial_exit(db,monkeypatch):
    db.set('paper_sizing_mode','strategy')
    original=ledger.effective_limits
    # Simulate a position genuinely filled under the previously authorized policy.
    with monkeypatch.context() as m:
        m.setattr(ledger,'effective_limits',lambda c:{**original(c),'max_agent_pct':1.0})
        book=Ledger(db)
        order=book.submit(76,'AAPL','buy',15,'legacy',stop_usd=98,reason='test',at=AT)
        assert book.fill(order['id'],AT)
    assert SignalEngine(db).evaluate(76,'AAPL','sell',AT).valid
    exit=book.submit(76,'AAPL','sell',8,'reduce',reason='CEO 25 percent cap',at=AT)
    assert book.fill(exit['id'],AT)
    with db.tx() as c:
        state=snapshot(c,'fund',AT)
        assert agent_exposure(state['positions'],76)<=units(state['equity_eur'])*.25
    assert book.reconcile()


def test_cap_exit_still_cannot_fill_with_stale_data(db,monkeypatch):
    db.set('paper_sizing_mode','strategy')
    original=ledger.effective_limits
    with monkeypatch.context() as m:
        m.setattr(ledger,'effective_limits',lambda c:{**original(c),'max_agent_pct':1.0})
        book=Ledger(db)
        order=book.submit(76,'AAPL','buy',15,'legacy',stop_usd=98,reason='test',at=AT)
        book.fill(order['id'],AT)
    with db.tx() as c:
        c.execute('UPDATE quotes SET market_at=?',((AT-timedelta(minutes=16)).isoformat(),))
    with pytest.raises(RiskError,match='Veraltete'):
        book.submit(76,'AAPL','sell',8,'reduce',reason='cap',at=AT)
    assert len(db.all('SELECT * FROM fills'))==1
