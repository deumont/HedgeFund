"""Transport contract tests use explicit fixtures. They do NOT prove account access."""
import json
from datetime import datetime,timezone
from types import SimpleNamespace
import httpx
import pytest
from openai import AsyncOpenAI
from backend.config import Settings
from backend.providers import Providers,paper_client
from backend.intelligence import AI,AgentDecision,StrategySpec,response_inputs,manager_chat
from backend.db import DB
from conftest import AT


def test_strict_schema_nested_objects():
    schema=AgentDecision.model_json_schema()
    assert schema['additionalProperties'] is False
    assert schema['$defs']['StrategySpec']['additionalProperties'] is False
    assert set(schema['required'])==set(schema['properties'])


@pytest.mark.asyncio
async def test_real_sdk_response_contract_persists_usage_memory_strategy(db,monkeypatch):
    today=datetime.now(timezone.utc).date().isoformat()
    with db.tx() as c:
        c.execute('INSERT OR REPLACE INTO fx VALUES(?,?,?,?)',(today,'1.10','TEST fixture',AT.isoformat()))
    cfg=Settings(_env_file=None,openai_api_key='test-fixture-key')
    result={'action':'research','symbol':'SPY','qty':'0','stop_usd':None,'take_usd':None,
            'hypothesis':'Reproduzierbare Testhypothese','conclusion':'Nicht handeln: keine ausreichenden Daten.',
            'evidence_ids':[],'rejected_alternatives':['Ungedeckter Kauf'],'memory':'Datenqualität prüfen.',
            'proposed_strategy':{'kind':'momentum','lookback':12,'holding_bars':3,'threshold':.01,'stop_pct':.02,'position_pct':.25,
                                'timeframe_minutes':15,'max_data_delay_minutes':15,'requires_realtime':False,'requires_full_market':False}}
    seen=[]
    def handler(request):
        seen.append(json.loads(request.content))
        assert request.url.host=='api.openai.com'
        return httpx.Response(200,json={
            'id':'resp_fixture','object':'response','created_at':1770000000,'model':'gpt-5.4-mini','status':'completed',
            'error':None,'incomplete_details':None,'instructions':None,'metadata':{},'parallel_tool_calls':True,
            'temperature':1.0,'tool_choice':'auto','tools':[],'top_p':1.0,'background':False,
            'output':[{'id':'msg_fixture','type':'message','status':'completed','role':'assistant','content':[
                {'type':'output_text','text':json.dumps(result),'annotations':[]}]}],
            'usage':{'input_tokens':300,'output_tokens':300,'total_tokens':600,
                     'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':50}}})
    def factory(**kwargs):
        kwargs['http_client']=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return AsyncOpenAI(**kwargs)
    monkeypatch.setattr('backend.intelligence.AsyncOpenAI',factory)
    analysis,decision=await AI(db,cfg).analyze(1)
    assert decision.action=='research'
    assert db.one('SELECT result FROM analyses WHERE id=?',(analysis,))
    assert db.one('SELECT COUNT(*) n FROM memories')['n']==1
    assert db.one('SELECT MAX(version) n FROM strategies WHERE agent_id=1')['n']==2
    assert db.one('SELECT status FROM usage')['status']=='settled'
    assert seen[0]['store'] is False
    assert seen[0]['include']==['reasoning.encrypted_content']
    assert seen[0]['text']['format']['strict'] is True


def test_alpaca_sdk_calendar_and_quote_storage(db,monkeypatch):
    cfg=Settings(_env_file=None,alpaca_paper_api_key='fixture-paper-key',alpaca_paper_secret_key='fixture-secret')
    client=paper_client(cfg)
    assert client._base_url=='https://paper-api.alpaca.markets'
    assert client._retry==0
    provider=Providers(db,cfg)
    provider.store_quote('TEST','99','100',50,50,AT.isoformat())
    provider.store_quote('TEST','1','2',50,50,'2026-10-19T14:00:00+00:00')
    assert db.one("SELECT ask FROM quotes WHERE symbol='TEST'")['ask']=='100'


def test_replayed_tool_calls_use_input_contract_without_output_status():
    output=SimpleNamespace(output=[
        SimpleNamespace(type='reasoning',id='rs_fixture',summary=[],encrypted_content='encrypted-fixture',status='completed'),
        SimpleNamespace(type='function_call',id='fc_fixture',name='read_fund_data',arguments='{}',call_id='call_fixture',status='completed')])
    items=response_inputs(output)
    assert all('status' not in item for item in items)
    assert items[0]['encrypted_content']=='encrypted-fixture'
    assert set(items[1])=={'type','name','arguments','call_id'}


@pytest.mark.asyncio
async def test_manager_sdk_tool_roundtrip_uses_real_database_fixture(db,monkeypatch):
    today=datetime.now(timezone.utc).date().isoformat()
    with db.tx() as c:
        c.execute('INSERT OR REPLACE INTO fx VALUES(?,?,?,?)',(today,'1.10','TEST fixture',AT.isoformat()))
    cfg=Settings(_env_file=None,openai_api_key='test-fixture-key')
    requests=[]
    def handler(request):
        params=json.loads(request.content)
        requests.append(params)
        if len(requests)==1:
            output=[{'type':'reasoning','id':'rs_fixture','summary':[],'encrypted_content':'opaque-fixture'},
                    {'type':'function_call','id':'fc_fixture','call_id':'call_fixture','name':'read_fund_data',
                     'arguments':json.dumps({'dataset':'fund','agent_id':None,'offset':0}),'status':'completed'}]
        else:
            replay=params['input']
            assert all('status' not in item for item in replay)
            tool=next(item for item in replay if item.get('type')=='function_call_output')
            assert json.loads(tool['output'])['equity_eur']==3000
            output=[{'id':'msg_fixture','type':'message','status':'completed','role':'assistant','content':[
                {'type':'output_text','text':'Fonds: 3.000 EUR laut Ledger fund.','annotations':[]}]}]
        return httpx.Response(200,json={'id':'resp_fixture','object':'response','created_at':1770000000,
            'model':'gpt-5.4-mini','status':'completed','output':output,'tools':[],
            'usage':{'input_tokens':300,'output_tokens':100,'total_tokens':400,
                     'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':50}}})
    def factory(**kwargs):
        kwargs['http_client']=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return AsyncOpenAI(**kwargs)
    monkeypatch.setattr('backend.intelligence.AsyncOpenAI',factory)
    result=await manager_chat(db,cfg,'Was ist der Fondsstand?')
    assert len(requests)==2
    assert len(result['evidence'])==2
    assert db.one("SELECT COUNT(*) n FROM chats WHERE role='assistant'")['n']==1
