import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from backend.config import Settings,now,units
from backend.db import dumps,uid
from backend.news_agents import configure,mandate,assess_news,save_thesis,Thesis,initial_strategy,event_signal
from backend.research_desks import DESKS,NEWS_IDS,watched_symbols
from backend.web_research import research_public_web,source_records,WEB_TOOL,WEB_CALL_LIMIT,public_url
from backend.intelligence import AI,BudgetError
from backend.worker import Worker
from backend.reporting import review_agents
from backend.decision_quality import RUBRIC,quality_evidence
from backend.ledger import Ledger,RiskError
from backend.daily import fallback_pair
from conftest import AT

CFG=Settings(_env_file=None,openai_api_key='fixture')

def news_agent(db,aid=76):
    with db.tx() as c:c.execute("UPDATE agent_mandates SET approach='news' WHERE agent_id=?",(aid,))
    configure(db)

def search_response():
    def item(data):return SimpleNamespace(type=data['type'],model_dump=lambda **kw:data)
    return SimpleNamespace(output=[item({'type':'web_search_call','action':{'type':'search','sources':[{'url':'https://www.sec.gov/filing?utm_source=x'}]}}),
        item({'type':'message','content':[{'annotations':[{'type':'url_citation','url':'https://www.sec.gov/filing','title':'Original filing'}]}]})],output_text='Dated filing is background; no fresh catalyst confirmed.')

def test_fifty_distinct_desks_and_role_boundaries_survive_reconfiguration(db):
    with db.tx() as c:
        c.execute('DELETE FROM agent_mandates')
    configure(db);configure(db)
    assert len(DESKS)==len(NEWS_IDS)==50
    assert len({mandate(db,i)['focus'] for i in NEWS_IDS})==50
    assert mandate(db,26)['desk']['watchlist'][0]=='MCD'
    assert mandate(db,27)['desk']['watchlist'][0]=='TTWO'
    for aid in range(1,51):
        with pytest.raises(RiskError,match='Research'):Ledger(db).submit(aid,'AAPL','buy',1,f'forbidden-{aid}',at=AT)
    assert not db.all('SELECT * FROM orders')
    assert {r['department']:r['n'] for r in db.all('SELECT department,COUNT(*) n FROM agents GROUP BY department')}=={'research':50,'demo':25,'fund':25}

@pytest.mark.asyncio
async def test_actual_web_tool_is_used_sources_persist_cache_and_no_fake_news(db,research_morning,monkeypatch):
    news_agent(db,26);calls=[]
    async def call(self,kind,messages,aid,**kw):
        assert kind=='web_research' and aid==26 and kw['tools']==[WEB_TOOL]
        task=json.loads(messages[0]['content']);assert 'portfolio' not in task and 'stocks' in task
        calls.append(task);return search_response()
    monkeypatch.setattr(AI,'call',call)
    r=await research_public_web(db,CFG,26,['AAPL'])
    again=await research_public_web(db,CFG,26,['AAPL'])
    assert r['status']=='sourced' and r['publication_time_verified'] is False
    assert r['sources']==[{'url':'https://www.sec.gov/filing','title':'Original filing','cited':True}]
    assert len(calls)==1 and again['id']==r['id']
    assert not db.all('SELECT * FROM news') and not db.all('SELECT * FROM event_theses') and not db.all('SELECT * FROM orders')
    with db.tx() as c:c.execute("UPDATE web_research SET created_at=?",((datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),))
    await research_public_web(db,CFG,26,['AAPL']);assert len(calls)==2

@pytest.mark.parametrize('url',['http://127.0.0.1/a','https://192.168.0.1/a','file:///secret','https://user:password@example.com/a','https://server.internal/a','javascript:alert(1)'])
def test_web_citations_reject_local_or_credential_urls(url):assert public_url(url) is None

def test_web_tool_cost_and_retrieved_tokens_are_reserved_atomically(db,monkeypatch):
    monkeypatch.setattr('backend.intelligence.latest_fx',lambda *a:__import__('decimal').Decimal('1.10'))
    ai=AI(db,CFG)
    plain,_=ai.reserve('agent','gpt-5.4-mini',{},2400,26)
    web,_=ai.reserve('web_research','gpt-5.4-mini',{'tools':[WEB_TOOL],'max_tool_calls':WEB_CALL_LIMIT},2400,26)
    assert db.one('SELECT reserved_u FROM usage WHERE id=?',(web,))['reserved_u']>db.one('SELECT reserved_u FROM usage WHERE id=?',(plain,))['reserved_u']+units('.17')
    low=Settings(_env_file=None,openai_api_key='fixture',monthly_budget_eur='.1')
    with pytest.raises(BudgetError):AI(db,low).reserve('web_research','gpt-5.4-mini',{'tools':[WEB_TOOL],'max_tool_calls':WEB_CALL_LIMIT},2400,26)

def test_monitor_covers_every_owned_stock_and_watchlist_new_news_wakes_within_same_bar(db,monkeypatch):
    news_agent(db);db.set('agent-stock-76','AAPL')
    # Existing owned stock outside the desk's starter list must stay monitored.
    with db.tx() as c:
        c.execute('UPDATE agents SET paused=1 WHERE id!=76')
        c.execute('INSERT INTO positions VALUES(?,?,?,?,?,?,?,?,?,?,?)',('watch-pos','fund',76,'MSFT','1','100',100000000,'1.10','98',None,AT.isoformat()))
    monkeypatch.setattr('backend.worker.phase',lambda *a:{'trading':True})
    w=Worker(db,CFG);monkeypatch.setattr(w.signals,'evaluate',lambda *a:SimpleNamespace(valid=False))
    w.monitor_signals(AT)
    jobs=db.all("SELECT payload FROM jobs WHERE kind='news_thesis'")
    assert {'AAPL','MSFT'}<={json.loads(j['payload'])['symbol'] for j in jobs}
    assert {'AAPL','MSFT'}<=set(watched_symbols(db,76))
    with db.tx() as c:c.execute("UPDATE jobs SET status='completed'")
    w.monitor_signals(AT+timedelta(seconds=1));assert len(db.all('SELECT * FROM jobs'))==len(jobs)
    with db.tx() as c:c.execute('INSERT INTO news VALUES(?,?,?,?,?,?,?,?,?,?)',('fresh','issuer','new fact','new fact','https://example.org/news','["AAPL"]',now(),now(),'reported','company'))
    w.monitor_signals(AT+timedelta(minutes=1))
    assert len(db.all('SELECT * FROM jobs'))==len(jobs)+1
    assert not db.all('SELECT * FROM orders')

@pytest.mark.asyncio
async def test_web_background_alone_never_authorizes_trade_and_research_cannot_assess_order(db,monkeypatch):
    news_agent(db);news_agent(db,26)
    monkeypatch.setattr('backend.calendar.phase',lambda *a:{'trading':True})
    async def web(*a,**kw):return {'id':'background','status':'sourced'}
    monkeypatch.setattr('backend.web_research.research_public_web',web)
    assert (await assess_news(db,CFG,76,'AAPL'))['status']=='background_only_no_fresh_catalyst'
    assert (await assess_news(db,CFG,26,'AAPL'))['status']=='research_no_execution'
    assert not db.all('SELECT * FROM event_theses') and not db.all('SELECT * FROM orders')

@pytest.mark.asyncio
async def test_manager_gets_role_and_prior_evidence_rubric_instead_of_profit_only(db,monkeypatch):
    async def call(self,kind,messages,**kw):
        context=json.loads(messages[0]['content']);assert context['quality_rubric']==RUBRIC
        facts=context['agents'];assert facts[0]['decision_quality']['execution_eligible'] is False
        assert facts[1]['decision_quality']['execution_eligible'] is True
        return SimpleNamespace(output_text=dumps({'ratings':[{'agent_id':1,'score':8,'reason':'Recherche ist die Aufgabe; fehlende Trades sind keine Schwäche.'},{'agent_id':76,'score':4,'reason':'Ohne Vorabbelege kein bewiesener Informationsvorteil.'}]}))
    monkeypatch.setattr(AI,'call',call);await review_agents(db,CFG,[1,76])
    assert db.one('SELECT score FROM manager_reviews WHERE agent_id=1')['score']==8

def test_staffing_tie_break_does_not_reward_lucky_profit(db):
    base={'promotion_ready':False,'manager_score':5,'metrics':{'research_tests':0}}
    facts=[{**base,'id':i,'department':dept,'metrics':{'realized_eur':profit}} for i,dept,profit in [(51,'demo',-5),(52,'demo',10000),(76,'fund',0),(77,'fund',2)]]
    first=fallback_pair(db,facts,'2026-10-21')
    for f in facts:f['metrics']['realized_eur']*=-100
    second=fallback_pair(db,facts,'2026-10-21')
    assert (first.promote,first.demote)==(second.promote,second.demote)


def test_manager_reads_fill_linked_pretrade_dossier_not_later_story(db,monkeypatch):
    monkeypatch.setattr('backend.ledger.now',lambda:AT.isoformat())
    order=Ledger(db).submit(76,'AAPL','buy',1,'pretrade-proof',stop_usd=98,reason='Valid strategy entry',at=AT)
    fill=Ledger(db).fill(order['id'],AT)
    proof={'event_thesis':{'id':'original','summary':'Before entry: contract revenue hypothesis'},
           'decision_dossier':{'causal_case':'Documented before entry','counterevidence':'Contract may be cancelled','created_at':(AT-timedelta(seconds=2)).isoformat()}}
    with db.tx() as c:
        c.execute('UPDATE signal_decisions SET observations=?,created_at=? WHERE id=(SELECT signal_id FROM order_signals WHERE order_id=?)',
                  (dumps(proof),(AT-timedelta(seconds=1)).isoformat(),order['id']))
        # An attractive later narrative is not evidence of what the trader knew.
        c.execute('INSERT INTO thesis_dossiers VALUES(?,?,?)',('later',dumps({'causal_case':'I knew it all along'}),(AT+timedelta(hours=1)).isoformat()))
    evidence=quality_evidence(db,76,AT.date().isoformat())
    case=evidence['pretrade_cases'][0]
    assert case['id']==fill['id'] and case['pre_execution_signal'] is True
    assert case['decision_dossier']['causal_case']=='Documented before entry'
    proof['decision_dossier']['created_at']=(AT+timedelta(seconds=1)).isoformat()
    with db.tx() as c:c.execute('UPDATE signal_decisions SET observations=?',(dumps(proof),))
    assert quality_evidence(db,76,AT.date().isoformat())['pretrade_cases'][0]['decision_dossier'] is None


@pytest.mark.asyncio
async def test_trading_research_records_original_sources_and_reasoning_before_valid_signal(db,research_morning,monkeypatch):
    from backend.news_agents import prepare_strategy
    from backend.signals import SignalEngine
    news_agent(db);prepare_strategy(db,76)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return AT-timedelta(minutes=16)
    monkeypatch.setattr('backend.news_agents.datetime',Clock)
    monkeypatch.setattr('backend.news_agents.now',lambda:Clock.now().isoformat())
    monkeypatch.setattr('backend.calendar.phase',lambda *a:{'trading':True})
    with db.tx() as c:c.execute('INSERT INTO news VALUES(?,?,?,?,?,?,?,?,?,?)',('issuer-1','Issuer','Contract awarded','Order volume confirmed','https://example.org/issuer','["AAPL"]',(AT-timedelta(hours=1)).isoformat(),(AT-timedelta(hours=1)).isoformat(),'reported','company'))
    async def web(*a,**kw):return {'id':'web-background','status':'sourced'}
    async def call(self,kind,*a,**kw):
        assert kind=='news_trade'
        return SimpleNamespace(output_text=dumps({'thesis':dict(symbol='AAPL',event_type='company',direction='positive',confidence=.85,evidence_ids=['issuer-1'],summary='Contract revenue may exceed prior expectations.',company_context='Margin contribution uncertain.'),
            'intent':'enter','target_position_pct':.15,'reduce_fraction':None,'causal_case':'Award could increase future revenue.','counterevidence':'Customer can cancel.','priced_in':'Compare award with prior guidance.','invalidation':'Cancellation or smaller contract value.','source_limits':'Only issuer announcement; independently unverified.'}))
    monkeypatch.setattr('backend.web_research.research_public_web',web);monkeypatch.setattr(AI,'call',call)
    result=await assess_news(db,CFG,76,'AAPL')
    dossier=json.loads(db.one('SELECT payload FROM thesis_dossiers WHERE thesis_id=?',(result['thesis_id'],))['payload'])
    assert dossier['counterevidence']=='Customer can cancel.' and dossier['source_snapshot'][0]['headline']=='Contract awarded'
    with db.tx() as c:c.execute("UPDATE news SET headline='Later revision'")
    decision=SignalEngine(db).evaluate(76,'AAPL','buy',AT)
    assert decision.valid and not db.all('SELECT * FROM orders')
    assert json.loads(db.one('SELECT observations FROM signal_decisions ORDER BY rowid DESC LIMIT 1')['observations'])['decision_dossier']['source_snapshot'][0]['headline']=='Contract awarded'
