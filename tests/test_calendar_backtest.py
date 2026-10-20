from datetime import datetime,timezone
import math
import pytest
from backend.calendar import phase
from backend.backtest import simulate,run_backtest
from backend.db import uid,dumps
from backend.config import now


@pytest.mark.parametrize('day,expected',[('2026-03-06',15),('2026-03-09',14),('2026-03-30',15),('2026-10-26',14),('2026-11-02',15)])
def test_dst_us_europe(db,day,expected):
    from zoneinfo import ZoneInfo
    ny=ZoneInfo('America/New_York')
    with db.tx() as c:
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(day,datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ny).isoformat(),datetime.fromisoformat(day+'T16:00:00').replace(tzinfo=ny).isoformat(),'Alpaca fixture'))
    result=phase(db,datetime.fromisoformat(day+'T08:00:00+00:00'))
    assert datetime.fromisoformat(result['opens_at']).hour==expected


@pytest.mark.parametrize('stamp,expected',[('2026-10-20T13:29:59+00:00','preparing'),('2026-10-20T13:30:00+00:00','trading'),('2026-10-20T16:24:59+00:00','trading'),('2026-10-20T16:25:00+00:00','liquidating'),('2026-10-20T16:30:00+00:00','review'),('2026-10-20T17:00:00+00:00','stopped')])
def test_personal_cutoffs(db,stamp,expected):
    assert phase(db,datetime.fromisoformat(stamp))['phase']==expected


def test_holiday_and_short_session_fail_closed(db):
    db.set('calendar_coverage',{'start':'2026-11-01','end':'2026-12-01'})
    assert phase(db,datetime.fromisoformat('2026-11-26T15:00:00+00:00'))['phase']=='closed'
    assert phase(db,datetime.fromisoformat('2026-12-25T15:00:00+00:00'))['phase']=='calendar_missing'
    with db.tx() as c:
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',('2026-11-27','2026-11-27T09:30:00-05:00','2026-11-27T13:00:00-05:00','Alpaca fixture'))
    assert phase(db,datetime.fromisoformat('2026-11-27T17:30:00+00:00'))['phase']=='review'
    assert phase(db,datetime.fromisoformat('2026-11-27T18:00:00+00:00'))['phase']=='stopped'
    with pytest.raises(ValueError):
        phase(db,datetime(2026,10,20,15))


def bars(n=250):
    from datetime import timedelta
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    return [dict(symbol='SPY',time=(start+timedelta(days=i)).isoformat(),timeframe='1Day',
                 open=str(100+i*.3),high=str(102+i*.3),low=str(99+i*.3),close=str(101+i*.3),
                 volume=10000,source='TEST fixture',adjustment='all') for i in range(n)]


SPEC={'kind':'momentum','lookback':10,'holding_bars':4,'threshold':.01,'stop_pct':.05}


def test_backtest_reproducible_costs_and_no_lookahead():
    data=bars()
    result=simulate(data,SPEC)
    assert result==simulate(data,SPEC)
    assert result['final_equity']<simulate(data,SPEC,cost_bps=0)['final_equity']
    changed=bars()
    changed[-1]['close']='10000'
    assert result['equity'][:-1]==simulate(changed,SPEC)['equity'][:-1]
    assert all(t['time']>data[SPEC['lookback']]['time'] for t in result['trades'])


def test_store_oos_and_hash(db,research_morning):
    with db.tx() as c:
        c.execute("UPDATE strategies SET spec=? WHERE id='agent-001-v1'",(dumps(SPEC|{'timeframe_minutes':1440}),))
        for b in bars(400):
            c.execute('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(b.values()))
    one=run_backtest(db,1,'agent-001-v1','SPY')
    two=run_backtest(db,1,'agent-001-v1','SPY')
    assert one['data_hash']==two['data_hash']
    assert one['result']==two['result']
    assert one['result']['out_of_sample']['equity'][0]['time']==one['result']['split_date']


def test_unsafe_code_not_executed():
    with pytest.raises(ValueError):
        simulate(bars(),SPEC|{'kind':'__import__("os").system("x")'})
