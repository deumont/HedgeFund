"""Immutable five-minute display samples, separate from the trading/risk ledger."""
import asyncio
from datetime import datetime,time,timedelta,timezone
from .calendar import BERLIN
from .config import units
from .ledger import snapshot
from .providers import safe_error


def window(at):
    day=at.astimezone(BERLIN).date()
    return (datetime.combine(day,time(15,30),BERLIN).astimezone(timezone.utc),
            datetime.combine(day,time(18,30),BERLIN).astimezone(timezone.utc))


def slot_for(at):
    start,end=window(at)
    if not start<=at<=end:return None
    return start+timedelta(minutes=int((at-start).total_seconds()//300)*5)


def record_point(db,at=None):
    at=at or datetime.now(timezone.utc)
    slot=slot_for(at)
    if slot is None:return False
    with db.tx() as c:
        if c.execute('SELECT 1 FROM fund_curve_points WHERE slot_at=?',(slot.isoformat(),)).fetchone():return False
        state=snapshot(c,'fund',at)
        # Entry cost is not a price observation. Last verified marks can be
        # shown as estimates, but never become suitable execution prices.
        if any(p['valuation_source']=='entry_cost_fallback' for p in state['positions']):return False
        c.execute('INSERT OR IGNORE INTO fund_curve_points VALUES(?,?,?,?,?,?,?)',
            (slot.isoformat(),at.isoformat(),units(state['equity_eur']),units(state['cash_eur']),
             units(state['unrealized_eur']),int(state['valuation_complete']),
             'verified_quotes' if state['valuation_complete'] else 'last_verified_quotes'))
    return True


def daily_points(db,at=None):
    at=at or datetime.now(timezone.utc)
    start,end=window(at)
    until=min(at,end)
    if until<start:return []
    with db.tx() as c:
        # Retain only provably complete legacy observations. Old incomplete
        # records did not identify whether entry costs or verified marks were used.
        for row in c.execute("SELECT * FROM equity WHERE portfolio_id='fund' AND valuation_complete=1 AND created_at>=? AND created_at<=? ORDER BY created_at,id",(start.isoformat(),until.isoformat())).fetchall():
            observed=datetime.fromisoformat(row['created_at'].replace('Z','+00:00'))
            slot=slot_for(observed)
            if slot is not None:
                c.execute('INSERT OR IGNORE INTO fund_curve_points VALUES(?,?,?,?,?,?,?)',
                    (slot.isoformat(),row['created_at'],row['equity_u'],row['cash_u'],row['unrealized_u'],1,'confirmed_equity'))
        return [dict(r) for r in c.execute('SELECT slot_at AS id,slot_at AS created_at,observed_at,equity_u,cash_u,unrealized_u,valuation_complete,sample_source FROM fund_curve_points WHERE slot_at>=? AND slot_at<=? AND observed_at<=? ORDER BY slot_at',(start.isoformat(),until.isoformat(),until.isoformat()))]


async def run(db,stop):
    while not stop.is_set():
        try:await asyncio.to_thread(record_point,db)
        except Exception as exc:db.integration('equity_curve','error',safe_error(exc))
        try:await asyncio.wait_for(stop.wait(),timeout=5)
        except asyncio.TimeoutError:pass
