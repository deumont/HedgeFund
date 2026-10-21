import asyncio
import json
from datetime import datetime,timedelta,timezone
import httpx
import pytest
from backend.cloud import CloudBridge,allowed_path
from backend.config import Settings


def config(**kwargs):
    return Settings(_env_file=None,supabase_url='https://'+'a'*20+'.supabase.co',
                    supabase_secret_key='sb_secret_test_fixture',cloud_sync_enabled=True,**kwargs)


@pytest.mark.parametrize('path',['../.env','https://evil.test/','/overview','session','login','data/auth_sessions',
                               'data/meta','data/quotes?sql=delete','agents/101','agents/1?offset=-1'])
def test_cloud_cannot_read_secrets_or_arbitrary_paths(path):
    assert not allowed_path('GET',path)


@pytest.mark.parametrize('path',['login','import/bars','task?x=1','https://evil.test/','../action','data/quotes'])
def test_cloud_only_forwards_declared_mutations(path):
    assert not allowed_path('POST',path)


def test_cloud_does_not_allow_insecure_or_non_supabase_targets(db):
    cfg=config();bridge=CloudBridge(db,cfg)
    for url in ['http://'+'a'*20+'.supabase.co','https://evil.test','https://'+'a'*20+'.supabase.co.evil.test']:
        cfg.supabase_url=url
        with pytest.raises(ValueError):bridge.validate_config()


@pytest.mark.asyncio
async def test_cloud_command_is_recorded_before_mutation_and_not_replayed(db):
    bridge=CloudBridge(db,config());calls=[];updates=[]
    cid='00000000-0000-4000-8000-000000000001'
    def local(request):
        assert db.get('cloud-command-'+cid)=={'status':'processing'}
        calls.append((request.method,request.url.path))
        return httpx.Response(200,json={'job_id':'real-local-job'})
    def remote(request):
        if request.method=='PATCH':updates.append(json.loads(request.content))
        return httpx.Response(204)
    command={'id':cid,'method':'POST','path':'chat','body':{'text':'test'},'engine_id':bridge.engine_id,
             'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()}
    async with httpx.AsyncClient(transport=httpx.MockTransport(local),base_url='http://local/api/') as l, \
               httpx.AsyncClient(transport=httpx.MockTransport(remote),base_url='https://cloud/') as r:
        await bridge.command(r,l,command)
        await bridge.command(r,l,command)
    assert [path for method,path in calls if method=='POST']==['/api/chat']
    assert [path for method,path in calls if method=='GET']==['/api/chats','/api/data/jobs']
    assert updates[0]==updates[1]=={'status':'completed','result':{'job_id':'real-local-job'}}


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['expired','wrong_engine','bad_path','previous_crash'])
async def test_cloud_invalid_or_ambiguous_commands_never_execute(db,mode):
    bridge=CloudBridge(db,config());calls=[]
    cid='00000000-0000-4000-8000-000000000002'
    command={'id':cid,'method':'POST','path':'action','body':{'action':'start_trading','confirmed':True},
             'engine_id':bridge.engine_id,'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()}
    if mode=='expired':command['expires_at']=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    elif mode=='wrong_engine':command['engine_id']='another-engine'
    elif mode=='bad_path':command['path']='../.env'
    else:db.set('cloud-command-'+cid,{'status':'processing'})
    def local(request):calls.append(request);return httpx.Response(500)
    async with httpx.AsyncClient(transport=httpx.MockTransport(local),base_url='http://local/api/') as l, \
               httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(204)),base_url='https://cloud/') as r:
        await bridge.command(r,l,command)
    assert calls==[]


@pytest.mark.asyncio
async def test_cloud_still_uses_existing_local_risk_rejection(db):
    bridge=CloudBridge(db,config());updates=[]
    command={'id':'00000000-0000-4000-8000-000000000003','method':'POST','path':'broker/submit','body':{},
             'engine_id':bridge.engine_id,'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()}
    def remote(request):updates.append(json.loads(request.content));return httpx.Response(204)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(400,json={'detail':'Stale data'})),base_url='http://local/api/') as l, \
               httpx.AsyncClient(transport=httpx.MockTransport(remote),base_url='https://cloud/') as r:
        await bridge.command(r,l,command)
    assert updates==[{'status':'failed','error':'Stale data'}]
    assert db.one('SELECT COUNT(*) n FROM orders')['n']==0


@pytest.mark.asyncio
async def test_cloud_roster_fits_limit_without_duplicating_manager_evidence(db):
    bridge=CloudBridge(db,config());published=[]
    row={'id':1,'day_stats':{'date':'2026-10-21','pnl_eur':3},
         'evaluation':{'facts':'e'*12000},'manager_review':{'score':8,'summary':'Evidence-based','facts':'f'*12000}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (published.append(json.loads(r.content)) or httpx.Response(204))),base_url='https://cloud/') as remote:
        result=await bridge.publish(remote,None,'agents',[dict(row,id=i) for i in range(1,101)])
    assert len(json.dumps(published[0]).encode())<900000
    assert len(result)==100 and result[0]['day_stats']==row['day_stats']
    assert result[0]['manager_review']=={'score':8,'summary':'Evidence-based'}
    assert 'facts' in row['manager_review']  # source records are untouched


@pytest.mark.asyncio
async def test_cloud_agent_history_is_not_mistaken_for_profile_and_keeps_daily_pnl(db):
    bridge=CloudBridge(db,config())
    history={'career':{'periods':[{'department':'demo'}]},'performance':{'roles':[]},'days':[],'day':{'date':'2026-10-21'}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(204)),base_url='https://cloud/') as remote:
        assert await bridge.publish(remote,None,'agents/76/history?month=2026-10',history)==history
        profile={'profile':{'id':76},'day_stats':{'pnl_eur':5},'stats':{},'day':{},'irrelevant':'x'}
        result=await bridge.publish(remote,None,'agents/76',profile)
        assert result['day_stats']=={'pnl_eur':5} and 'irrelevant' not in result


@pytest.mark.asyncio
async def test_cloud_snapshot_failure_does_not_starve_calendar_or_commands(db,monkeypatch):
    import backend.cloud as module
    monkeypatch.setattr(module,'BASE_PATHS',['agents','calendar'])
    bridge=CloudBridge(db,config());calendar=asyncio.Event();blocked=asyncio.Event();started=asyncio.Event()
    async def local(request):
        if request.url.path=='/api/agents':return httpx.Response(200,json={'oversize':'x'*900001})
        if request.url.path=='/api/calendar':calendar.set();return httpx.Response(200,json={'days':[]})
        started.set();await blocked.wait();return httpx.Response(200,json={'profile':{}})
    cid='00000000-0000-4000-8000-000000000004';updates=[]
    command={'id':cid,'method':'GET','path':'calendar','engine_id':bridge.engine_id,
             'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()}
    def remote(request):
        if request.url.path.endswith('atlas_claim_commands'):return httpx.Response(200,json=[command])
        if request.method=='PATCH':updates.append(json.loads(request.content))
        return httpx.Response(204)
    async with httpx.AsyncClient(transport=httpx.MockTransport(local),base_url='http://local/api/') as l, \
               httpx.AsyncClient(transport=httpx.MockTransport(remote),base_url='https://cloud/') as r:
        warming=asyncio.create_task(bridge.sync_snapshots(r,l))
        try:
            await asyncio.wait_for(calendar.wait(),1)
            await asyncio.wait_for(started.wait(),1)
            await asyncio.wait_for(bridge.cycle(r,l),1)  # warming is still blocked
            assert updates==[{'status':'completed','result':{'days':[]}}]
        finally:
            blocked.set();await warming
    assert 'agents' in db.get('cloud_snapshot_errors')
