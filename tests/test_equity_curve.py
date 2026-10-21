from datetime import datetime,timedelta,timezone
from backend.config import units
from backend.db import uid,DB
from backend.equity_curve import slot_for,record_point,daily_points,window

AT=datetime(2026,10,21,13,30,3,tzinfo=timezone.utc)


def test_points_are_immutable_persistent_and_once_per_five_minutes(db):
    assert record_point(db,AT)
    with db.tx() as c:c.execute("UPDATE portfolios SET cash_u=cash_u+1000000 WHERE id='fund'")
    assert not record_point(db,AT+timedelta(minutes=2))
    assert record_point(db,AT+timedelta(minutes=5))
    rows=daily_points(DB(db.path),AT+timedelta(minutes=6))
    assert [r['created_at'] for r in rows]==['2026-10-21T13:30:00+00:00','2026-10-21T13:35:00+00:00']
    assert [r['equity_u'] for r in rows]==[units(3000),units(3001)]
    assert rows[0]['observed_at']==AT.isoformat()


def test_window_dst_and_no_points_before_after_or_on_previous_day(db):
    assert slot_for(datetime(2026,10,21,13,29,tzinfo=timezone.utc)) is None
    assert slot_for(datetime(2026,10,21,16,30,1,tzinfo=timezone.utc)) is None
    assert window(datetime(2026,10,25,15,tzinfo=timezone.utc))[0].hour==14
    record_point(db,AT)
    assert daily_points(db,AT+timedelta(days=1))==[]
    assert not record_point(db,AT+timedelta(hours=4))


def test_complete_legacy_points_backfill_first_observation_only_not_missing_slots(db):
    with db.tx() as c:
        for minutes,value,complete in [(0,3000,1),(1,3100,1),(5,3002,0),(10,3003,1)]:
            c.execute('INSERT INTO equity VALUES(?,?,?,?,?,?,?)',(uid(),'fund',units(value),units(value),0,complete,(AT+timedelta(minutes=minutes)).isoformat()))
    rows=daily_points(db,AT+timedelta(minutes=12))
    assert [r['equity_u'] for r in rows]==[units(3000),units(3003)]
    assert len(daily_points(db,AT+timedelta(minutes=12)))==2


def test_entry_cost_fallback_never_creates_a_price_observation_but_verified_marks_can(db):
    with db.tx() as c:
        c.execute("INSERT INTO positions VALUES(?,?,?,?,?,?,?,?,?,?,?)",('curve-position','fund',76,'AAPL','1','100',units(100),'1.1','98',None,AT.isoformat()))
    assert not record_point(db,AT)
    db.set('valuation-mark-curve-position',{'bid':'101','fx':'1.1','market_at':'2026-10-21T13:14:00+00:00'})
    assert record_point(db,AT)
    row=daily_points(db,AT)[0]
    assert row['valuation_complete']==0 and row['sample_source']=='last_verified_quotes'
    assert db.one('SELECT COUNT(*) n FROM orders')['n']==0
