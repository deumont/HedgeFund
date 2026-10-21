import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from backend.config import Settings,now
from backend.db import dumps
from backend.ledger import Ledger
from backend.reporting import day_view,write_report,review_agents,schedule
from backend.universe import eligible,select_stock,active_symbols,rotate
from backend.intelligence import AI
from backend.providers import Providers
from conftest import AT


@pytest.mark.asyncio
async def test_agent_authored_report_persists_once_with_exact_trade_proof(db,monkeypatch):
    monkeypatch.setattr('backend.ledger.now',lambda:AT.isoformat())
    order=Ledger(db).submit(76,'AAPL','buy',1,'report-fill',stop_usd=98,reason='Valid entry',at=AT)
    fill=Ledger(db).fill(order['id'],AT)
    calls=[]
    async def call(self,kind,messages,agent_id=None,**kwargs):
        assert kind=='agent_report' and agent_id==76
        facts=json.loads(messages[0]['content'])['evidence']
        assert facts['trade_count']==1
        assert facts['trades'][0]['signal']['indicators']['entry_condition'] is True
        calls.append(kind)
        return SimpleNamespace(output_text=dumps({'report':'Ich habe eine AAPL-Position nach gültigem Signal eröffnet.','evidence_ids':[fill['id']]}))
    monkeypatch.setattr(AI,'call',call)
    cfg=Settings(_env_file=None)
    await write_report(db,cfg,76,AT.date().isoformat())
    await write_report(db,cfg,76,AT.date().isoformat())
    view=day_view(db,76,AT.date().isoformat())
    assert len(calls)==1 and view['report']['model']=='gpt-6-luna'
    assert view['actions'][0]['id']==fill['id']


@pytest.mark.asyncio
async def test_report_rejects_invented_evidence(db,monkeypatch):
    async def call(*a,**kw):return SimpleNamespace(output_text=dumps({'report':'Fake','evidence_ids':['invented']}))
    monkeypatch.setattr(AI,'call',call)
    with pytest.raises(ValueError,match='Belege'):await write_report(db,Settings(_env_file=None),76)
    assert not db.all('SELECT * FROM agent_reports')


@pytest.mark.asyncio
async def test_manager_reviews_are_real_bounded_assessments_not_profit_scores(db,monkeypatch):
    async def call(self,kind,messages,**kw):
        assert kind=='manager_review'
        return SimpleNamespace(output_text=dumps({'ratings':[{'agent_id':76,'score':5.5,'reason':'Noch keine Handelsstichprobe; vorläufig.'},{'agent_id':77,'score':6,'reason':'Datenregeln berücksichtigt.'}]}))
    monkeypatch.setattr(AI,'call',call)
    await review_agents(db,Settings(_env_file=None),[76,77])
    assert [r['score'] for r in db.all('SELECT score FROM manager_reviews ORDER BY agent_id')]==[5.5,6]
    assert db.one('SELECT score FROM evaluations WHERE agent_id=76')['score'] is None
    with pytest.raises(ValueError):await review_agents(db,Settings(_env_file=None),[76])


def test_manager_schedule_is_continuous_batched_and_deduplicated(db):
    cfg=Settings(_env_file=None,openai_api_key='fixture')
    schedule(db,cfg,AT)
    assert len(db.all("SELECT * FROM jobs WHERE kind='manager_review'"))==10
    schedule(db,cfg,AT+timedelta(seconds=1))
    assert len(db.all("SELECT * FROM jobs WHERE kind='manager_review'"))==10
    schedule(db,cfg,AT+timedelta(minutes=5))
    assert len(db.all("SELECT * FROM jobs WHERE kind='manager_review'"))==11
    assert not db.all('SELECT * FROM fills')


def test_catalog_accepts_stock_outside_original_watchlist_but_does_not_authorize_trade(db):
    cfg=Settings(_env_file=None)
    with db.tx() as c:c.execute('INSERT INTO assets VALUES(?,?,?,?,?)',('XYZ',1,'us_equity','TXSE',now()))
    assert eligible(db,'XYZ') and 'XYZ' not in cfg.symbols
    select_stock(db,cfg,76,'XYZ')
    assert 'XYZ' in active_symbols(db,cfg)
    assert db.one("SELECT kind FROM jobs WHERE kind='prepare_stock'")
    from backend.ledger import RiskError
    with pytest.raises(RiskError):Ledger(db).submit(76,'XYZ','buy',1,'missing-data',stop_usd=90,reason='test',at=AT)
    assert not db.all('SELECT * FROM fills')
    with pytest.raises(ValueError):select_stock(db,cfg,76,'UNKNOWN')


def test_bulk_catalog_handles_new_exchange_and_deactivates_removed_assets(db,monkeypatch):
    class Client:
        def get_all_assets(self,request):return [{'symbol':'XYZ','class':'us_equity','exchange':'TXSE','tradable':True}]
    monkeypatch.setattr('backend.providers.paper_client',lambda cfg,**kw:Client())
    Providers(db,Settings(_env_file=None)).assets()
    assert eligible(db,'XYZ')
    assert not eligible(db,'AAPL')


def test_default_models_and_price_cards_use_exact_requested_agent_model(db):
    cfg=Settings(_env_file=None,openai_api_key='fixture')
    assert cfg.openai_model=='gpt-6.1-sol'
    with db.tx() as c:c.execute('INSERT OR REPLACE INTO fx VALUES(?,?,?,?)',(now()[:10],'1.10','TEST',now()))
    first,_=AI(db,cfg).reserve('agent','gpt-6.1-sol','small',100,1)
    second,_=AI(db,cfg).reserve('manager','gpt-5.4-mini','small',100)
    assert db.one('SELECT reserved_u FROM usage WHERE id=?',(first,))['reserved_u']>db.one('SELECT reserved_u FROM usage WHERE id=?',(second,))['reserved_u']
