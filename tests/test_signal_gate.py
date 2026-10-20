"""Regression tests for HOLD by default and a mandatory data/strategy gate at execution."""
from datetime import timedelta,datetime,timezone
from types import SimpleNamespace
import json
import pytest
from backend.signals import SignalEngine
from backend.ledger import Ledger,RiskError
from backend.db import dumps,uid
from backend.worker import Worker
from backend.config import Settings
from conftest import AT


def spec_change(db,agent=76,**changes):
    row=db.one('SELECT * FROM strategies WHERE agent_id=? ORDER BY version DESC LIMIT 1',(agent,))
    spec=json.loads(row['spec'])|changes
    with db.tx() as c:
        c.execute('UPDATE strategies SET spec=? WHERE id=?',(dumps(spec),row['id']))


def submit(db,key='test'):
    return Ledger(db).submit(76,'AAPL','buy',1,key,stop_usd=98,reason='Model says BUY',at=AT)


def test_no_entry_condition_means_no_order_even_if_model_says_buy(db):
    with db.tx() as c:
        c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
    decision=SignalEngine(db).evaluate(76,'AAPL',at=AT)
    assert not decision.valid
    assert 'Einstiegsbedingung nicht erfüllt' in decision.reason
    with pytest.raises(RiskError):
        submit(db)
    assert db.one('SELECT COUNT(*) n FROM orders')['n']==0
    assert db.one("SELECT decision FROM signal_decisions WHERE agent_id=76")['decision']=='HOLD'


def test_valid_strategy_signal_required_and_linked_to_order(db):
    decision=SignalEngine(db).evaluate(76,'AAPL',at=AT)
    assert decision.valid
    order=submit(db)
    assert db.one('SELECT * FROM order_signals WHERE order_id=?',(order['id'],))
    assert Ledger(db).fill(order['id'],AT)


@pytest.mark.parametrize('minutes',[1,5,10,14])
def test_sub_15_minute_strategies_never_trade(db,minutes):
    spec_change(db,timeframe_minutes=minutes)
    with pytest.raises(RiskError):
        submit(db)
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==0


@pytest.mark.parametrize('changes',[
    {'requires_realtime':True}, {'max_data_delay_minutes':0}, {'requires_full_market':True}
])
def test_unsuitable_delayed_or_partial_data_never_trade(db,changes):
    spec_change(db,**changes)
    with pytest.raises(RiskError):
        submit(db)
    assert db.one('SELECT COUNT(*) n FROM orders')['n']==0


def test_recent_strategy_bar_does_not_make_delayed_quote_executable(db):
    with db.tx() as c:
        c.execute('UPDATE quotes SET market_at=?',((AT-timedelta(minutes=15)).isoformat(),))
    assert SignalEngine(db).evaluate(76,'AAPL',at=AT).valid
    with pytest.raises(RiskError,match='Veraltete'):
        submit(db)
    assert db.one('SELECT COUNT(*) n FROM orders')['n']==0


def test_missing_bars_and_import_only_data_hold(db):
    with db.tx() as c:
        c.execute("UPDATE bars SET source='Import: permitted research dataset'")
    with pytest.raises(RiskError,match='Keine geeigneten'):
        submit(db)


@pytest.mark.parametrize('mode',['stale','future','zero_volume','invalid_ohlc'])
def test_bad_market_data_never_generates_executable_signal(db,mode):
    with db.tx() as c:
        if mode=='stale':
            c.execute('DELETE FROM bars WHERE time>?',((AT-timedelta(hours=2)).isoformat(),))
        elif mode=='future':
            c.execute('UPDATE bars SET time=? WHERE symbol=? AND time=(SELECT MAX(time) FROM bars WHERE symbol=?)',((AT+timedelta(hours=1)).isoformat(),'AAPL','AAPL'))
        elif mode=='zero_volume':
            c.execute('UPDATE bars SET volume=0')
        else:
            c.execute("UPDATE bars SET high='1'")
    with pytest.raises(RiskError):
        submit(db)
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==0


def test_signal_rechecked_at_fill_and_reservation_released(db):
    order=submit(db)
    with db.tx() as c:
        c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
    assert Ledger(db).fill(order['id'],AT) is None
    assert db.one("SELECT reserved_u FROM portfolios WHERE id='fund'")['reserved_u']==0
    assert db.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status']=='cancelled'


def test_changed_strategy_invalidates_existing_signal(db):
    order=submit(db)
    row=db.one('SELECT * FROM strategies WHERE agent_id=76')
    with db.tx() as c:
        c.execute('INSERT INTO strategies VALUES(?,?,?,?,?,?,?)',(uid(),76,2,row['spec'],'new version','candidate',AT.isoformat()))
    assert Ledger(db).fill(order['id'],AT) is None
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==0


def test_no_forced_trade_for_weeks_of_inactivity(db):
    with db.tx() as c:
        c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
    worker=Worker(db,Settings(_env_file=None,openai_api_key='not-a-real-key'))
    # Many monitoring cycles and an old activity date create no trade or model trade task.
    with db.tx() as c:
        c.execute('UPDATE agents SET last_active=?',((AT-timedelta(weeks=8)).isoformat(),))
    for minute in range(0,120,10):
        worker.monitor_signals(AT+timedelta(minutes=minute))
    assert db.one('SELECT COUNT(*) n FROM orders')['n']==0
    assert db.one('SELECT COUNT(*) n FROM jobs')['n']==0
    assert db.one("SELECT COUNT(*) n FROM signal_decisions WHERE decision='HOLD'")['n']>0


def test_same_data_independent_agent_strategies(db):
    spec_change(db,77,kind='mean_reversion')
    assert SignalEngine(db).evaluate(76,'AAPL',at=AT).valid
    assert not SignalEngine(db).evaluate(77,'AAPL',at=AT).valid


def test_open_position_does_not_force_repeated_entries(db):
    order=submit(db)
    Ledger(db).fill(order['id'],AT)
    with pytest.raises(RiskError,match='Bestehende Position'):
        submit(db,'second')


def test_missing_proof_cannot_bypass_gate_at_execution(db):
    order=submit(db)
    with db.tx() as c:
        c.execute('DELETE FROM order_signals WHERE order_id=?',(order['id'],))
    assert Ledger(db).fill(order['id'],AT) is None
    assert db.one('SELECT COUNT(*) n FROM fills')['n']==0


def test_strategy_cannot_be_rewritten_to_force_a_trade_on_old_data(db):
    with db.tx() as c:
        c.execute('UPDATE strategies SET created_at=? WHERE agent_id=76',(AT.isoformat(),))
    with pytest.raises(RiskError,match='Neue Strategie'):
        submit(db)


def test_intraday_missing_candle_is_unsuitable_data(db):
    with db.tx() as c:
        c.execute('DELETE FROM bars WHERE symbol=? AND time=?',('AAPL',(AT-timedelta(minutes=60)).isoformat()))
    with pytest.raises(RiskError,match='Datenlücke'):
        submit(db)


@pytest.mark.asyncio
async def test_clean_worker_stop_can_restart_with_zero_pid_sentinel(db,tmp_path):
    db.set('worker_identity',{'pid':0,'created':0})
    worker=Worker(db,Settings(_env_file=None,openai_api_key='',alpaca_paper_api_key='',alpaca_paper_secret_key=''))
    worker.backup_dir=tmp_path/'backups'
    worker.stop.set()
    await worker.run()
    assert db.get('worker_identity')['pid']==0


def test_forming_or_not_yet_available_candle_cannot_create_entry(db):
    with db.tx() as c:
        c.execute("UPDATE bars SET open='100',high='101',low='99',close='100'")
        c.execute('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',('AAPL',(AT-timedelta(minutes=15)).isoformat(),
                    '15Min','100','201','99','200',10000,'Alpaca IEX','raw'))
    assert not SignalEngine(db).evaluate(76,'AAPL',at=AT).valid
    with pytest.raises(RiskError):
        submit(db)


def test_one_minute_dataset_does_not_satisfy_15_minute_strategy(db):
    with db.tx() as c:
        c.execute("UPDATE bars SET timeframe='1Min'")
    with pytest.raises(RiskError,match='Keine geeigneten'):
        submit(db)


def test_policy_migration_preserves_agents_roles_ledgers_and_memory(db):
    from backend.catalog import seed
    with db.tx() as c:
        c.execute("UPDATE agents SET department='demo',paused=1 WHERE id=1")
        c.execute("UPDATE agents SET department='research' WHERE id=51")
        c.execute('INSERT INTO memories VALUES(?,?,?,?,?,?)',(uid(),1,'test','Preserve this memory','[]',AT.isoformat()))
        c.execute("UPDATE portfolios SET cash_u=cash_u-1 WHERE id='fund'")
        old=json.loads(c.execute('SELECT spec FROM strategies WHERE agent_id=1').fetchone()[0])
        old.pop('timeframe_minutes')
        c.execute('UPDATE strategies SET spec=? WHERE agent_id=1',(dumps(old),))
    seed(db)
    assert db.one('SELECT department,paused FROM agents WHERE id=1')=={'department':'demo','paused':1}
    assert db.one('SELECT COUNT(*) n FROM agents')['n']==100
    assert db.one('SELECT COUNT(*) n FROM memories')['n']==1
    assert db.one("SELECT cash_u FROM portfolios WHERE id='fund'")['cash_u']==3_000_000_000-1
    assert json.loads(db.one('SELECT spec FROM strategies WHERE agent_id=1')['spec'])['timeframe_minutes']>=15
