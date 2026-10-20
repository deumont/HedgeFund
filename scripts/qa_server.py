"""Isolated browser QA. Temporary DB, no API keys, no autonomous worker or live orders."""
import sys,hashlib,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.db import DB
from backend.api import create_app
from backend.providers import Providers
import uvicorn
salt='02'*16
digest=hashlib.scrypt(b'ATLAS-local-QA-only',salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
with tempfile.TemporaryDirectory(prefix='atlas-browser-qa-') as folder:
    cfg=Settings(_env_file=None,openai_api_key='',alpaca_paper_api_key='',alpaca_paper_secret_key='',
                 database_path=str(Path(folder)/'qa.sqlite3'),ceo_password_hash=salt+':'+digest,port=8766)
    db=DB(cfg.database_path)
    app=create_app(cfg,db)
    Providers(db,cfg).diagnose()
    uvicorn.run(app,host='127.0.0.1',port=8766,access_log=False)
