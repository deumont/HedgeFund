import pytest
from datetime import datetime,timezone
from backend.db import DB
from backend.catalog import seed
from backend.config import units
from backend.db import dumps
from datetime import timedelta

AT=datetime(2026,10,20,15,30,tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    d=DB(tmp_path/'test.sqlite3')
    d.init()
    seed(d)
    with d.tx() as c:
        c.execute("INSERT INTO sessions VALUES(?,?,?,?)",('2026-10-20','2026-10-20T09:30:00-04:00','2026-10-20T16:00:00-04:00','test fixture'))
        c.execute("INSERT INTO fx VALUES(?,?,?,?)",('2026-10-20','1.10','TEST fixture',AT.isoformat()))
        for symbol in ['AAPL','SPY','QQQ','MSFT','AMD','NVDA']:
            c.execute('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',(symbol,'99.95','100','100','100',AT.isoformat(),AT.isoformat(),'TEST fixture'))
            c.execute('INSERT INTO assets VALUES(?,?,?,?,?)',(symbol,1,'us_equity','NASDAQ',AT.isoformat()))
            for i in range(8):
                stamp=AT-timedelta(minutes=(9-i)*15)
                close=85+i*2
                c.execute('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',(symbol,stamp.isoformat(),'15Min',str(close-.5),str(close+1),str(close-1),str(close),10000,'Alpaca IEX','raw'))
        spec={'kind':'momentum','lookback':2,'threshold':.01,'holding_bars':4,'stop_pct':.02,
              'timeframe_minutes':15,'max_data_delay_minutes':15,'requires_realtime':False,'requires_full_market':False}
        c.execute('UPDATE strategies SET spec=?,created_at=?',(dumps(spec),(AT-timedelta(days=1)).isoformat()))
    d.integration('market_stream','connected','TEST fixture')
    d.set('risk_confirmed',True)
    d.set('trading_enabled',True)
    return d
