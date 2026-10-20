import hashlib
import json
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest
import requests
from fastapi.testclient import TestClient
from backend.config import Settings,units
from backend.api import create_app
from backend.intelligence import AI,BudgetError,evaluate,propose_swap,apply_rotations,read_data
from backend.providers import PaperOnlyAdapter,Providers
from backend.worker import enqueue,Worker
from backend.db import DB
from conftest import AT


def config(db,**kwargs):
    salt='01'*16
    password=hashlib.scrypt(b'only-test-password',salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return Settings(_env_file=None,database_path=db.path,ceo_password_hash=salt+':'+password,
                    openai_api_key='unit-test-not-real',**kwargs)


def test_budget_reservations_and_fail_closed(db):
    cfg=config(db,monthly_budget_eur=Decimal('0.03'))
    ai=AI(db,cfg)
    # Use current dated FX fixture because costs use actual current time.
    today=datetime.now(timezone.utc).date().isoformat()
    with db.tx() as c:
        c.execute('INSERT OR REPLACE INTO fx VALUES(?,?,?,?)',(today,'1.10','TEST fixture',AT.isoformat()))
    first,_=ai.reserve('agent','gpt-5.4-mini','small',1000,1)
    assert db.one('SELECT status FROM usage WHERE id=?',(first,))['status']=='reserved'
    with pytest.raises(BudgetError):
        ai.reserve('agent','unknown-unpriced-model','small',1000,2)
    for _ in range(10):
        try:
            ai.reserve('agent','gpt-5.4-mini','small',1000,3)
        except BudgetError:
            break
    else:
        pytest.fail('Budget did not stop calls')
    assert db.one('SELECT SUM(reserved_u) n FROM usage')['n']<=units('.03')


def test_rotation_confirmed_next_session_and_sizes(db):
    result=propose_swap(db,51,76,'Begründete Testplanung',effective='2026-10-21')
    assert not apply_rotations(db,AT)
    with db.tx() as c:
        c.execute("UPDATE decisions SET status='approved' WHERE id=?",(result['decision_id'],))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',('2026-10-21','2026-10-21T09:30:00-04:00','2026-10-21T16:00:00-04:00','Alpaca fixture'))
    morning=datetime.fromisoformat('2026-10-21T08:00:00+00:00')
    assert apply_rotations(db,morning)==[result['decision_id']]
    assert not apply_rotations(db,morning)
    assert db.one('SELECT department FROM agents WHERE id=51')['department']=='fund'
    assert {r['department']:r['n'] for r in db.all('SELECT department,COUNT(*) n FROM agents GROUP BY department')}=={'research':50,'demo':25,'fund':25}


def test_no_fabricated_scores(db):
    result=evaluate(db,1)
    assert result['score'] is None
    assert result['metrics']['win_rate_pct'] is None
    assert not result['metrics']['eligible']
    assert read_data(db,'fills',1)['rows']==[]
    with pytest.raises(ValueError):
        read_data(db,'auth_sessions')


def test_no_live_transport_or_credentials(db):
    adapter=PaperOnlyAdapter()
    for url in ['https://api.alpaca.markets/v2/orders','http://paper-api.alpaca.markets/v2/orders','https://paper-api.alpaca.markets.evil.test/v2/orders']:
        request=requests.Request('POST',url).prepare()
        with pytest.raises(RuntimeError):
            adapter.send(request)
    cfg=Settings(_env_file=None,openai_api_key='',alpaca_paper_api_key='',alpaca_paper_secret_key='')
    Providers(db,cfg).diagnose()
    assert db.one("SELECT status FROM integrations WHERE name='alpaca_paper'")['status']=='blocked'


def test_queue_recovery_and_dedup(db):
    cfg=config(db)
    a=enqueue(db,'analysis',agent_id=1,dedupe='same')
    b=enqueue(db,'analysis',agent_id=1,dedupe='same')
    assert a==b
    worker=Worker(db,cfg)
    assert worker.claim()['id']==a
    assert worker.claim() is None
    assert DB(db.path).one('SELECT status FROM jobs WHERE id=?',(a,))['status']=='running'


@pytest.fixture
def client(db):
    return TestClient(create_app(config(db),db))


def test_authentication_csrf_no_secret_exposure(client):
    assert client.get('/api/overview').status_code==401
    assert client.post('/api/login',json={'password':'bad'}).status_code==401
    assert client.post('/api/login',json={'password':'only-test-password'}).status_code==200
    response=client.get('/api/system')
    assert response.status_code==200
    assert 'unit-test-not-real' not in response.text
    assert client.post('/api/action',json={'action':'kill'},headers={'Origin':'https://untrusted.test'}).status_code==403
    assert client.get('/api/overview',headers={'Host':'untrusted.test'}).status_code==400
    assert client.post('/api/action',json={'action':'risk_confirm'}).status_code==400
    assert client.post('/api/action',json={'action':'live','confirmed':True}).status_code==400
    assert client.post('/api/logout',json={}).status_code==200
    assert client.get('/api/agents').status_code==401


def test_api_dashboard_metrics_and_sections(client):
    client.post('/api/login',json={'password':'only-test-password'})
    overview=client.get('/api/overview').json()
    assert overview['fund']['equity_eur']==3000
    assert overview['fund']['day_pnl_eur']==0
    assert overview['active_traders']==0
    for endpoint in ['agents','agents/17','portfolios','portfolio/fund','chats','system','data/quotes','data/jobs','data/strategies','data/news','data/decisions','data/orders_all','data/broker']:
        response=client.get('/api/'+endpoint)
        assert response.status_code==200,(endpoint,response.text)
    assert len(client.get('/api/agents').json())==100
    assert len(client.get('/api/portfolios').json())==26


def test_console_blocks_uploads_and_manual_broker_orders(client,db):
    client.post('/api/login',json={'password':'only-test-password'})
    good='time,open,high,low,close,volume\n2025-01-01T00:00:00+00:00,100,102,99,101,1000\n'
    request={'symbol':'SPY','csv_text':good,'source':'Licensed unit fixture','licensed':True,'adjustment':'raw'}
    assert client.post('/api/import/bars',json=request).status_code==403
    assert client.post('/api/broker/submit',json={'symbol':'SPY','side':'buy','order_type':'market','confirmed':True}).status_code==403
    assert db.one("SELECT COUNT(*) n FROM bars WHERE source LIKE 'Import:%'")['n']==0
    assert not db.all('SELECT * FROM broker_orders')


@pytest.mark.asyncio
async def test_missing_key_never_fakes_ai_output(db):
    ai=AI(db,Settings(_env_file=None,openai_api_key=''))
    with pytest.raises(BudgetError):
        await ai.analyze(1)
    assert db.one('SELECT COUNT(*) n FROM analyses')['n']==0
