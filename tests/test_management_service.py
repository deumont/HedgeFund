import asyncio
import pytest
from backend.config import Settings
from backend.management import ManagementService
from backend.worker import Worker,enqueue


def test_trade_worker_and_management_claim_disjoint_jobs(db,research_morning):
    cfg=Settings(_env_file=None,openai_api_key='')
    report=enqueue(db,'agent_report',{},76,priority=0)
    analysis=enqueue(db,'analysis',{},1,priority=60)
    assert Worker(db,cfg).claim()['id']==analysis
    service=ManagementService(db,cfg)
    assert service.claim()['id']==report
    assert service.claim() is None
    assert not db.all('SELECT * FROM orders')


@pytest.mark.asyncio
async def test_management_persists_completion_without_trading_worker_or_browser(db,monkeypatch):
    job=enqueue(db,'agent_report',{},76)
    stop=asyncio.Event()
    async def report(*a):
        stop.set()
        return {'report_id':'fixture-report'}
    monkeypatch.setattr('backend.management.write_report',report)
    await ManagementService(db,Settings(_env_file=None)).runner(stop)
    assert db.one('SELECT status FROM jobs WHERE id=?',(job,))['status']=='completed'
    assert not db.all('SELECT * FROM fills')


@pytest.mark.asyncio
async def test_management_cancellation_is_uncertain_not_automatic_replay(db,monkeypatch):
    job=enqueue(db,'agent_report',{},76)
    async def cancelled(*a):raise asyncio.CancelledError()
    monkeypatch.setattr('backend.management.write_report',cancelled)
    with pytest.raises(asyncio.CancelledError):
        await ManagementService(db,Settings(_env_file=None)).runner(asyncio.Event())
    assert db.one('SELECT status FROM jobs WHERE id=?',(job,))['status']=='uncertain'


@pytest.mark.asyncio
async def test_manager_scheduling_does_not_depend_on_trading_session(db,monkeypatch):
    stop=asyncio.Event();seen=[]
    def scheduled(*args):seen.append(True);stop.set()
    monkeypatch.setattr('backend.management.schedule',scheduled)
    await ManagementService(db,Settings(_env_file=None,openai_api_key='fixture')).run(stop)
    assert seen==[True]
    assert not db.all('SELECT * FROM orders')
