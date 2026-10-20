import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.db import DB
db=DB(Settings().database_path)
print('paused' if db.get('supervisor_paused',False) else 'enabled')
