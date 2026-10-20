"""Authenticated read-only local smoke test; password and cookie are never printed."""
import sys
from pathlib import Path
import httpx
import json
from websockets.sync.client import connect
ROOT=Path(__file__).resolve().parents[1]
password=[x.split(': ',1)[1] for x in (ROOT/'local-access.txt').read_text(encoding='utf-8').splitlines() if x.startswith('Passwort: ')][0]
with httpx.Client(base_url='http://127.0.0.1:8765',trust_env=False) as client:
    assert client.get('/api/overview').status_code==401
    response=client.post('/api/login',json={'password':password})
    response.raise_for_status()
    for path in ['overview','closeout','research','research-roster','research/agents/1','team','agents','agents/17','system','portfolios','portfolio/fund','chats','data/jobs','data/news','data/decisions','data/strategies','data/orders_all']:
        r=client.get('/api/'+path)
        r.raise_for_status()
        print(path,'OK')
    o=client.get('/api/overview').json()
    assert o['fund']['initial_eur']==3000
    assert len(client.get('/api/agents').json())==100
    print('Worker online:',o['worker_online'],'Paper-only:',o['paper_only'])
    cookie='; '.join(k+'='+v for k,v in client.cookies.items())
    with connect('ws://127.0.0.1:8765/api/live',origin='http://127.0.0.1:8765',additional_headers={'Cookie':cookie},open_timeout=10) as socket:
        message=json.loads(socket.recv(timeout=10))
        assert message['type']=='update'
        print('Authenticated live activity socket: OK')
    client.post('/api/logout',json={}).raise_for_status()
