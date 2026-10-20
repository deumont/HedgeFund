import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import Settings,ROOT
from backend.db import DB
from backend.ledger import Ledger
cfg=Settings()
db=DB(cfg.database_path)
db.set('trading_enabled',False)
db.set('supervisor_paused',True)
db.set('kill_switch',True)
ledger=Ledger(db)
for order in db.all("SELECT id FROM orders WHERE status IN ('pending','triggered') AND side='buy'"):
    ledger.cancel(order['id'],'Windows-Stopp')
for _ in range(6):
    if not db.one('SELECT id FROM positions LIMIT 1'):
        break
    time.sleep(2)
db.set('worker_stop_requested',True)
for _ in range(45):
    if db.get('worker_identity',{}).get('pid',0)==0:
        break
    time.sleep(2)
print('Datenbankbackup:',db.backup(ROOT/'backups'))
