from datetime import datetime,timezone
from decimal import Decimal
import pytest
from backend.config import Settings,now,units
from backend.db import uid
from backend.intelligence import AI,BudgetError
from backend.manager import create_request,reply_id


def spend(db,amount,status='settled'):
    with db.tx() as c:
        c.execute('INSERT INTO usage VALUES(?,?,?,?,?,?,?,?,?,?)',
            (uid(),None,'test','gpt-5.4-mini',0,0,units(amount),units(amount),status,now()))
        c.execute('INSERT OR REPLACE INTO fx VALUES(?,?,?,?)',
            (datetime.now(timezone.utc).date().isoformat(),'1.10','TEST fixture',now()))


def test_previous_daily_ceiling_does_not_block_ai_or_manager(db):
    spend(db,'2')
    # A leftover legacy env setting cannot reintroduce a daily limit.
    cfg=Settings(_env_file=None,openai_api_key='test-only',monthly_budget_eur=Decimal('30'),daily_budget_eur=Decimal('1'))
    rid,_=AI(db,cfg).reserve('agent','gpt-5.4-mini','small',1000,1)
    assert db.one('SELECT status FROM usage WHERE id=?',(rid,))['status']=='reserved'
    response=create_request(db,cfg,'Analysiere eine neue Hypothese')
    assert response['status']=='pending'
    assert not db.one('SELECT id FROM chats WHERE id=?',(reply_id(response['message_id']),))


@pytest.mark.parametrize('status',['settled','reserved','uncertain'])
def test_monthly_ceiling_still_blocks_ai_and_explains_manager(db,status):
    spend(db,'30',status)
    cfg=Settings(_env_file=None,openai_api_key='test-only',monthly_budget_eur=Decimal('30'))
    with pytest.raises(BudgetError,match='Monatsbudget'):
        AI(db,cfg).reserve('agent','gpt-5.4-mini','small',1000,1)
    response=create_request(db,cfg,'Analysiere eine neue Hypothese')
    assert response['status']=='completed'
    answer=db.one('SELECT content FROM chats WHERE id=?',(reply_id(response['message_id']),))
    assert 'Monatsbudget' in answer['content']
