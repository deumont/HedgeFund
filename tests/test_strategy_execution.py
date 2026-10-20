"""The running monitor must reach the real internal ledger, including without an LLM."""
import json
from datetime import timedelta
import pytest
from backend.config import Settings
from backend.worker import Worker
from backend.ledger import Ledger, RiskError
from backend.db import dumps
from conftest import AT


def trader(db):
    with db.tx() as c:
        c.execute('UPDATE agents SET paused=1 WHERE id!=76')
    db.set('engine_enabled', False)
    return Worker(db, Settings(_env_file=None, openai_api_key='', watchlist='AAPL'))


def test_monitor_executes_valid_signal_without_ai_or_budget(db):
    worker=trader(db)
    worker.monitor_signals(AT)
    fill=db.one('SELECT * FROM fills')
    assert fill and fill['side']=='buy' and fill['source']=='Interne Simulation'
    assert db.one('SELECT * FROM order_signals WHERE order_id=?',(fill['order_id'],))
    assert db.one('SELECT COUNT(*) n FROM jobs')['n']==0
    assert Ledger(db).reconcile()
    worker.monitor_signals(AT)
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==1
    assert db.one('SELECT COUNT(*) n FROM agents')['n']==100


@pytest.mark.parametrize('bad', ['no_signal','stale_quote','gap','realtime','missing_feed','paused','risk_revoked','disabled','kill','capital'])
def test_monitor_never_executes_when_gate_fails(db,bad):
    worker=trader(db)
    with db.tx() as c:
        if bad=='no_signal':
            c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
        elif bad=='stale_quote':
            c.execute('UPDATE quotes SET market_at=?',((AT-timedelta(minutes=15)).isoformat(),))
        elif bad=='gap':
            c.execute('DELETE FROM bars WHERE time=?',((AT-timedelta(minutes=60)).isoformat(),))
        elif bad=='realtime':
            row=c.execute('SELECT * FROM strategies WHERE agent_id=76').fetchone()
            c.execute('UPDATE strategies SET spec=? WHERE id=?',(dumps(json.loads(row['spec'])|{'requires_realtime':True}),row['id']))
        elif bad=='paused':
            c.execute('UPDATE agents SET paused=1 WHERE id=76')
        elif bad=='capital':
            c.execute("UPDATE portfolios SET reserved_u=cash_u WHERE id='fund'")
    if bad=='missing_feed':
        db.integration('market_stream','error','Test disconnection')
    if bad in ('risk_revoked','disabled','kill'):
        db.set({'risk_revoked':'risk_confirmed','disabled':'trading_enabled','kill':'kill_switch'}[bad],bad=='kill')
    worker.monitor_signals(AT)
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==0
    assert db.one('SELECT COUNT(*) n FROM orders')['n']==0


def test_monitor_closes_on_predefined_strategy_exit_without_model(db):
    worker=trader(db)
    worker.monitor_signals(AT)
    with db.tx() as c:
        c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
    worker.monitor_signals(AT)
    assert [r['side'] for r in db.all('SELECT * FROM fills ORDER BY created_at')]==['buy','sell']
    assert db.one('SELECT COUNT(*) n FROM positions')['n']==0
    assert Ledger(db).reconcile()


@pytest.mark.parametrize('change',['risk_revoked','exposure','stop_risk'])
def test_fill_rechecks_risk_after_reservation(db,change):
    ledger=Ledger(db)
    order=ledger.submit(76,'AAPL','buy',1,'reserve',stop_usd=98,reason='valid signal',at=AT)
    if change=='risk_revoked':
        db.set('risk_confirmed',False)
        assert ledger.fill(order['id'],AT) is None
    else:
        limits=db.get('risk_limits')
        limits['max_exposure_pct' if change=='exposure' else 'max_loss_per_position_pct']=0.00001
        db.set('risk_limits',limits)
        with pytest.raises(RiskError):
            ledger.fill(order['id'],AT)
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==0
