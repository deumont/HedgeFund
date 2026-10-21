from datetime import timedelta
import json
import pytest
from backend.config import Settings
from backend.db import dumps
from backend.daily_target import POLICY,progress,record_search,candidates
from backend.signals import SignalEngine
from backend.ledger import Ledger
from backend.worker import Worker
from conftest import AT


def enable(db):db.set('daily_entry_policy',{**POLICY,'effective_from':'2026-10-20'})


@pytest.fixture(autouse=True)
def dated_fills(monkeypatch):
    monkeypatch.setattr('backend.ledger.now',lambda:AT.isoformat())


def test_target_counts_actual_new_fills_not_pending_orders_or_carry(db):
    enable(db)
    assert progress(db,76,at=AT)['new_positions']==0
    ledger=Ledger(db)
    order=ledger.submit(76,'AAPL','buy',1,'daily-first',stop_usd=98,reason='Fixture validated strategy signal',at=AT)
    assert progress(db,76,at=AT)['status']=='searching'
    ledger.fill(order['id'],AT)
    assert progress(db,76,at=AT)['status']=='met'
    tomorrow=AT+timedelta(days=1)
    with db.tx() as c:c.execute('INSERT INTO sessions VALUES(?,?,?,?)',('2026-10-21','2026-10-21T09:30:00-04:00','2026-10-21T16:00:00-04:00','fixture'))
    assert progress(db,76,at=tomorrow)['new_positions']==0
    assert progress(db,1,at=AT)['status']=='not_applicable'


def test_addition_does_not_count_as_new_position(db):
    enable(db)
    ledger=Ledger(db);order=ledger.submit(76,'AAPL','buy',1,'opening',stop_usd=98,reason='Fixture validated strategy signal',at=AT);ledger.fill(order['id'],AT)
    proof=db.one('SELECT s.id,s.observations FROM signal_decisions s JOIN order_signals os ON os.signal_id=s.id WHERE os.order_id=?',(order['id'],))
    with db.tx() as c:c.execute('UPDATE signal_decisions SET observations=? WHERE id=?',(dumps({**json.loads(proof['observations']),'position_id':'existing-position'}),proof['id']))
    assert progress(db,76,at=AT)['new_positions']==0


def test_unmet_target_records_search_and_requires_manager_exception_after_close(db):
    enable(db);record_search(db,76,AT,['AAPL','SPY'],0)
    status=progress(db,76,at=AT+timedelta(hours=1))
    assert status['exception_requires_manager_review'] and status['documented_search']
    assert status['search']['symbols_checked']==2
    assert progress(db,76,at=AT)['status']=='searching'
    assert not progress(db,76,at=AT+timedelta(days=4))['applies']
    record_search(db,76,AT+timedelta(days=1),['MSFT'],0)
    assert progress(db,76,at=AT)['search']['symbols_checked']==2


def test_daily_search_finds_other_stock_with_own_signal(db):
    enable(db)
    with db.tx() as c:
        c.execute('UPDATE agents SET paused=1 WHERE id!=76')
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?)',('ZZZ',1,'us_equity','NASDAQ',AT.isoformat()))
    db.set('agent-stock-76','ZZZ');db.set('market_symbols',['ZZZ','AAPL'])
    worker=Worker(db,Settings(_env_file=None))
    worker.monitor_signals(AT)
    fills=db.all("SELECT * FROM fills WHERE agent_id=76 AND side='buy'")
    assert len(fills)==1 and fills[0]['symbol']=='AAPL'
    assert progress(db,76,at=AT)['status']=='met'
    worker.monitor_signals(AT)
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==1


def test_daily_target_never_authorizes_a_trade_without_valid_entry(db):
    enable(db)
    with db.tx() as c:
        c.execute('UPDATE agents SET paused=1 WHERE id!=76')
        c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
    Worker(db,Settings(_env_file=None)).monitor_signals(AT)
    assert not db.all('SELECT * FROM orders') and not db.all('SELECT * FROM fills')
    assert progress(db,76,at=AT)['documented_search']


def test_gap_outside_decision_window_does_not_disable_valid_current_signal(db):
    with db.tx() as c:c.execute("DELETE FROM bars WHERE symbol='AAPL' AND time=?",((AT-timedelta(minutes=120)).isoformat(),))
    assert SignalEngine(db).evaluate(76,'AAPL',at=AT).valid
    with db.tx() as c:c.execute("DELETE FROM bars WHERE symbol='AAPL' AND time=?",((AT-timedelta(minutes=45)).isoformat(),))
    decision=SignalEngine(db).evaluate(76,'AAPL',at=AT)
    assert not decision.valid and 'Datenlücke' in decision.reason
