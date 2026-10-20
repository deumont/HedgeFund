"""Optional Supabase console bridge; never executes a trade outside the local API gates."""
import asyncio
import hashlib
import json
import re
import secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit,parse_qsl,urlencode
import httpx
from .config import now
from .db import uid,dumps
from .providers import safe_error

BASE_PATHS=['overview','agents','system','trading-floor','closeout','research','portfolios','portfolio/fund','chats','data/jobs',
            'data/news','data/strategies','data/orders_all','data/decisions','data/quotes','data/broker']
DATASETS={'fund','agents','agent_detail','fills','orders','news','events','analyses','backtests','strategies',
          'decisions','evaluations','risk','usage','documents','quotes','bars','memories','agent_equity',
          'signal_decisions','jobs','orders_all','broker'}


def allowed_path(method,path):
    if not isinstance(path,str) or len(path)>200 or '://' in path or '..' in path or path.startswith('/'):
        return False
    parsed=urlsplit(path)
    params=parse_qsl(parsed.query,keep_blank_values=True)
    if any(k not in ('agent_id','offset') or not v.isdigit() or int(v)>1000000 for k,v in params):
        return False
    clean=parsed.path
    if method=='GET':
        return (clean in BASE_PATHS or bool(re.fullmatch(r'agents/(?:[1-9][0-9]?|100)|portfolio/(?:fund|demo-[0-9]{3})|jobs/[a-f0-9-]{36}',clean))
                or clean.startswith('data/') and clean[5:] in DATASETS)
    return method=='POST' and not params and (clean in ('chat','task','action','evaluate','broker/submit') or
           bool(re.fullmatch(r'agents/(?:[1-9][0-9]?|100)/report|(?:orders|broker)/[a-f0-9-]{36}/cancel|jobs/[a-f0-9-]{36}/retry|decisions/[a-f0-9-]{36}/confirm',clean)))


def normalize_path(path):
    p=urlsplit(path)
    return p.path+('?' + urlencode(sorted(parse_qsl(p.query))) if p.query else '')


class CloudBridge:
    def __init__(self,db,cfg):
        self.db,self.cfg=db,cfg
        self.engine_id=db.get('cloud_engine_id') or uid()
        self.db.set('cloud_engine_id',self.engine_id)
        self.token=None
        self.token_hash=None
        self.last_sync=0
        self.next_detail=1

    @property
    def enabled(self):
        return self.cfg.cloud_sync_enabled and bool(self.cfg.supabase_url and self.cfg.supabase_secret_key)

    def validate_config(self):
        url=urlsplit(self.cfg.supabase_url)
        if url.scheme!='https' or not re.fullmatch(r'[a-z0-9]{20}\.supabase\.co',url.netloc) or url.path not in ('','/'):
            raise ValueError('Nur die feste HTTPS-Supabase-Projektadresse erlaubt')
        if self.cfg.supabase_secret_key.startswith('sb_publishable_'):
            raise ValueError('Worker benötigt einen geheimen serverseitigen Supabase-Schlüssel')

    def local_session(self):
        self.token=secrets.token_urlsafe(32)
        self.token_hash=hashlib.sha256(self.token.encode()).hexdigest()
        with self.db.tx() as c:
            c.execute('INSERT INTO auth_sessions VALUES(?,?,?)',(self.token_hash,
                (datetime.now(timezone.utc)+timedelta(hours=13)).isoformat(),now()))

    async def run(self,stop):
        if not self.enabled:
            return
        try:
            self.validate_config()
            self.local_session()
            headers={'apikey':self.cfg.supabase_secret_key,'Content-Type':'application/json'}
            if self.cfg.supabase_secret_key.startswith('eyJ'):
                headers['Authorization']='Bearer '+self.cfg.supabase_secret_key
            async with httpx.AsyncClient(base_url=self.cfg.supabase_url.rstrip('/')+'/rest/v1/',
                headers=headers,
                timeout=12,trust_env=False,follow_redirects=False) as remote, httpx.AsyncClient(
                base_url=f'http://127.0.0.1:{self.cfg.port}/api/',cookies={'atlas_session':self.token},
                timeout=15,trust_env=False,follow_redirects=False) as local:
                while not stop.is_set():
                    try:
                        await self.cycle(remote,local)
                        self.db.integration('supabase','connected','Private Cloud-Konsole synchronisiert; lokale Engine bleibt einzige Ausführungsinstanz')
                    except Exception as exc:
                        self.db.integration('supabase','error',safe_error(exc))
                    try: await asyncio.wait_for(stop.wait(),timeout=5)
                    except asyncio.TimeoutError: pass
        finally:
            if self.token_hash:
                with self.db.tx() as c: c.execute('DELETE FROM auth_sessions WHERE token_hash=?',(self.token_hash,))

    async def cycle(self,remote,local):
        stamp=now()
        r=await remote.post('atlas_engine?on_conflict=id',headers={'Prefer':'resolution=merge-duplicates'},
                            json={'id':True,'engine_id':self.engine_id,'connected_at':stamp})
        r.raise_for_status()
        r=await remote.post('rpc/atlas_claim_commands',json={'p_engine':self.engine_id});r.raise_for_status()
        for command in r.json():
            await self.command(remote,local,command)
        clock=asyncio.get_running_loop().time()
        if clock-self.last_sync>=max(30,self.cfg.cloud_sync_seconds):
            for path in BASE_PATHS:
                await self.publish(remote,local,path)
            # Warm all agent pages progressively without delaying trading or flooding the free tier.
            for _ in range(5):
                await self.publish(remote,local,'agents/'+str(self.next_detail))
                self.next_detail=self.next_detail%100+1
            self.last_sync=clock

    async def publish(self,remote,local,path,payload=None):
        if not allowed_path('GET',path):
            raise ValueError('Cloud-Lesepfad gesperrt')
        if payload is None:
            r=await local.get(path);r.raise_for_status();payload=r.json()
        # Show recent complete records, never cropped or invented record contents.
        if path.startswith('agents/') and isinstance(payload,dict):
            payload={k:v for k,v in payload.items() if k in ('profile','stats','runtime','day','manager_review')}
        encoded=dumps(payload).encode()
        if len(encoded)>900000:
            raise ValueError('Cloud-Datensatz überschreitet die kostenlose Synchronisationsgrenze')
        digest=hashlib.sha256(encoded).hexdigest()
        r=await remote.post('atlas_snapshots?on_conflict=path',headers={'Prefer':'resolution=merge-duplicates'},
            json={'path':normalize_path(path),'payload':payload,'etag':digest,'captured_at':now()})
        r.raise_for_status()

    async def command(self,remote,local,command):
        cid=command['id']; key='cloud-command-'+cid
        previous=self.db.get(key)
        if previous:
            result=previous if previous.get('status') in ('completed','failed') else {
                'status':'uncertain','error':'Ausführung bereits begonnen; nicht automatisch wiederholt'}
        elif datetime.fromisoformat(command['expires_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc):
            result={'status':'expired','error':'Auftrag abgelaufen; keine Ausführung'}
        elif command.get('engine_id')!=self.engine_id or not allowed_path(command['method'],command['path']):
            result={'status':'failed','error':'Cloud-Auftrag oder Ausführungsinstanz nicht freigegeben'}
        else:
            # Write intent before any side effect. An ambiguous crash is never auto-retried.
            self.db.set(key,{'status':'processing'})
            try:
                r=await local.request(command['method'],command['path'],
                    json=command.get('body') if command['method']=='POST' else None)
                data=r.json()
                if r.is_success:
                    if command['method']=='GET':
                        await self.publish(remote,local,command['path'],data)
                    elif command['path']=='chat':
                        await self.publish(remote,local,'chats')
                        await self.publish(remote,local,'data/jobs')
                    result={'status':'completed','result':data}
                else:
                    result={'status':'failed','error':str(data.get('detail','Lokale Aktion abgelehnt'))}
            except Exception as exc:
                result={'status':'uncertain','error':safe_error(exc)+' Keine automatische Wiederholung.'}
            self.db.set(key,result)
            self.last_sync=0
            self.db.event('cloud_command','Authentifizierter Cloud-Auftrag: '+command['path'],data={'command_id':cid,'status':result['status']})
        r=await remote.patch('atlas_commands',params={'id':'eq.'+cid},json=result);r.raise_for_status()
