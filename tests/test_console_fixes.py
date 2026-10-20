from datetime import timedelta,datetime,timezone
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.config import Settings
from backend.ledger import Ledger,RiskError
from backend.intelligence import evaluate,manager_chat
from backend.manager import create_request,reply_id
from backend.agent_state import agent_states
from conftest import AT


def test_last_verified_mark_is_retained_but_does_not_authorize_execution(db):
    ledger=Ledger(db)
    order=ledger.submit(76,'AAPL','buy',1,'mark-test',stop_usd=98,reason='valid strategy',at=AT)
    ledger.fill(order['id'],AT)
    with db.tx() as c:c.execute("UPDATE quotes SET bid='101',ask='101.05' WHERE symbol='AAPL'")
    from backend.ledger import snapshot
    with db.tx() as c:fresh=snapshot(c,'fund',AT)
    with db.tx() as c:stale=snapshot(c,'fund',AT+timedelta(minutes=5))
    assert stale['equity_eur']==fresh['equity_eur']
    assert not stale['valuation_complete']
    assert stale['positions'][0]['valuation_source']=='last_verified_quote'
    with pytest.raises(RiskError):
        ledger.submit(77,'AAPL','buy',1,'stale',stop_usd=98,reason='valid strategy',at=AT+timedelta(minutes=5))


def test_instant_manager_answer_is_short_persisted_and_free(db):
    cfg=Settings(_env_file=None,openai_api_key='')
    response=create_request(db,cfg,'Hat schon jemand einen Trade genommen?')
    assert response['status']=='completed'
    row=db.one('SELECT * FROM chats WHERE id=?',(reply_id(response['message_id']),))
    assert 'keine ausgeführten' in row['content']
    assert len(row['content'].split())<80
    assert db.one('SELECT COUNT(*) n FROM usage')['n']==0
    # A different process/client sees the completed answer with no browser state.
    from backend.db import DB
    assert DB(db.path).one('SELECT status FROM jobs WHERE id=?',(response['job_id'],))['status']=='completed'


def test_budget_block_is_a_durable_answer_instead_of_silent_chat(db):
    response=create_request(db,Settings(_env_file=None,openai_api_key=''),'Analysiere eine komplexe neue Hypothese')
    answer=db.one('SELECT content FROM chats WHERE id=?',(reply_id(response['message_id']),))
    assert answer and 'KI-Zugang' in answer['content']
    assert response['status']=='completed'


@pytest.mark.asyncio
async def test_completed_manager_request_is_not_reexecuted_after_restart(db,monkeypatch):
    cfg=Settings(_env_file=None,openai_api_key='')
    response=create_request(db,cfg,'hallo')
    monkeypatch.setattr('backend.intelligence.AI.call',lambda *a,**k:pytest.fail('must not call model twice'))
    result=await manager_chat(db,cfg,'hallo',response['message_id'])
    assert result['id']==reply_id(response['message_id'])
    assert db.one("SELECT COUNT(*) n FROM chats WHERE role='assistant'")['n']==1


def test_agent_status_and_rating_progress_do_not_invent_profit_rank(db):
    states=agent_states(db,[76,1])
    assert states[76]['runtime']['label']
    assert states[76]['stats']['realized_eur']==0
    rating=evaluate(db,76)
    assert rating['score'] is None and not rating['metrics']['eligible']
    assert rating['metrics']['evidence_progress']=={'closed_trades':0,'required_closed_trades':30,'trading_days':0,'required_trading_days':20,'daily_returns':0,'required_daily_returns':20}
