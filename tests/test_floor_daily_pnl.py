from datetime import datetime,timezone
from backend.agent_state import daily_stats,agent_states
from backend.db import uid
from backend.config import units

AT=datetime(2026,10,21,15,tzinfo=timezone.utc)


def fill(c,stamp,side='sell',pnl=0):
    oid=uid()
    c.execute('INSERT INTO orders(id,client_id,portfolio_id,agent_id,symbol,side,qty,order_type,status,reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
        (oid,oid,'fund',76,'AAPL',side,'1','market','filled','fixture',stamp,stamp))
    c.execute('INSERT INTO fills VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (uid(),oid,76,'fund','AAPL',side,'1','100','1.10',0,0,units(pnl),units(pnl),0,'fixture',stamp))


def old_closed(c):
    fill(c,'2026-10-19T14:00:00+00:00','buy')
    fill(c,'2026-10-20T14:00:00+00:00',pnl=40)


def test_floor_daily_values_exclude_previous_profit_and_include_live_mark(db):
    with db.tx() as c:
        old_closed(c)
        fill(c,'2026-10-21T14:00:00+00:00',pnl=-3)
        own=[{'created_at':'2026-10-21T13:00:00+00:00','unrealized_eur':2,'valuation_complete':True}]
        day=daily_stats(c,76,'fund',own,AT)
    assert day['realized_eur']==-3 and day['unrealized_eur']==2 and day['pnl_eur']==-1
    assert day['date']=='2026-10-21'
    assert agent_states(db,[76],AT)[76]['stats']['realized_eur']==37
    assert agent_states(db,[76],AT)[76]['day_stats']['realized_eur']==-3


def test_carry_position_uses_opening_mark_and_avoids_counting_prior_gain_twice(db):
    with db.tx() as c:
        old_closed(c)
        fill(c,'2026-10-20T15:00:00+00:00','buy')
        c.execute('INSERT INTO agent_equity VALUES(?,?,?,?,?,?,?,?)',(uid(),76,'fund',units(120),units(48),units(168),1,'2026-10-20T17:00:00+00:00'))
        fill(c,'2026-10-21T14:00:00+00:00',pnl=12)
        day=daily_stats(c,76,'fund',[],AT)
    assert day['realized_eur']==12 and day['unrealized_eur']==-8 and day['pnl_eur']==4


def test_missing_opening_mark_never_displays_lifetime_profit_as_daily(db):
    with db.tx() as c:
        fill(c,'2026-10-20T15:00:00+00:00','buy')
        own=[{'created_at':'2026-10-20T15:00:00+00:00','unrealized_eur':80,'valuation_complete':True}]
        day=daily_stats(c,76,'fund',own,AT)
    assert day['pnl_eur'] is None and day['unrealized_eur'] is None
    assert not day['opening_mark_known']


def test_berlin_day_rollover_and_25_hour_dst_day(db):
    with db.tx() as c:
        fill(c,'2026-10-24T21:59:59+00:00',pnl=100)
        fill(c,'2026-10-24T22:00:00+00:00',pnl=1)
        fill(c,'2026-10-25T22:59:59+00:00',pnl=2)
        fill(c,'2026-10-25T23:00:00+00:00',pnl=100)
        day=daily_stats(c,76,'fund',[],datetime(2026,10,25,22,59,59,tzinfo=timezone.utc))
    assert day['realized_eur']==3 and day['pnl_eur']==3
