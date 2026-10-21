from datetime import datetime,timezone
import pytest
from backend.config import Settings,now,units
from backend.db import uid
from backend.intelligence import AI,BudgetError,PRICE_CARDS
from backend.models import agent_model,request_model
from backend.manager import create_request
from backend.worker import enqueue
from backend.budget import resume_spend_blocked_jobs


CFG=Settings(_env_file=None,openai_api_key='fixture')


@pytest.mark.parametrize('department',['research','demo','fund'])
def test_technical_luna_takes_precedence_and_tracks_approach_changes(db,department):
    with db.tx() as c:c.execute('UPDATE agents SET department=? WHERE id=1',(department,))
    assert agent_model(db,CFG,1)=='gpt-6-luna'
    assert request_model(db,CFG,'agent_report',1)=='gpt-6-luna'
    assert request_model(db,CFG,'manager_review',1)=='gpt-5.4-mini'
    with db.tx() as c:c.execute("UPDATE agent_mandates SET approach='news' WHERE agent_id=1")
    assert agent_model(db,CFG,1)==('gpt-5.4-mini' if department=='research' else 'gpt-6.1-sol')


@pytest.mark.parametrize('status',['settled','reserved','uncertain'])
def test_old_monthly_limit_never_stops_default_work_and_keeps_usage(db,status):
    with db.tx() as c:
        c.execute('INSERT OR REPLACE INTO fx VALUES(?,?,?,?)',(now()[:10],'1.10','TEST',now()))
        c.execute('INSERT INTO usage VALUES(?,?,?,?,?,?,?,?,?,?)',('historic',1,'agent','gpt-6.1-sol',100,100,units('999'),units('999'),status,now()))
    cfg=Settings(_env_file=None,openai_api_key='fixture',monthly_budget_eur='0.01')
    rid,_=AI(db,cfg).reserve('agent','gpt-6-luna','small',1000,1)
    assert db.one('SELECT status FROM usage WHERE id=?',(rid,))['status']=='reserved'
    historical=db.one("SELECT * FROM usage WHERE id='historic'")
    assert historical['status']==status and historical['reserved_u']==units('999')
    assert create_request(db,cfg,'Analysiere eine neue Hypothese')['status']=='pending'
    assert PRICE_CARDS['gpt-6-luna'][0]<PRICE_CARDS['gpt-5.4-mini'][0]


def test_resume_only_latest_budget_block_without_replaying_other_failures(db):
    rows=[enqueue(db,'analysis',{},1) for _ in range(3)]
    for i,jid in enumerate(rows):
        with db.tx() as c:c.execute("UPDATE jobs SET status='blocked',created_at=?,error=? WHERE id=?",(f'2026-10-20T08:0{i}:00+00:00','Lokales Monatsbudget ausgeschöpft; neue KI-Aufgaben gesperrt',jid))
    unknown=enqueue(db,'news_thesis',{},26)
    context=enqueue(db,'analysis',{},2)
    broker=enqueue(db,'broker_submit',{},1)
    with db.tx() as c:
        c.execute("UPDATE jobs SET status='uncertain',error='network unknown' WHERE id=?",(unknown,))
        c.execute("UPDATE jobs SET status='blocked',error='KI-Kontext überschreitet lokale Grenze' WHERE id=?",(context,))
        c.execute("UPDATE jobs SET status='blocked',error='Lokales Monatsbudget ausgeschöpft; neue KI-Aufgaben gesperrt' WHERE id=?",(broker,))
    db.set('context_capacity_v2',True)
    assert resume_spend_blocked_jobs(db,CFG)==1
    assert db.one('SELECT status FROM jobs WHERE id=?',(rows[-1],))['status']=='pending'
    assert db.one('SELECT COUNT(*) n FROM jobs WHERE status=\'superseded\'')['n']==2
    assert db.one('SELECT status FROM jobs WHERE id=?',(unknown,))['status']=='uncertain'
    assert db.one('SELECT status FROM jobs WHERE id=?',(context,))['status']=='blocked'
    assert db.one('SELECT status FROM jobs WHERE id=?',(broker,))['status']=='blocked'
    assert resume_spend_blocked_jobs(db,CFG)==0


def test_unlimited_preserves_missing_key_unpriced_and_provider_pause_gates(db):
    with pytest.raises(BudgetError,match='fehlt'):AI(db,Settings(_env_file=None)).reserve('agent','gpt-6-luna','small',100,1)
    with pytest.raises(BudgetError,match='Preiskarte'):AI(db,CFG).reserve('agent','unknown','small',100,1)
    db.set('openai_retry_after','2099-01-01T00:00:00+00:00')
    with pytest.raises(BudgetError,match='pause'):AI(db,CFG).reserve('agent','gpt-6-luna','small',100,1)


def test_context_capacity_accepts_valid_continuation_and_bounds_extremes(db):
    with db.tx() as c:c.execute('INSERT OR REPLACE INTO fx VALUES(?,?,?,?)',(now()[:10],'1.10','TEST',now()))
    rid,_=AI(db,CFG).reserve('agent','gpt-6-luna',{'input':'x'*170000},2400,1)
    assert db.one('SELECT status FROM usage WHERE id=?',(rid,))['status']=='reserved'
    with pytest.raises(BudgetError):AI(db,CFG).reserve('agent','gpt-6-luna',{'input':'x'*400000},2400,1)


@pytest.mark.asyncio
async def test_large_tool_result_does_not_strand_analysis_and_final_turn_finishes(db,monkeypatch,research_morning):
    import json
    from types import SimpleNamespace
    import backend.intelligence as intelligence
    requests=[]
    decision={'action':'research','symbol':'AAPL','qty':'0','stop_usd':None,'take_usd':None,
              'hypothesis':'Inspect available history','conclusion':'No valid entry signal',
              'evidence_ids':[],'rejected_alternatives':[],'memory':'Data gap','proposed_strategy':None}
    async def call(self,kind,messages,agent_id=None,tools=None,schema=None):
        requests.append({'tools':tools,'messages':list(messages)})
        if len(requests)<4:
            item=SimpleNamespace(type='function_call',name='read_fund_data',arguments=json.dumps({'dataset':'bars'}),call_id=str(len(requests)))
            return SimpleNamespace(output=[item])
        return SimpleNamespace(output=[],output_text=json.dumps(decision))
    monkeypatch.setattr(AI,'call',call)
    monkeypatch.setattr(intelligence,'read_data',lambda *a,**kw:{'payload':'x'*400000})
    monkeypatch.setattr(intelligence,'response_inputs',lambda response:[{'type':'function_call','name':'read_fund_data','arguments':'{}','call_id':response.output[0].call_id}])
    context={}
    result=await AI(db,CFG)._generate_analysis({'approach':'technical'},{'id':'fixture'},context,1)
    assert result.action=='research' and len(requests)==4
    assert requests[-1]['tools'] is None
    outputs=[x for x in requests[-1]['messages'] if x.get('type')=='function_call_output']
    assert all(json.loads(x['output'])['result_omitted'] for x in outputs)
    assert len(context['tool_receipts'][0]['result']['payload'])==400000
